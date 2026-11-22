"""Catalog search must not care about case or Polish diacritics (SQLite LIKE only folds ASCII)."""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from analysis.search import fold
from collection.extract import content_hash
from collection.models import Article, Source


class FoldTests(SimpleTestCase):
    def test_polish_letters_and_case(self):
        self.assertEqual(fold("Łódź ŻYWNOŚĆ Gęślą jaźń Ćma"), "lodz zywnosc gesla jazn cma")
        self.assertEqual(fold(None), "")


class CatalogSearchTests(TestCase):
    def setUp(self):
        src = Source.objects.create(name="Z", entry_url="https://example.pl/")
        for i, (title, text) in enumerate([("Żywność z Łodzi", "Projekt dotyczy żywności."),
                                           ("Dron nad Rzeszowem", "Inspekcja linii energetycznych.")]):
            Article.objects.create(source=src, original_url=f"https://example.pl/{i}", title=title, text=text * 5,
                                   content_hash=content_hash(title), status="fetched")

    def titles(self, q):
        return sorted(a.title for a in self.client.get(reverse("radar"), {"q": q, "widok": "weryfikacja"}).context["articles"])

    def test_upper_lower_and_diacritics_find_the_same_article(self):
        for q in ("żywność", "ŻYWNOŚĆ", "zywnosc", "Łodzi", "łodzi", "LODZI"):
            self.assertEqual(self.titles(q), ["Żywność z Łodzi"], q)

    def test_no_match_and_empty_query(self):
        self.assertEqual(self.titles("kosmonauta"), [])
        self.assertEqual(len(self.titles("")), 2)
