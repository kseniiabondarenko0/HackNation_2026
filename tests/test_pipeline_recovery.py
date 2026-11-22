"""Regressions found during live-pipeline checks: typed replies, changed evidence and outage recovery."""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from analysis import ai, currency, retention, service
from analysis.llmbase import LLMError
from analysis.models import Analysis
from analysis.tabs import INTERESTING
from collection.extract import content_hash
from collection.models import Article, Rejected, Source
from collection.services import _fetch_article
from tests.test_ai import GEM, GRQ_OFF, GRQ_ON, Net, QUOTE, TEXT, TempArchive, ago, g_reply, mk_article, q_reply, raw


@override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
class ReplyValidationTests(TempArchive, TestCase):
    def test_wrong_field_types_leave_the_article_queued(self):
        bad_values = ({"evidence": [{"quote": QUOTE}]}, {"evidence": QUOTE}, {"authors": [{}]},
                      {"summary": None}, {"score": True}, {"is_initiative": "true"}, {"stage": []})
        a = mk_article(published_at=ago(1))
        for fields in bad_values:
            with self.subTest(fields=list(fields)):
                net = Net([g_reply(raw(**fields))])
                with mock.patch("analysis.llmbase.httpx.post", side_effect=net), self.assertRaises(LLMError) as raised:
                    service.analyze_article(a, "ai")
                self.assertEqual(raised.exception.kind, "bad_response")
                self.assertTrue(Article.objects.filter(pk=a.pk).exists())
                self.assertFalse(Rejected.objects.exists())

    def test_missing_required_fields_are_not_a_rejection(self):
        a = mk_article(published_at=ago(1))
        net = Net([g_reply({"score": 80})])
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net), self.assertRaises(LLMError) as raised:
            service.analyze_article(a, "ai")
        self.assertEqual(raised.exception.kind, "bad_response")
        self.assertTrue(Article.objects.filter(pk=a.pk).exists())

    def test_bad_article_does_not_stop_the_next_and_attempts_are_bounded(self):
        bad, good = mk_article(1, published_at=ago(1)), mk_article(2, published_at=ago(2))
        malformed = lambda: g_reply(raw(evidence=[{"quote": QUOTE}]))
        net = Net([malformed(), g_reply(raw())])
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            self.assertEqual(service.analyze_pending("ai"), 1)
        self.assertTrue(Analysis.objects.filter(article=good).exists())
        for _ in range(2):
            with mock.patch("analysis.llmbase.httpx.post", side_effect=Net([malformed()])):
                service.analyze_pending("ai")
        bad.refresh_from_db()
        self.assertEqual(bad.analysis_attempts, 3)
        with mock.patch("analysis.llmbase.httpx.post") as post:
            service.analyze_pending("ai")
            post.assert_not_called()

    @override_settings(GROQ=GRQ_ON)
    def test_invalid_gemini_structure_can_fall_back_to_groq(self):
        a = mk_article(published_at=ago(1))
        net = Net([g_reply(raw(evidence=[{}]))], [q_reply(raw())])
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            service.analyze_pending("ai")
        self.assertEqual(Analysis.objects.get(article=a).data["ai"]["provider"], "groq")


class ChangedEvidenceTests(TempArchive, TestCase):
    def setUp(self):
        super().setUp()
        self.a = mk_article(text=(TEXT + " ") * 3, published_at=ago(1))
        self.a.content_hash = content_hash(self.a.text)
        self.a.save(update_fields=["content_hash"])
        self.old_text = self.a.text
        self.data = ai.finalize_ai(raw(), self.a)
        self.an = Analysis.objects.create(article=self.a, backend="ai", input_key=service._key(self.a, "ai"),
                                          verdict="glowna", potential=72, data=self.data, handling="kontakt")

    def change_text(self, text):
        stats = dict.fromkeys(("fetched", "updated", "duplicates", "skipped", "errors", "unchanged"), 0)
        with mock.patch("collection.services.extract_article", return_value={"title": "Zmieniony tekst", "text": text,
                                                                           "published_at": self.a.published_at}):
            _fetch_article(self.a, lambda url: (url, "<html></html>"), stats)
        self.a.refresh_from_db()
        self.an.refresh_from_db()

    def test_changed_text_withdraws_old_evidence_but_keeps_snapshot_and_handling(self):
        self.a.analysis_attempts = 3
        self.a.save(update_fields=["analysis_attempts"])
        self.change_text("Poprzednie wyniki zostały wycofane. " * 15)
        self.assertFalse(Article.objects.filter(INTERESTING, pk=self.a.pk).exists())
        self.assertIsNone(self.an.potential)
        self.assertEqual(self.an.data.get("verified", {}).get("quotes", []), [])
        self.assertEqual(self.an.data["_previous"]["text"], self.old_text)
        self.assertEqual(self.an.handling, "kontakt")
        self.assertEqual(self.a.analysis_attempts, 0)
        html = self.client.get(f"/a/{self.a.pk}/").content.decode()
        self.assertNotIn(QUOTE, html)
        self.assertIn("Treść źródła zmieniła się", html)

    def test_unchanged_text_keeps_current_analysis(self):
        self.change_text(self.old_text)
        self.assertEqual((self.an.verdict, self.an.potential), ("glowna", 72))
        self.assertNotIn("stale", self.an.data)

    @override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
    def test_reanalysis_preserves_one_previous_version_and_restores_current_evidence(self):
        text = "Zaktualizowany opis. " * 20 + QUOTE
        self.change_text(text)
        with mock.patch("analysis.llmbase.httpx.post", side_effect=Net([g_reply(raw())])):
            service.analyze_pending("ai")
        self.an.refresh_from_db()
        self.assertEqual(self.an.verdict, "glowna")
        self.assertNotIn("stale", self.an.data)
        self.assertEqual(self.an.data["verified"]["quotes"], [QUOTE])
        self.assertEqual(self.an.data["_previous"]["text"], self.old_text)
        self.change_text("Jeszcze inny opis. " * 30)
        self.assertEqual(self.an.data["_previous"]["text"], text)
        self.assertNotIn("_previous", self.an.data["_previous"]["data"])

    def test_a_changed_old_article_gets_time_for_reanalysis(self):
        Article.objects.filter(pk=self.a.pk).update(first_seen_at=ago(100))
        self.change_text("Nowy opis tego samego projektu. " * 20)
        retention.cleanup(getter=lambda url: (url, "<html></html>"))
        self.assertTrue(Article.objects.filter(pk=self.a.pk).exists())


class CurrencyRecoveryTests(TestCase):
    def test_held_card_is_rechecked_and_restored_after_source_recovers(self):
        a = mk_article(published_at=ago(1))
        data = ai.finalize_ai(raw(), a)
        data["currency"] = {"failures": 2, "checked_at": "2000-01-01T00:00:00"}
        an = Analysis.objects.create(article=a, input_key=service._key(a, "ai"), backend="ai", verdict="glowna", data=data)
        def unavailable(url):
            raise OSError("test source outage")
        now = timezone.now()
        self.assertEqual(currency.check(an, unavailable, now), "wstrzymano")
        self.assertIn(an.pk, [x.pk for x in currency.due(now + timedelta(days=15), 10)])
        currency.check(an, lambda url: (url, "ok"), now + timedelta(days=15))
        an.refresh_from_db()
        self.assertEqual((an.verdict, an.data["currency"]["failures"]), ("glowna", 0))

    def test_unconfirmed_cards_are_not_promoted_by_a_working_url(self):
        a = mk_article(published_at=ago(1))
        an = Analysis.objects.create(article=a, backend="ai", verdict="weryfikacja", data={})
        self.assertNotIn(an.pk, [x.pk for x in currency.due(timezone.now() + timedelta(days=30), 10)])


class WorkerFairnessTests(TestCase):
    def test_analysis_runs_between_sources_not_only_after_the_entire_sweep(self):
        sources = [Source.objects.create(name=str(n), entry_url=f"https://example.org/{n}") for n in range(2)]
        events = []
        def collect(source):
            events.append(("collect", source.pk))
            return {}
        def analyze(max_calls=None):
            events.append(("analyze", max_calls))
        with mock.patch("collection.management.commands.collect_sources.due_sources", return_value=sources), \
             mock.patch("collection.management.commands.collect_sources.run_source", side_effect=collect), \
             mock.patch("collection.sourcefinder.maybe_run_discovery", return_value=None), \
             mock.patch("analysis.retention.maybe_cleanup", return_value=None), \
             mock.patch("analysis.service.analyze_pending", side_effect=analyze):
            call_command("collect_sources", once=True, stdout=__import__("io").StringIO())
        self.assertEqual(events, [("collect", sources[0].pk), ("analyze", settings.LLM["CALLS_PER_SOURCE"]),
                                  ("collect", sources[1].pk), ("analyze", settings.LLM["CALLS_PER_SOURCE"]),
                                  ("analyze", None)])
