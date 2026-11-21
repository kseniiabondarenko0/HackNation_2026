"""Demonstration set: real AI-confirmed publications exported from a database and loaded into a clean one."""
import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analysis import demo, retention
from analysis.core import verify_quote
from analysis.models import Analysis
from analysis.service import analyze_pending
from analysis.tabs import TABS
from collection.extract import content_hash
from collection.models import Article, Rejected, Source

QUOTE = "System został wdrożony w trzech szkołach i skrócił czas oceny o 40 procent."
LONG = ("Politechnika Testowa opracowała system oceny prac. " * 30) + QUOTE + " Wyniki opisano w raporcie."
PAGE = "<html><body><article><h1>T</h1><p>" + LONG + "</p></article></body></html>"


def ai_data(score=80, authors=("Jan Kowalski",), quote=QUOTE):
    return {"sector": "Edukacja", "stage": "in_use", "stage_label": "w użyciu", "potential": score, "completeness": 60,
            "authors": list(authors), "signal": "wysoki", "signal_label": "wysokie", "path": {"id": "transfer", "label": "Transfer"},
            "verdict": {"id": "glowna", "label": "Interesujące", "reason": f"Potwierdzona; ocena {score}/100."},
            "region": {"code": "podkarpackie", "how": "z tekstu"}, "priority": 1, "priority_reasons": [],
            "verified": {"url": "https://x", "source": "Politechnika", "published_at": "2026-11-10", "date_source": "metadane strony",
                         "quotes": [quote]},
            "ai": {"provider": "gemini", "model": "m", "is_initiative": True, "score": score, "credibility": "wysoka",
                   "summary": "System oceny prac.", "explanation": "Opisano wdrożenie i wynik.", "authors": list(authors)}}


class DemoBase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "demo.json"
        for p in (override_settings(ARCHIVE_DIR=Path(self.tmp.name), ANALYSIS={**settings.ANALYSIS, "BACKEND": "ai", "WINDOW_MONTHS": 8}),):
            p.enable()
            self.addCleanup(p.disable)
        self.src = Source.objects.create(name="Politechnika Testowa", entry_url="https://pt.example.pl/aktualnosci/",
                                         organization_type="university", region="podkarpackie", status="active", origin="registry")

    def mk(self, n, score=80, backend="ai", verdict="glowna", days=10, source=None, status="fetched", text=LONG, **kw):
        a = Article.objects.create(source=source or self.src, original_url=kw.pop("original_url", f"https://pt.example.pl/a/{n}"), title=f"Innowacja szkolna numer {n}",
                                   text=text, content_hash=content_hash(f"{n}{text}"), status=status,
                                   published_at=timezone.now() - timedelta(days=days), **kw)
        Analysis.objects.create(article=a, input_key="k", backend=backend, data=ai_data(score), potential=score, completeness=60,
                                path="transfer", signal="wysoki", sector="Edukacja", stage="in_use", verdict=verdict, priority=1,
                                region="podkarpackie")
        return a

    def export_to_file(self, **kw):
        items = demo.export_items(check_links=False, **kw)
        self.file.write_text(json.dumps(demo.build_payload(items), ensure_ascii=False), encoding="utf-8")
        return items

    def wipe(self):
        Article.objects.all().delete()
        Source.objects.all().delete()


class ExportTests(DemoBase):
    def test_only_real_confirmed_current_items_without_personal_data(self):
        good = self.mk(1)
        self.mk(2, backend="rules")                                   # not an AI answer
        self.mk(3, verdict="weryfikacja")                             # not confirmed
        self.mk(4, days=400)                                          # outside the 8-month window
        off = Source.objects.create(name="Wyłączone", entry_url="https://off.example.pl/", status="candidate")
        self.mk(5, source=off)                                        # source not monitored
        self.mk(6, original_url="https://pt.example.pl/aktualnosci/page-1")       # index page, not a publication
        short = self.mk(7)
        Article.objects.filter(pk=short.pk).update(title="Program")                # no real headline
        items = demo.export_items(check_links=False)
        self.assertEqual([i["url"] for i in items], [good.original_url])
        item = items[0]
        self.assertEqual(item["analysis"]["data"]["authors"], [])      # no author names
        self.assertEqual(item["analysis"]["data"]["ai"]["authors"], [])
        self.assertEqual((item["title"], item["source"]["name"], item["analysis"]["data"]["ai"]["score"]),
                         ("Innowacja szkolna numer 1", "Politechnika Testowa", 80))
        self.assertEqual((item["url"], item["final_url"]), (good.original_url, good.original_url))
        self.assertTrue(all(verify_quote(item["excerpt"], q) for q in item["analysis"]["data"]["verified"]["quotes"]))
        self.assertLess(len(item["excerpt"]), 1200)                    # an excerpt, not the full text
        self.assertEqual(demo.check_clean(demo.build_payload(items)), [])

    def test_dead_links_and_per_source_cap(self):
        for n in (1, 2, 3):
            self.mk(n, score=90 - n)
        self.assertEqual(len(demo.export_items(per_source=2, check_links=False)), 2)
        calls = []

        def getter(url):
            calls.append(url)
            if url.endswith("/1"):
                raise OSError("404")
            return url, PAGE
        report = {}
        items = demo.export_items(getter=getter, report=report)
        self.assertEqual(sorted(i["url"][-1] for i in items), ["2", "3"])
        self.assertEqual(report["dead"], 1)

    def test_loaded_demo_items_are_not_exported_again(self):
        self.mk(1)
        self.export_to_file()
        self.wipe()
        demo.load(self.file)
        self.assertEqual(demo.export_items(check_links=False), [])

    def test_check_clean_flags_email_phone_and_keys(self):
        for bad in ("pisz: jan.kowalski@uczelnia.pl", "tel. 17 865 43 21 00", "klucz " + "AI" + "zaSy" + "A" * 33):
            self.assertTrue(demo.check_clean({"x": bad}), bad)
        self.assertEqual(demo.check_clean({"x": "Wartość 0,5 mld zł w 2026 roku (731 mln euro)"}), [])

    def test_export_command_writes_file_and_refuses_personal_data(self):
        self.mk(1)
        out = StringIO()
        call_command("export_demo", "--no-check-links", "--out", str(self.file), stdout=out)
        self.assertEqual(len(json.loads(self.file.read_text())["items"]), 1)
        a = Article.objects.get()
        a.text += " Kontakt: jan.kowalski@uczelnia.pl"
        a.save()
        Analysis.objects.filter(article=a).update(data={**ai_data(), "caveat": "pisz: jan.kowalski@uczelnia.pl"})
        self.file.unlink()
        with self.assertRaises(CommandError):
            call_command("export_demo", "--no-check-links", "--out", str(self.file), stdout=out)
        self.assertFalse(self.file.exists())


class LoadTests(DemoBase):
    def setUp(self):
        super().setUp()
        self.n = 4
        for n in range(1, self.n + 1):
            self.mk(n, score=90 - n)
        self.export_to_file()
        self.wipe()

    def tabs(self):
        return {k: self.client.get(reverse("radar"), {"widok": k}).context["total"] for k in TABS}

    def test_clean_install_shows_demo_at_once_with_correct_counters(self):
        r = demo.load(self.file)
        self.assertEqual((r["added"], r["sources_created"], r["refused"]), (self.n, 1, False))
        self.assertEqual(self.tabs(), {"glowna": self.n, "weryfikacja": 0, "wszystkie": self.n})
        c = retention.counts()
        self.assertEqual((c["interesujace"], c["do_weryfikacji"], c["wszystkie"]), (self.n, 0, self.n))
        self.assertEqual(self.client.get(reverse("overview")).context["total"], self.n)
        self.assertEqual(demo.loaded_count(), self.n)
        listing = self.client.get(reverse("radar")).content.decode()
        self.assertIn("Demo · wstępna ocena AI", listing)
        self.assertIn("wstępne", listing)
        self.assertIn("zestawu demonstracyjnego", self.client.get(reverse("overview")).content.decode())
        a = Article.objects.get(original_url="https://pt.example.pl/a/1")
        page = self.client.get(reverse("detail", args=[a.pk])).content.decode()
        for needle in ("Zestaw demonstracyjny", "wstępna", "Fragment tekstu", "Opisano wdrożenie i wynik."):
            self.assertIn(needle, page)
        self.assertEqual((a.title, a.source.name, a.analysis.potential, a.analysis.backend), ("Innowacja szkolna numer 1", "Politechnika Testowa", 89, "ai"))

    def test_second_run_adds_nothing(self):
        demo.load(self.file)
        before = (Article.objects.count(), Analysis.objects.count(), Source.objects.count())
        r = demo.load(self.file)
        self.assertEqual((r["added"], r["existing"]), (0, self.n))
        self.assertEqual((Article.objects.count(), Analysis.objects.count(), Source.objects.count()), before)
        call_command("load_demo", "--file", str(self.file), stdout=StringIO())
        self.assertEqual(Article.objects.count(), self.n)

    def test_filled_base_is_left_alone_unless_forced_and_never_overwritten(self):
        own_src = Source.objects.create(name="Własne", entry_url="https://wlasne.example.pl/")
        own = Article.objects.create(source=own_src, original_url="https://wlasne.example.pl/x", title="Własny", text="tekst",
                                     content_hash=content_hash("tekst"), status="fetched")
        r = demo.load(self.file)
        self.assertEqual((r["refused"], r["added"], Article.objects.count()), (True, 0, 1))
        twin = Article.objects.create(source=own_src, original_url="https://pt.example.pl/a/1", title="Prawdziwy rekord", text="moje",
                                      content_hash=content_hash("moje"), status="fetched")
        r = demo.load(self.file, force=True)
        self.assertEqual((r["refused"], r["added"], r["existing"]), (False, self.n - 1, 1))
        twin.refresh_from_db()
        self.assertEqual((twin.title, twin.text, hasattr(twin, "analysis")), ("Prawdziwy rekord", "moje", False))
        own.refresh_from_db()
        self.assertEqual(own.title, "Własny")
        out = StringIO()
        call_command("load_demo", "--file", str(self.file), stdout=out)
        self.assertIn("pominięty", out.getvalue())

    def test_removed_and_too_old_items_are_not_brought_back(self):
        Rejected.objects.create(url="https://pt.example.pl/a/1", reason="usunięte")
        payload = json.loads(self.file.read_text())
        payload["items"][1]["published_at"] = (timezone.localdate() - timedelta(days=400)).isoformat()
        self.file.write_text(json.dumps(payload))
        r = demo.load(self.file)
        self.assertEqual((r["added"], r["tombstoned"], r["too_old"]), (self.n - 2, 1, 1))

    def test_dry_run_changes_nothing(self):
        r = demo.load(self.file, dry=True)
        self.assertEqual((r["added"], Article.objects.count(), Source.objects.count()), (self.n, 0, 0))

    def test_existing_source_is_reused(self):
        Source.objects.create(name="Politechnika Testowa", entry_url="https://pt.example.pl/aktualnosci/", status="active")
        r = demo.load(self.file)
        self.assertEqual((r["sources_created"], Source.objects.count()), (0, 1))

    def test_ai_analysis_is_not_repeated_or_replaced(self):
        demo.load(self.file)
        with mock.patch("analysis.llm.chain", return_value=[object()]), mock.patch("analysis.llm.remaining_calls", return_value=10), \
                mock.patch("analysis.ai.analyze", side_effect=AssertionError("AI call for a demo item")):
            self.assertEqual(analyze_pending("ai"), 0)
        with override_settings(ANALYSIS={**settings.ANALYSIS, "BACKEND": "rules"}):
            analyze_pending()                                          # offline mode must not downgrade AI answers
            analyze_pending("rules", force=False)
        self.assertEqual(set(Analysis.objects.values_list("backend", flat=True)), {"ai"})
        self.assertEqual(demo.loaded_count(), self.n)

    def test_storage_policy_keeps_demo_items_and_collection_adds_alongside(self):
        demo.load(self.file)
        retention.cleanup()
        self.assertEqual(Article.objects.count(), self.n)
        fresh = Article.objects.create(source=Source.objects.get(), original_url="https://pt.example.pl/new", title="Nowy",
                                       text=LONG + " nowy", content_hash=content_hash("nowy"), status="fetched")
        self.assertEqual(self.tabs(), {"glowna": self.n, "weryfikacja": 1, "wszystkie": self.n})
        self.assertIn(fresh, Article.objects.filter(analysis__isnull=True))

    def test_command_reports_and_rejects_a_broken_file(self):
        out = StringIO()
        call_command("load_demo", "--file", str(self.file), "--dry-run", stdout=out)
        self.assertIn(f"dodano {self.n}", out.getvalue())
        self.assertEqual(Article.objects.count(), 0)
        self.file.write_text("{}")
        with self.assertRaises(CommandError):
            call_command("load_demo", "--file", str(self.file), stdout=out)


class ShippedFileTests(TestCase):
    """analysis/data/demo_innovations.json is what a committee sees on a clean installation."""
    def test_file_is_valid_real_and_clean(self):
        payload = demo.read()
        items = payload["items"]
        self.assertGreaterEqual(len(items), 20)
        self.assertLessEqual(len(items), 30)
        self.assertEqual(demo.check_clean(payload), [])
        self.assertIn("wstępne", payload["note"])
        self.assertEqual(len({i["url"] for i in items}), len(items))
        for i in items:
            self.assertTrue(i["url"].startswith("https://"), i["url"])
            data = i["analysis"]["data"]
            self.assertEqual((data["authors"], data["verdict"]["id"]), ([], "glowna"))
            self.assertTrue(data["verified"]["quotes"])
            self.assertTrue(all(verify_quote(i["excerpt"], q) for q in data["verified"]["quotes"]), i["url"])
            self.assertGreaterEqual(data["ai"]["score"], 50)
            self.assertTrue(i["source"]["name"] and i["source"]["entry_url"].startswith("http"))

    def test_loads_into_an_empty_database_with_matching_counters(self):
        n = len(demo.read()["items"])
        with mock.patch("analysis.demo.is_old", return_value=False):   # the file ages; the content does not matter here
            r = demo.load()
        self.assertEqual((r["added"], r["refused"]), (n, False))
        self.assertEqual(retention.counts()["interesujace"], n)
        self.assertEqual(self.client.get(reverse("radar")).context["total"], min(n, 10 ** 6))
        self.assertEqual(demo.load()["added"], 0)
