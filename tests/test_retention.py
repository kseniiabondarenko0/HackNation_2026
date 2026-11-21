"""Storage policy (analysis.retention): only current, promising items stay; the rest leaves without a dump of rejects."""
import gzip
import json
import sqlite3
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analysis import retention
from analysis.models import Analysis
from analysis.tabs import TABS, tab_q
from collection import archive
from collection.extract import content_hash
from collection.models import Article, Rejected, Source, Submission
from collection.netsafe import FetchError

BODY = "<p>" + "Szkoła wdrożyła system oceny prac, który skrócił czas sprawdzania o 40 procent w trzech klasach. " * 6 + "</p>"


def page(published=None):
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    return f"<html><head><title>T</title>{meta}</head><body><article><h1>T</h1>{BODY}</article></body></html>"


def days_ago(n):
    return timezone.now() - timedelta(days=n)


class RetentionBase(TestCase):
    def setUp(self):
        self.src = Source.objects.create(name="Z", entry_url="https://example.pl/")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patcher in (override_settings(ARCHIVE_DIR=Path(self.tmp.name),
                                          ANALYSIS={**settings.ANALYSIS, "BACKEND": "ai", "WINDOW_MONTHS": 8}),):
            patcher.enable()
            self.addCleanup(patcher.disable)
        self.n = 0

    def mk(self, hours=1, published="recent", status="fetched", verdict=None, backend="ai", score=70, handling="brak", **kw):
        self.n += 1
        pub = days_ago(10) if published == "recent" else published
        a = Article.objects.create(source=self.src, original_url=f"https://example.pl/a/{self.n}", title=f"Tytuł {self.n}",
                                   text=f"Treść {self.n}. " * 40, content_hash=content_hash(f"t{self.n}"), status=status,
                                   published_at=pub, **kw)
        Article.objects.filter(pk=a.pk).update(first_seen_at=timezone.now() - timedelta(hours=hours))
        if verdict:
            data = {"ai": {"is_initiative": verdict != "odrzucone", "score": score, "credibility": "wysoka",
                           "explanation": "Opis"},
                    "verified": {"quotes": ["System skrócił czas oceny o 40 procent."]},
                    "verdict": {"id": verdict, "label": TABS.get(verdict, ""), "reason": "Powód"}}
            Analysis.objects.create(article=a, input_key="k", backend=backend, data=data, potential=score,
                                    verdict=verdict, handling=handling)
        return Article.objects.get(pk=a.pk)

    def gone(self, a):
        return not Article.objects.filter(pk=a.pk).exists()


class AiRejectedAndOldTests(RetentionBase):
    def test_ai_rejected_is_deleted_and_leaves_only_url_and_hash(self):
        a = self.mk(verdict="odrzucone", score=30)
        stats = retention.cleanup()
        self.assertTrue(self.gone(a))
        self.assertEqual(Analysis.objects.count(), 0)
        t = Rejected.objects.get(url=a.original_url)
        self.assertEqual((t.content_hash, t.score), (a.content_hash, 30))
        self.assertEqual(stats["rejected"], 1)

    def test_interesting_and_fresh_queue_items_stay(self):
        good, waiting, unanalysed = self.mk(verdict="glowna", hours=500), self.mk(verdict="weryfikacja"), self.mk()
        retention.cleanup()
        for a in (good, waiting, unanalysed):
            self.assertFalse(self.gone(a))

    def test_older_than_window_is_archived_first_then_removed(self):
        a = self.mk(published=days_ago(300), verdict="glowna")
        retention.cleanup()
        self.assertTrue(self.gone(a))
        self.assertTrue(Rejected.objects.filter(url=a.original_url).exists())
        with gzip.open(archive.path(), "rb") as fh:
            rows = [json.loads(line) for line in fh.read().splitlines()]
        self.assertEqual([r["url"] for r in rows], [a.original_url])
        self.assertEqual(rows[0]["analysis"]["verdict"], "glowna")

    def test_failed_archive_write_deletes_nothing(self):
        blocker = Path(self.tmp.name) / "plik"
        blocker.write_text("x")
        a = self.mk(published=days_ago(300))
        with override_settings(ARCHIVE_DIR=blocker / "sub"):
            stats = retention.cleanup()
        self.assertFalse(self.gone(a))
        self.assertEqual(stats["errors"], 1)

    def test_archive_is_bounded(self):
        with override_settings(RETENTION={**settings.RETENTION, "ARCHIVE_MAX_RECORDS": 3}):
            for _ in range(5):
                archive.append([self.mk(published=days_ago(300))], "test")
        with gzip.open(archive.path(), "rb") as fh:
            self.assertEqual(len(fh.read().splitlines()), 3)

    def test_unknown_date_is_not_treated_as_old(self):
        a = self.mk(published=None, verdict="weryfikacja")
        retention.cleanup()
        self.assertFalse(self.gone(a))


class JunkTests(RetentionBase):
    def test_duplicate_is_deleted_without_blocking_the_original(self):
        original = self.mk(verdict="glowna")
        dup = self.mk(duplicate_of=original)
        retention.cleanup()
        self.assertTrue(self.gone(dup))
        self.assertFalse(self.gone(original))
        self.assertEqual(Rejected.objects.get(url=dup.original_url).content_hash, "")

    def test_skipped_and_exhausted_errors_are_removed_young_errors_wait(self):
        skipped = self.mk(status="skipped")
        dead = self.mk(status="error", fetch_attempts=settings.COLLECT["MAX_ATTEMPTS"])
        young = self.mk(status="error", fetch_attempts=1)
        retention.cleanup()
        self.assertTrue(self.gone(skipped) and self.gone(dead))
        self.assertFalse(self.gone(young))

    def test_submission_is_protected_for_a_while_then_removed_without_trace(self):
        a = self.mk(verdict="odrzucone", score=20, published=days_ago(300))
        Submission.objects.create(article=a, consent=False)
        retention.cleanup()
        self.assertFalse(self.gone(a))                       # the submitter can still read the result
        Article.objects.filter(pk=a.pk).update(first_seen_at=timezone.now() - timedelta(hours=60))
        retention.cleanup()
        self.assertTrue(self.gone(a))
        self.assertFalse(Rejected.objects.filter(url=a.original_url).exists())
        self.assertEqual(Submission.objects.count(), 0)


class QueueTests(RetentionBase):
    def test_unconfirmed_items_expire_after_ttl(self):
        old = self.mk(hours=50)
        fresh = self.mk(hours=5)
        kept = self.mk(hours=50, verdict="glowna")
        stats = retention.cleanup()
        self.assertTrue(self.gone(old))
        self.assertFalse(self.gone(fresh) or self.gone(kept))
        self.assertIn("Niepotwierdzone", Rejected.objects.get(url=old.original_url).reason)
        self.assertEqual(stats["expired"], 1)

    def test_links_that_were_never_fetched_expire_without_trace(self):
        stale = self.mk(hours=60, status="found", published=None)
        retention.cleanup()
        self.assertTrue(self.gone(stale))
        self.assertEqual(Rejected.objects.count(), 0)

    def test_queue_is_bounded_newest_first(self):
        with override_settings(RETENTION={**settings.RETENTION, "QUEUE_MAX": 2}):
            items = [self.mk(published=days_ago(d)) for d in (30, 20, 10, 5)]
            stats = retention.cleanup()
        self.assertEqual([self.gone(a) for a in items], [True, True, False, False])
        self.assertEqual(stats["evicted"], 2)

    def test_found_links_are_bounded(self):
        with override_settings(RETENTION={**settings.RETENTION, "FOUND_MAX": 2}):
            for h in (1, 2, 3, 4):
                self.mk(hours=h, status="found", published=None)
            retention.cleanup()
        self.assertEqual(Article.objects.filter(status="found").count(), 2)

    def test_registry_expires_and_is_capped(self):
        for i in range(4):
            Rejected.objects.create(url=f"https://example.pl/r/{i}", reason="x")
        Rejected.objects.filter(url="https://example.pl/r/0").update(rejected_at=days_ago(400))
        with override_settings(RETENTION={**settings.RETENTION, "TOMBSTONE_MAX": 2}):
            stats = retention.cleanup()
        self.assertEqual(Rejected.objects.count(), 2)
        self.assertEqual(stats["tombstones_dropped"], 2)


class UnknownDateTests(RetentionBase):
    """An undated item is not removed before its date was looked up in the primary source."""
    def undated(self, **kw):
        return self.mk(hours=50, published=None, verdict="weryfikacja", score=80, **kw)

    def test_recent_date_found_in_source_promotes_without_ai_call(self):
        a = self.undated()
        calls = []
        getter = lambda url: (calls.append(url) or (url, page(days_ago(10).isoformat())))
        stats = retention.cleanup(getter=getter)
        a.refresh_from_db()
        self.assertEqual((calls[:1], stats["date_resolved"]), ([a.original_url], 1))
        self.assertEqual((a.analysis.verdict, a.analysis.backend), ("glowna", "ai"))
        self.assertIsNotNone(a.published_at)

    def test_old_date_found_in_source_archives_and_removes(self):
        a = self.undated()
        retention.cleanup(getter=lambda url: (url, page(days_ago(300).isoformat())))
        self.assertTrue(self.gone(a))
        with gzip.open(archive.path(), "rb") as fh:
            self.assertEqual(json.loads(fh.read().splitlines()[0])["url"], a.original_url)

    def test_no_date_in_source_expires_after_one_successful_check(self):
        a = self.undated()
        calls = []
        retention.cleanup(getter=lambda url: (calls.append(1) or (url, page())))
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.gone(a))

    def test_fetch_errors_are_retried_then_the_item_expires(self):
        a = self.undated()

        def boom(url):
            raise FetchError("http_503")
        for _ in range(settings.RETENTION["DATE_CHECKS"]):
            retention.cleanup(getter=boom)
            self.assertFalse(self.gone(a))                   # failed lookup: keep, check again next cycle
        retention.cleanup(getter=boom)
        self.assertTrue(self.gone(a))                        # DATE_CHECKS exhausted

    def test_redecide_uses_stored_answer_only(self):
        a = self.undated()
        Article.objects.filter(pk=a.pk).update(published_at=days_ago(300))
        v = retention.redecide(Article.objects.get(pk=a.pk))
        self.assertEqual((v["id"], v.get("window")), ("odrzucone", True))
        b = self.mk(verdict="weryfikacja", backend="rules")
        self.assertIsNone(retention.redecide(b))


class LegacyTests(RetentionBase):
    def test_rule_based_verdicts_become_queue_items_and_rejects_go(self):
        was_main = self.mk(verdict="glowna", backend="rules")
        was_rejected = self.mk(verdict="odrzucone", backend="rules")
        handled = self.mk(verdict="glowna", backend="rules", handling="kontakt")
        retention.cleanup()
        was_main.refresh_from_db()
        self.assertFalse(hasattr(was_main, "analysis") and Analysis.objects.filter(article=was_main).exists())
        self.assertIn(was_main, Article.objects.filter(tab_q("weryfikacja")))
        self.assertTrue(self.gone(was_rejected))
        self.assertTrue(Analysis.objects.filter(article=handled).exists())   # work in progress is never dropped

    def test_rules_backend_keeps_its_analyses(self):
        a = self.mk(verdict="glowna", backend="rules")
        with override_settings(ANALYSIS={**settings.ANALYSIS, "BACKEND": "rules"}):
            retention.cleanup()
        self.assertTrue(Analysis.objects.filter(article=a).exists())


class DryRunAndBackupTests(RetentionBase):
    def test_dry_run_reports_but_changes_nothing(self):
        self.mk(verdict="odrzucone", score=10)
        self.mk(hours=80)
        old = self.mk(published=days_ago(300))
        stats = retention.cleanup(dry=True)
        self.assertEqual((stats["rejected"], stats["expired"], stats["old"]), (1, 1, 1))
        self.assertEqual((Article.objects.count(), Rejected.objects.count()), (3, 0))
        self.assertFalse(archive.path().exists())
        self.assertFalse(self.gone(old))

    def test_backup_file_is_a_valid_copy_throttled_and_rotated(self):
        db = Path(self.tmp.name) / "live.sqlite3"
        con = sqlite3.connect(db)
        con.execute("create table t(x)")
        con.execute("insert into t values (42)")
        con.commit()
        con.close()
        folder = retention.backup_dir()
        folder.mkdir(parents=True)
        for stamp in ("20200101_000000", "20200102_000000"):
            (folder / f"db_{stamp}.sqlite3").write_bytes(b"old")
        with mock.patch.dict(connection.settings_dict, {"NAME": str(db)}):
            path = retention.backup_db(force=True)
            self.assertEqual(sqlite3.connect(path).execute("select x from t").fetchall(), [(42,)])
            self.assertEqual(len(list(folder.glob("db_*.sqlite3"))), settings.RETENTION["BACKUP_KEEP"])
            self.assertEqual(retention.backup_db(), path)       # within BACKUP_EVERY_HOURS: no new file

    def test_memory_database_is_not_backed_up(self):
        self.assertIsNone(retention.backup_db(force=True))

    def test_failed_backup_stops_the_command_before_any_deletion(self):
        a = self.mk(verdict="odrzucone", score=10)
        with mock.patch("analysis.management.commands.cleanup_storage.backup_db", side_effect=OSError("disk full")):
            with self.assertRaises(CommandError):
                call_command("cleanup_storage", "--apply", stdout=StringIO())
        self.assertFalse(self.gone(a))


class CommandAndCounterTests(RetentionBase):
    def test_command_is_a_dry_run_by_default_and_applies_with_flag(self):
        a = self.mk(verdict="odrzucone", score=10)
        out = StringIO()
        call_command("cleanup_storage", stdout=out)
        self.assertFalse(self.gone(a))
        self.assertIn("Dodaj --apply", out.getvalue())
        with mock.patch("analysis.management.commands.cleanup_storage.backup_db", return_value=Path("/tmp/kopia")) as b:
            call_command("cleanup_storage", "--apply", "--no-vacuum", stdout=out)
        b.assert_called_once_with(force=True)
        self.assertTrue(self.gone(a))

    def test_restart_queue_clock_spares_confirmed_items(self):
        waiting, good = self.mk(hours=100), self.mk(hours=100, verdict="glowna")
        call_command("cleanup_storage", "--apply", "--restart-queue-clock", "--no-vacuum", stdout=StringIO())
        self.assertFalse(self.gone(waiting))                    # clock restarted -> not expired
        waiting.refresh_from_db(); good.refresh_from_db()
        self.assertLess(timezone.now() - waiting.first_seen_at, timedelta(hours=1))
        self.assertGreater(timezone.now() - good.first_seen_at, timedelta(hours=90))

    def test_counts_equal_what_the_tabs_list(self):
        self.mk(verdict="glowna"); self.mk(verdict="glowna"); self.mk(verdict="weryfikacja"); self.mk(); self.mk(hours=70)
        retention.cleanup()
        c = retention.counts()
        tabs = {k: self.client.get(reverse("radar"), {"widok": k}).context["total"] for k in TABS}
        self.assertEqual((c["interesujace"], c["do_weryfikacji"], c["wszystkie"]),
                         (tabs["glowna"], tabs["weryfikacja"], tabs["wszystkie"]))
        self.assertEqual((tabs["glowna"], tabs["weryfikacja"], tabs["wszystkie"]), (2, 2, 3))
        self.assertEqual(self.client.get(reverse("overview")).context["total"], tabs["glowna"])

    def test_maybe_cleanup_throttle(self):
        with mock.patch.object(retention, "cleanup", return_value={}) as run:
            retention._last_run[0] = float("-inf")             # not 0.0: time.monotonic() can be tiny on a freshly booted machine
            retention.maybe_cleanup()
            retention.maybe_cleanup()
            self.assertEqual(run.call_count, 1)
            retention.maybe_cleanup(ran_sources=True)           # a cycle that collected something always cleans
            self.assertEqual(run.call_count, 2)

    def test_collection_cycle_runs_the_cleanup(self):
        with mock.patch("analysis.retention.maybe_cleanup", return_value={"old": 0}) as hook, \
                mock.patch("analysis.service.analyze_pending"), \
                mock.patch("collection.sourcefinder.maybe_run_discovery", return_value=None):   # no real network in tests
            call_command("collect_sources", "--once", stdout=StringIO())
        hook.assert_called_once()
