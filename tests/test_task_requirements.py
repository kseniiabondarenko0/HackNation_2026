"""Requirements from the task text that are not covered elsewhere: section 7 databases, integration export,
demo scenario on two use cases."""
import io
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from analysis.examples import EXAMPLES
from analysis.external import external_search
from analysis.service import analyze_pending
from collection.extract import content_hash
from collection.models import Article, Source


class ExternalDatabasesTests(TestCase):
    def test_all_task_databases_linked_with_keywords(self):
        r = external_search("Czujnik wykrywa sepsę w kilka minut")
        self.assertEqual(r["query"], "Czujnik wykrywa sepsę kilka minut")
        urls = " ".join(l["url"] for l in r["links"])
        for host in ("ewyszukiwarka.pue.uprp.gov.pl", "register.epo.org", "pbn.nauka.gov.pl", "ppm.edu.pl",
                     "czasopisma.pan.pl", "interreg.gov.pl", "wyszukiwarka-sukcesow-beneficjentow"):
            self.assertIn(host, urls)
        self.assertIn("q=Czujnik+wykrywa", urls)


class ExportAndDetailTests(TestCase):
    def setUp(self):
        src = Source.objects.create(name="T", entry_url="https://example.org/n/")
        for n, i in enumerate(("gmina-decyzje", "dozynki")):
            e = next(x for x in EXAMPLES if x["id"] == i)
            Article.objects.create(source=src, original_url=f"https://example.org/n/{n}", title=e["title"],
                                   text=e["text"], content_hash=content_hash(e["text"]), status="fetched")
        analyze_pending()

    def test_json_export_main_list_without_personal_data(self):
        r = self.client.get(reverse("export", args=["json"])).json()
        self.assertEqual([x["tytul"] for x in r["results"]], ["Gmina skróciła czas wydawania decyzji"])
        self.assertEqual(r["results"][0]["typ_innowacji"], "organizacyjna, procesowa")
        self.assertNotIn("autorzy", r["fields"])
        all_rows = self.client.get(reverse("export", args=["json"]), {"widok": "wszystkie"}).json()
        self.assertEqual(all_rows["count"], 2)

    def test_csv_export(self):
        r = self.client.get(reverse("export", args=["csv"]))
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("tytul;url;zrodlo", r.content.decode("utf-8-sig"))

    def test_detail_shows_databases_and_type(self):
        a = Article.objects.get(title__startswith="Gmina")
        r = self.client.get(reverse("detail", args=[a.pk]))
        self.assertContains(r, "Sprawdź w bazach zewnętrznych")
        self.assertContains(r, "Typ innowacji: organizacyjna")

    def test_about_mentions_rodo(self):
        self.assertContains(self.client.get(reverse("about")), "RODO")


class DemoScenarioTests(TestCase):
    def test_two_use_cases_a_to_e(self):
        out = io.StringIO()
        call_command("demo_cases", stdout=out)
        text = out.getvalue()
        self.assertEqual(text.count("PRZYPADEK"), 2)
        for step in ("a) ", "b) ", "c) ", "d) ", "e) "):
            self.assertEqual(text.count(step), 2, step)
        self.assertIn("Ścieżka: Komercjalizacja", text)
        self.assertIn("Ścieżka: Transfer", text)
        self.assertEqual(Article.objects.count(), 2)
        call_command("demo_cases", stdout=io.StringIO())  # idempotent
        self.assertEqual(Article.objects.count(), 2)
