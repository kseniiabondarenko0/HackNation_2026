"""Offline tests of the free AI pipeline (Gemini free tier -> Groq free plan): every HTTP call is mocked."""
import gzip
import json
import re
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

import httpx
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from analysis import groq, llmbase, service
from analysis.models import Analysis, LLMState, LLMUsage
from collection import sourcefinder
from collection.extract import content_hash
from collection.models import Article, Rejected, Source, Submission
from collection.netsafe import FetchError
from collection.services import _fetch_article, run_source
from collection.window import cutoff, to_date
from tests.test_sources import getter as site_getter, robots

QUOTE = "System został wdrożony w trzech szkołach i skrócił czas oceny o 40 procent."
TEXT = "Politechnika Testowa opracowała system oceny prac. " + QUOTE + " Wyniki opisano w raporcie."
FAST = {"RETRY_BASE_S": 0, "MIN_INTERVAL_S": 0}
GEM = {**settings.GEMINI, "API_KEY": "test-gemini", **FAST}
GRQ_OFF = {**settings.GROQ, "API_KEY": "", **FAST}
GRQ_ON = {**settings.GROQ, "API_KEY": "test-groq", **FAST}


def raw(**kw):
    base = {"is_initiative": True, "score": 72, "summary": "System oceny prac wdrożony w szkołach.",
            "explanation": "Opisano wdrożenie i zmierzony wynik.", "evidence": [QUOTE],
            "missing_info": ["Brak informacji o kosztach"], "uncertainty": "Jedno źródło.", "sector": "Edukacja",
            "innovation_types": ["edukacyjna"], "stage": "in_use", "path": "transfer", "authors": [],
            "published_date": None, "date_evidence": None, "credibility": "wysoka",
            "credibility_reason": "Oficjalna strona uczelni."}
    return {**base, **kw}


def g_reply(obj, finish="STOP", text=None):
    cand = {"content": {"parts": [{"text": text if text is not None else json.dumps(obj)}]}, "finishReason": finish}
    return httpx.Response(200, json={"candidates": [cand], "usageMetadata": {
        "promptTokenCount": 100, "candidatesTokenCount": 50}})


def q_reply(obj, finish="stop", text=None):
    return httpx.Response(200, json={"choices": [{"message": {"content": text if text is not None else json.dumps(obj)},
                                                  "finish_reason": finish}],
                                     "usage": {"prompt_tokens": 120, "completion_tokens": 60}})


def err(status, message="x", **headers):
    return httpx.Response(status, json={"error": {"message": message}}, headers=headers)


class Net:
    """Fake network: queued answers per provider; any unexpected call fails the test."""

    def __init__(self, gemini=(), groq=()):
        self.queue = {"gemini": list(gemini), "groq": list(groq)}
        self.calls = []

    def __call__(self, url, **kw):
        name = "gemini" if "generativelanguage" in url else "groq"
        self.calls.append((name, kw))
        if not self.queue[name]:
            raise AssertionError(f"nieoczekiwane wywołanie {name}")
        return self.queue[name].pop(0)

    def count(self, name=None):
        return len([c for c in self.calls if name in (None, c[0])])


def ago(days):
    return timezone.now() - timedelta(days=days)


def mk_article(n=1, text=TEXT, published_at=None, **kw):
    src, _ = Source.objects.get_or_create(entry_url="https://u.example.pl/", defaults=dict(
        name="Uczelnia Testowa", organization_type="university", discovery_type="html"))
    return Article.objects.create(source=src, original_url=f"https://u.example.pl/a/{n}", title=f"Tytuł {n}",
                                  text=text, content_hash=content_hash(text + str(n)), status="fetched",
                                  published_at=published_at, fetched_at=timezone.now(), **kw)


class TempArchive:
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.archive_dir = Path(tmp.name)
        patcher = override_settings(ARCHIVE_DIR=self.archive_dir)
        patcher.enable()
        self.addCleanup(patcher.disable)

    def archived(self):
        path = self.archive_dir / "old_articles.jsonl.gz"
        if not path.exists():
            return []
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]


@override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
@override_settings(ANALYSIS={**settings.ANALYSIS, "WINDOW_MONTHS": 8})
class AnalysisTests(TempArchive, TestCase):
    def run_pending(self, gemini=(), groq=(), **kw):
        net = Net(gemini, groq)
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            n = service.analyze_pending("ai", **kw)
        return n, net

    def test_confirmed_recent_initiative_is_published(self):
        a = mk_article(published_at=ago(30))
        n, net = self.run_pending([g_reply(raw())])
        an = Analysis.objects.get(article=a)
        self.assertEqual((n, an.verdict, an.potential, an.backend), (1, "glowna", 72, "ai"))
        self.assertEqual(an.data["verified"]["quotes"], [QUOTE])
        self.assertEqual((an.data["ai"]["provider"], an.data["ai"]["model"]), ("gemini", settings.GEMINI["MODEL"]))
        self.assertEqual(Article.objects.get(pk=a.pk).pipeline_status, "opublikowano")
        kw = net.calls[0][1]   # the key travels only in the header, never in the body
        self.assertEqual(kw["headers"]["x-goog-api-key"], "test-gemini")
        self.assertNotIn("test-gemini", json.dumps(kw["json"]))
        row = LLMUsage.objects.get(provider="gemini")
        self.assertEqual((row.calls, row.tokens_in, row.tokens_out), (1, 100, 50))

    def test_invented_quote_is_dropped_and_not_published(self):
        a = mk_article(published_at=ago(10))
        self.run_pending([g_reply(raw(evidence=["Zdanie, którego w artykule nigdy nie było napisane."]))])
        an = Analysis.objects.get(article=a)
        self.assertEqual((an.verdict, an.data["verified"]["quotes"]), ("weryfikacja", []))
        self.assertTrue(an.data["dropped"])

    def test_low_score_goes_to_compact_registry_without_archive(self):
        a = mk_article(published_at=ago(10))
        n, _ = self.run_pending([g_reply(raw(score=30))])
        self.assertEqual(n, 1)
        self.assertFalse(Article.objects.filter(pk=a.pk).exists() or Analysis.objects.exists())
        r = Rejected.objects.get()
        self.assertEqual((r.url, r.content_hash, r.score), (a.original_url, a.content_hash, 30))
        self.assertIn("30/100", r.reason)
        self.assertEqual(self.archived(), [])

    def test_not_an_initiative_is_rejected(self):
        mk_article(published_at=ago(10))
        self.run_pending([g_reply(raw(is_initiative=False, score=10))])
        self.assertEqual(Rejected.objects.count(), 1)

    def test_old_article_is_archived_then_rejected_without_a_paid_call(self):
        a = mk_article(published_at=ago(300))
        net = Net()
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            obj, _ = service.analyze_article(a, "ai")
        self.assertIsNone(obj)
        self.assertEqual(net.count(), 0)
        self.assertIn("starsza niż 8 mies.", Rejected.objects.get().reason)
        (rec,) = self.archived()
        self.assertEqual((rec["url"], rec["text"], rec["source"]["name"]), (a.original_url, TEXT, "Uczelnia Testowa"))

    def test_pending_pass_leaves_out_of_window_rows_alone(self):
        a = mk_article(published_at=ago(300))
        n, net = self.run_pending()
        self.assertEqual((n, net.count()), (0, 0))
        self.assertTrue(Article.objects.filter(pk=a.pk).exists())

    def test_unknown_date_needs_verification_unless_evidenced_in_text(self):
        a = mk_article(1)
        self.run_pending([g_reply(raw(published_date=(date.today() - timedelta(days=20)).isoformat(),
                                      date_evidence="12 stycznia 2020"))])
        an = Analysis.objects.get(article=a)   # FAQ: a missing date never blocks publication, it is only noted
        self.assertEqual((an.verdict, an.data["verified"]["published_at"]), ("glowna", ""))
        self.assertIn("nieustalona", an.data["verdict"]["reason"])
        day = date.today() - timedelta(days=20)
        stamp = f"{day.day}.{day.month:02d}.{day.year}"
        b = mk_article(2, text=f"Opublikowano {stamp}. " + TEXT)
        self.run_pending([g_reply(raw(published_date=day.isoformat(), date_evidence=stamp))])
        an = Analysis.objects.get(article=b)
        self.assertEqual((an.verdict, an.data["verified"]["date_source"]), ("glowna", "treść artykułu"))
        self.assertEqual(to_date(Article.objects.get(pk=b.pk).published_at), day)

    def test_low_credibility_is_not_published(self):
        a = mk_article(published_at=ago(5))
        self.run_pending([g_reply(raw(credibility="niska"))])
        self.assertEqual(Analysis.objects.get(article=a).verdict, "weryfikacja")

    def test_result_is_cached_even_if_the_model_changes(self):
        mk_article(published_at=ago(5))
        _, net = self.run_pending([g_reply(raw())])
        with override_settings(GEMINI={**GEM, "MODEL": "inny-model"}, GROQ=GRQ_ON):
            _, net2 = self.run_pending()
        self.assertEqual((net.count(), net2.count()), (1, 0))

    def test_rejected_hash_is_deduplicated_before_the_call(self):
        a = mk_article(published_at=ago(5))
        Rejected.objects.create(url="https://inna.example.pl/x", content_hash=a.content_hash, reason="wcześniej odrzucone")
        _, net = self.run_pending()
        self.assertEqual(net.count(), 0)
        self.assertFalse(Article.objects.filter(pk=a.pk).exists())

    def test_submission_is_never_deleted(self):
        a = mk_article(published_at=ago(5))
        Submission.objects.create(article=a)
        self.run_pending([g_reply(raw(score=10, is_initiative=False))])
        self.assertTrue(Article.objects.filter(pk=a.pk).exists())
        self.assertEqual(Analysis.objects.get(article=a).verdict, "odrzucone")
        self.assertFalse(Rejected.objects.exists())

    def test_text_is_truncated_before_sending(self):
        with override_settings(LLM={**settings.LLM, "MAX_TEXT_CHARS": 500}):
            mk_article(text="Zdanie testowe numer jeden. " * 400, published_at=ago(5))
            _, net = self.run_pending([g_reply(raw(evidence=[], is_initiative=False))])
        sent = net.calls[0][1]["json"]["contents"][0]["parts"][0]["text"]
        self.assertLess(len(sent), 1100)

    def test_call_budget_per_run(self):
        for i in range(5):
            mk_article(i, published_at=ago(5 + i))
        n, net = self.run_pending([g_reply(raw()) for _ in range(5)], max_calls=2)
        self.assertEqual((n, net.count()), (2, 2))
        self.assertIn("limit", service.last_stats["stopped"])

    def test_daily_limits_stop_calls(self):
        LLMUsage.objects.create(day=date.today(), provider="gemini", calls=GEM["MAX_CALLS_PER_DAY"])
        mk_article(published_at=ago(5))
        n, net = self.run_pending()
        self.assertEqual((n, net.count()), (0, 0))
        self.assertTrue(Article.objects.exists())

    def test_429_is_not_retried_and_pauses_the_provider(self):
        for i in range(3):
            mk_article(i, published_at=ago(5))
        n, net = self.run_pending([err(429, "quota")])
        self.assertEqual((n, net.count()), (0, 1))                       # one request, no retry loop
        self.assertIn("quota", service.last_stats["stopped"])
        self.assertEqual(Article.objects.filter(analysis_attempts__gt=0).count(), 0)
        self.assertTrue(LLMState.objects.get(provider="gemini").blocked_until > timezone.now())
        _, net2 = self.run_pending()                                     # still paused: not even one request
        self.assertEqual(net2.count(), 0)
        LLMState.objects.update(blocked_until=timezone.now() - timedelta(seconds=1))
        n3, net3 = self.run_pending([g_reply(raw()) for _ in range(3)])
        self.assertEqual((n3, net3.count()), (3, 3))                     # quota back: the queue is processed
        self.assertEqual(LLMState.objects.get(provider="gemini").failures, 0)

    def test_retry_after_header_sets_the_pause(self):
        mk_article(published_at=ago(5))
        self.run_pending([err(429, "quota", **{"retry-after": "30"})])
        wait = (LLMState.objects.get(provider="gemini").blocked_until - timezone.now()).total_seconds()
        self.assertTrue(25 <= wait <= 40, wait)

    def test_pause_grows_with_repeated_failures_but_is_capped(self):
        self.assertEqual(llmbase.cooldown_seconds(llmbase.LLMError("quota"), 1), 120)
        self.assertEqual(llmbase.cooldown_seconds(llmbase.LLMError("quota"), 2), 480)
        self.assertEqual(llmbase.cooldown_seconds(llmbase.LLMError("quota"), 10), 6 * 3600)

    def test_network_error_gets_bounded_retries_only(self):
        mk_article(published_at=ago(5))
        n, net = self.run_pending([err(503), err(503), err(503)])
        self.assertEqual((n, net.count()), (0, 3))                       # 1 try + 2 bounded retries
        _, net2 = self.run_pending()
        self.assertEqual(net2.count(), 0)                                # short pause, not a hot loop

    def test_retry_then_success(self):
        mk_article(published_at=ago(5))
        n, net = self.run_pending([err(503), g_reply(raw())])
        self.assertEqual((n, net.count()), (1, 2))

    def test_bad_request_is_not_retried_and_counts_against_the_article(self):
        a = mk_article(published_at=ago(5))
        n, net = self.run_pending([err(400, "bad schema")])
        self.assertEqual((n, net.count()), (0, 1))
        self.assertEqual(Article.objects.get(pk=a.pk).analysis_attempts, 1)

    def test_invalid_json_is_counted_and_eventually_marked_as_error(self):
        a = mk_article(published_at=ago(5))
        for _ in range(3):
            self.run_pending([g_reply(None, text="to nie jest JSON")])
        a.refresh_from_db()
        self.assertEqual((a.analysis_attempts, a.pipeline_status), (3, "błąd"))
        _, net = self.run_pending()
        self.assertEqual(net.count(), 0)

    def test_truncated_answer_is_a_bad_response(self):
        a = mk_article(published_at=ago(5))
        self.run_pending([g_reply(None, finish="MAX_TOKENS", text='{"score": 7')])
        self.assertEqual(Article.objects.get(pk=a.pk).analysis_attempts, 1)

    def test_without_any_key_articles_wait_and_nothing_is_replaced_by_a_formula(self):
        a = mk_article(published_at=ago(5))
        with override_settings(GEMINI={**GEM, "API_KEY": ""}):
            n, net = self.run_pending()
        self.assertEqual((n, net.count(), Analysis.objects.count()), (0, 0, 0))
        self.assertIn("brak kluczy", service.last_stats["stopped"])
        self.assertEqual(Article.objects.get(pk=a.pk).pipeline_status, "zweryfikowano")

    def test_pipeline_counts(self):
        mk_article(1, published_at=ago(5))
        mk_article(2, published_at=ago(6))
        Rejected.objects.create(url="https://x.example.pl/", reason="r")
        self.run_pending([g_reply(raw()), g_reply(raw(score=30))])
        counts = service.pipeline_counts()
        self.assertEqual((counts["opublikowano"], counts["odrzucono"], counts["znaleziono"]), (1, 2, 0))


@override_settings(GEMINI=GEM, GROQ=GRQ_ON)
class FallbackTests(TempArchive, TestCase):
    def run_pending(self, gemini=(), groq=(), **kw):
        net = Net(gemini, groq)
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            n = service.analyze_pending("ai", **kw)
        return n, net

    def test_groq_takes_over_when_gemini_hits_the_quota(self):
        a, b = mk_article(1, published_at=ago(5)), mk_article(2, published_at=ago(6))
        n, net = self.run_pending([err(429, "quota")], [q_reply(raw()), q_reply(raw())])
        self.assertEqual(n, 2)
        self.assertEqual([c[0] for c in net.calls], ["gemini", "groq", "groq"])   # 2nd article skips the paused Gemini
        an = Analysis.objects.get(article=a)
        self.assertEqual((an.verdict, an.data["ai"]["provider"], an.data["ai"]["model"]),
                         ("glowna", "groq", settings.GROQ["MODEL"]))

    def test_groq_request_is_json_mode_with_bearer_key_and_schema_hint(self):
        mk_article(published_at=ago(5))
        _, net = self.run_pending([err(429)], [q_reply(raw())])
        kw = net.calls[1][1]
        self.assertEqual(kw["headers"]["Authorization"], "Bearer test-groq")
        self.assertEqual(kw["json"]["response_format"], {"type": "json_object"})
        system = kw["json"]["messages"][0]["content"]
        self.assertIn('"score": integer', system)
        self.assertIn("JSON", system)
        self.assertNotIn("test-groq", json.dumps(kw["json"]))

    def test_both_providers_unavailable_leaves_the_queue_untouched(self):
        for i in range(3):
            mk_article(i, published_at=ago(5))
        n, net = self.run_pending([err(429)], [err(429, **{"retry-after": "60"})])
        self.assertEqual((n, net.count()), (0, 2))
        self.assertEqual((Analysis.objects.count(), Article.objects.filter(analysis_attempts__gt=0).count()), (0, 0))
        _, net2 = self.run_pending()
        self.assertEqual(net2.count(), 0)                                # both paused: no calls at all
        self.assertEqual(Article.objects.count(), 3)

    def test_unusable_gemini_answer_falls_through_to_groq(self):
        a = mk_article(published_at=ago(5))
        n, net = self.run_pending([g_reply(None, text="nie JSON")], [q_reply(raw())])
        self.assertEqual((n, Analysis.objects.get(article=a).data["ai"]["provider"]), (1, "groq"))
        self.assertEqual(Article.objects.get(pk=a.pk).analysis_attempts, 0)

    def test_groq_truncated_answer_counts_against_the_article(self):
        a = mk_article(published_at=ago(5))
        self.run_pending([err(429)], [q_reply(None, finish="length", text='{"score"')])
        self.assertEqual(Article.objects.get(pk=a.pk).analysis_attempts, 1)

    def test_schema_hint_lists_enums(self):
        from analysis.ai import SCHEMA
        hint = groq.schema_hint(SCHEMA)
        self.assertIn('"stage": jedna z: idea | prototype', hint)
        self.assertIn('"published_date": string lub null', hint)


class DiscoveryIsFreeTests(TestCase):
    SEEDS = [{"name": "Park testowy", "url": "https://park.example.pl/", "tags": ["park naukowo-technologiczny"]}]

    def test_default_discovery_uses_only_free_mechanisms(self):
        self.assertEqual(settings.DISCOVERY["PROVIDERS"], ["seeds", "links"])
        self.assertNotIn("gemini", sourcefinder.QUERY_PROVIDERS)

    def test_seeds_candidates_that_pass_the_probe_start_monitoring_automatically(self):
        with mock.patch.object(sourcefinder, "load_seeds", return_value=self.SEEDS):
            run = sourcefinder.run_discovery(queries=["park naukowo-technologiczny"], providers=["seeds"],
                                             getter=site_getter, robots=robots)
        src = Source.objects.get(entry_url__startswith="https://park.example.pl")
        self.assertEqual((src.status, src.enabled, src.origin, run.stats["auto_approved"]), ("active", True, "discovery", 1))

    def test_auto_approve_can_be_switched_off(self):
        with override_settings(DISCOVERY={**settings.DISCOVERY, "AUTO_APPROVE": False}), \
                mock.patch.object(sourcefinder, "load_seeds", return_value=self.SEEDS):
            sourcefinder.run_discovery(queries=["park naukowo-technologiczny"], providers=["seeds"],
                                       getter=site_getter, robots=robots)
        src = Source.objects.get(entry_url__startswith="https://park.example.pl")
        self.assertEqual((src.status, src.enabled), ("candidate", False))


@override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
@override_settings(ANALYSIS={**settings.ANALYSIS, "WINDOW_MONTHS": 8})
class CollectionFilterTests(TempArchive, TestCase):
    def test_listing_skips_old_and_already_rejected_links(self):
        fresh = format_rfc822(ago(3))
        feed = ("<?xml version='1.0'?><rss><channel>"
                f"<item><link>https://x.example.pl/n/fresh</link><pubDate>{fresh}</pubDate></item>"
                "<item><link>https://x.example.pl/n/old</link><pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate></item>"
                f"<item><link>https://x.example.pl/n/bad</link><pubDate>{fresh}</pubDate></item>"
                "</channel></rss>")
        Rejected.objects.create(url="https://x.example.pl/n/bad", reason="wcześniej odrzucone")
        src = Source.objects.create(name="X", entry_url="https://x.example.pl/feed", discovery_type="rss",
                                    allowed_prefix="https://x.example.pl/")

        def getter(url):
            if url == src.entry_url:
                return url, feed
            raise FetchError("http_404")
        stats = run_source(src, getter=getter, sleep=lambda _: None)
        self.assertEqual(set(Article.objects.values_list("original_url", flat=True)), {"https://x.example.pl/n/fresh"})
        self.assertEqual((stats["too_old"], stats["rejected_known"]), (1, 1))

    def fetch(self, article, **extract):
        data = {"title": "T", "text": "x" * 400, "published_at": None, **extract}
        stats = dict.fromkeys(("fetched", "updated", "duplicates", "skipped", "errors", "unchanged"), 0)
        with mock.patch("collection.services.extract_article", return_value=data):
            _fetch_article(article, lambda url: (url, "<html></html>"), stats)
        return stats

    def test_new_article_with_old_date_is_archived_and_rejected_at_fetch(self):
        src = Source.objects.create(name="X", entry_url="https://x.example.pl/", discovery_type="html")
        a = Article.objects.create(source=src, original_url="https://x.example.pl/old")
        stats = self.fetch(a, published_at=ago(400))
        self.assertEqual(stats["too_old"], 1)
        self.assertFalse(Article.objects.exists())
        self.assertEqual(Rejected.objects.get().content_hash, content_hash("x" * 400))
        (rec,) = self.archived()
        self.assertEqual((rec["url"], rec["text"]), ("https://x.example.pl/old", "x" * 400))

    def test_text_equal_to_a_rejected_one_is_dropped_at_fetch(self):
        src = Source.objects.create(name="X", entry_url="https://x.example.pl/", discovery_type="html")
        Rejected.objects.create(url="https://y.example.pl/m", content_hash=content_hash("x" * 400), reason="słaba ocena")
        a = Article.objects.create(source=src, original_url="https://x.example.pl/mirror")
        self.fetch(a)
        self.assertFalse(Article.objects.exists())
        self.assertTrue(Rejected.objects.filter(url="https://x.example.pl/mirror").exists())

    def test_article_already_in_the_base_is_not_removed_by_a_recheck(self):
        a = mk_article(published_at=ago(400))
        self.fetch(a, text=a.text + " nowy fragment " * 30, published_at=ago(400))
        self.assertTrue(Article.objects.filter(pk=a.pk).exists())


@override_settings(ANALYSIS={**settings.ANALYSIS, "WINDOW_MONTHS": 8})
class PruneWindowTests(TempArchive, TestCase):
    def test_dry_run_changes_nothing(self):
        mk_article(1, published_at=ago(400))
        out = StringIO()
        call_command("prune_window", stdout=out)
        self.assertEqual((Article.objects.count(), self.archived()), (1, []))
        self.assertIn("1", out.getvalue())

    def test_apply_archives_first_then_removes_and_keeps_submissions(self):
        old, kept, fresh = (mk_article(1, published_at=ago(400)), mk_article(2, published_at=ago(400)),
                            mk_article(3, published_at=ago(5)))
        Submission.objects.create(article=kept)
        call_command("prune_window", "--apply", stdout=StringIO())
        self.assertEqual(set(Article.objects.values_list("pk", flat=True)), {kept.pk, fresh.pk})
        self.assertEqual([r["url"] for r in self.archived()], [old.original_url])
        self.assertEqual(Rejected.objects.get().url, old.original_url)

    def test_nothing_is_deleted_when_the_archive_cannot_be_written(self):
        mk_article(1, published_at=ago(400))
        blocker = self.archive_dir / "file"
        blocker.write_text("x")
        with override_settings(ARCHIVE_DIR=blocker / "sub"), self.assertRaises(CommandError):
            call_command("prune_window", "--apply", stdout=StringIO())
        self.assertEqual((Article.objects.count(), Rejected.objects.count()), (1, 0))


@override_settings(ANALYSIS={**settings.ANALYSIS, "WINDOW_MONTHS": 8})
class WindowAndSecretsTests(SimpleTestCase):
    def test_cutoff_is_eight_months_back_and_handles_month_ends(self):
        self.assertEqual(cutoff(date(2026, 11, 21)), date(2026, 3, 21))
        self.assertEqual(cutoff(date(2026, 10, 31)), date(2026, 2, 28))

    def test_keys_are_not_in_the_repository_and_env_and_archive_are_ignored(self):
        root = Path(settings.BASE_DIR)
        ignored = (root / ".gitignore").read_text().split()
        self.assertIn(".env", ignored)
        self.assertIn("archive/", ignored)
        self.assertEqual((settings.GEMINI["API_KEY"], settings.GROQ["API_KEY"]), ("", ""))   # tests never load .env
        pattern = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|gsk_[0-9A-Za-z]{20,}")
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".html", ".md", ".txt", ".json", ".js", ".example")
                 and not any(x in p.parts for x in (".venv", ".git", "node_modules", "staticfiles", "archive"))]
        self.assertEqual([str(p) for p in files if pattern.search(p.read_text(encoding="utf-8", errors="ignore"))], [])

    def test_no_paid_or_grounding_features_in_the_code(self):
        root = Path(settings.BASE_DIR)
        offenders = [str(p) for app in ("analysis", "collection", "web", "config") for p in (root / app).rglob("*.py")
                     if "google_search" in p.read_text(encoding="utf-8") or "grounding" in p.read_text(encoding="utf-8").lower()]
        self.assertEqual(offenders, [])


def format_rfc822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
