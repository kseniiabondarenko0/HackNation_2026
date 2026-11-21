from pathlib import Path
from unittest import mock
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from analysis.core import finalize, verify_quote, choose_path
from analysis.models import Analysis
from analysis.rules import analyze
from analysis.service import analyze_article, analyze_pending
from collection.extract import content_hash
from collection.models import Article, Source

BASE = ("Naukowcy z Politechniki opracowali innowacyjny prototyp betonu z odpadów PET. "
        "Celem projektu jest rozwiązanie problemu składowania odpadów tworzyw sztucznych. "
        "Prototyp został przetestowany w laboratorium, a wyniki pokazują redukcję emisji o 20%. "
        "Wytrzymałość wzrosła o 15%, a koszt produkcji spadł o 10%. "
        "Rozwiązanie jest skalowalne i może trafić do innych miast. "
        "Technologię można upowszechnić wśród partnerów przemysłowych. "
        "Autorem pomysłu jest dr Jan Kowalski z Wydziału Budownictwa.")
MARKET = " Technologia jest objęta zgłoszeniem patentowym, a zainteresowali się nią klienci z branży budowlanej."


def run(text):
    return finalize(analyze(text), text)


def crit(d, key):
    return next(c for c in d["criteria"] if c["key"] == key)


class QuoteTests(TestCase):
    def test_verify_quote_normalizes_whitespace_and_case(self):
        self.assertTrue(verify_quote("Ala  ma\nkota i bardzo lubi psy.", "ala ma kota i bardzo lubi"))

    def test_rejects_fabricated_or_short_quote(self):
        self.assertFalse(verify_quote("Ala ma kota i bardzo lubi psy.", "Ala ma psa i lubi koty"))
        self.assertFalse(verify_quote("Ala ma kota.", "Ala ma"))
        self.assertFalse(verify_quote("Ala ma kota i bardzo lubi psy.", ""))

    def test_finalize_drops_score_with_unverified_quote(self):
        raw = {"criteria": {"dowody": {"score": 3, "quote": "Tego zdania nie ma w tekście artykułu."}},
               "stage": "pilot", "authors": ["dr Wymyślony"], "signal_terms": ["blockchain"]}
        d = finalize(raw, "Zupełnie inny tekst o czymś innym, bez żadnych wynalazków.")
        self.assertIsNone(crit(d, "dowody")["score"])
        self.assertEqual(d["dropped"], ["Dowody"])
        self.assertEqual((d["authors"], d["signal_terms"], d["potential"]), ([], [], None))


class RulesTests(TestCase):
    def test_rubric_stage_and_quotes_come_from_text(self):
        d = run(BASE)
        self.assertEqual(d["stage"], "pilot")
        self.assertEqual(d["sector"], "Energia i środowisko")  # odpady/emisje outweigh beton/budowa
        self.assertEqual(d["authors"], ["dr Jan Kowalski"])
        self.assertEqual([crit(d, k)["score"] for k in ("problem", "dowody", "wyniki", "przenosnosc", "gotowosc")],
                         [1, 1, 2, 2, 2])
        for c in d["criteria"]:
            self.assertTrue(verify_quote(BASE, c["quote"]), c)
        self.assertEqual(d["completeness"], 100)
        self.assertEqual(d["potential"], 52)  # weights 1,2,2,1,1 -> (1+2+4+2+2)*100/(3*7)

    def test_sector_materials_for_construction_text(self):
        d = run("Nowy beton konstrukcyjny z dodatkiem kompozytu poprawia trwałość budowli mostowych.")
        self.assertEqual(d["sector"], "Materiały i budownictwo")

    def test_potential_uses_only_known_criteria(self):
        text = "Szkoła zorganizowała dzień otwarty dla uczniów i rodziców w sobotę rano."
        d = run(text)
        self.assertIsNone(d["potential"])
        self.assertEqual((d["completeness"], d["signal"], d["path"]), (0, "brak", None))

    def test_path_transfer_when_pilot_and_portable_without_market(self):
        self.assertEqual(run(BASE)["path"]["id"], "transfer")

    def test_path_commercialization_with_results_and_market_signal(self):
        p = run(BASE + MARKET)["path"]
        self.assertEqual(p["id"], "komercjalizacja")
        self.assertTrue(p["reasons"])

    def test_path_development_for_idea_lists_missing_authors(self):
        d = run("Zespół planuje opracować koncepcję systemu monitorowania jakości powietrza w szkołach.")
        self.assertEqual(d["stage"], "idea")
        self.assertEqual(d["path"]["id"], "rozwoj")
        self.assertIn("Brak publicznie wskazanych autorów", d["path"]["missing"])

    def test_choose_path_none_without_stage(self):
        empty = {k: {"score": None, "quote": ""} for k in ("problem", "dowody", "wyniki", "przenosnosc", "gotowosc")}
        self.assertIsNone(choose_path(empty, "unknown", "", []))


class ServiceTests(TestCase):
    def setUp(self):
        self.src = Source.objects.create(name="T", entry_url="https://example.org/n/")

    def mk(self, text, url="https://example.org/n/1", **kw):
        return Article.objects.create(source=self.src, original_url=url, title="Beton", text=text,
                                      content_hash=content_hash(text), status="fetched", **kw)

    def test_cached_until_text_changes_or_force(self):
        a = self.mk(BASE)
        obj, changed = analyze_article(a)
        self.assertTrue(changed)
        self.assertEqual((obj.potential, obj.path, obj.stage), (52, "transfer", "pilot"))
        self.assertFalse(analyze_article(a)[1])
        self.assertTrue(analyze_article(a, force=True)[1])
        a.text = BASE + MARKET
        a.content_hash = content_hash(a.text)
        a.save()
        obj, changed = analyze_article(a)
        self.assertTrue(changed)
        self.assertEqual(obj.path, "komercjalizacja")
        self.assertEqual(Analysis.objects.count(), 1)

    def test_pending_skips_duplicates_unfetched_and_done(self):
        a = self.mk(BASE)
        self.mk(BASE, url="https://example.org/n/2", duplicate_of=a)
        Article.objects.create(source=self.src, original_url="https://example.org/n/3")
        self.assertEqual(analyze_pending(), 1)
        self.assertEqual(analyze_pending(), 0)
        self.assertEqual(Analysis.objects.count(), 1)

    def test_unknown_backend_rejected(self):
        with self.assertRaises(ValueError):
            analyze_article(self.mk(BASE), backend="nope")

    def test_command_and_views(self):
        a = self.mk(BASE)
        self.mk("Szkoła zorganizowała dzień otwarty dla uczniów i rodziców w sobotę.", url="https://example.org/n/9")
        call_command("analyze", stdout=__import__("io").StringIO())
        r = self.client.get(reverse("detail", args=[a.pk]))
        self.assertContains(r, "Rubryka oceny")
        self.assertContains(r, "Transfer")
        r = self.client.get(reverse("radar"), {"sort": "potencjal"})
        self.assertEqual(r.context["articles"][0].pk, a.pk)
        self.assertContains(r, "Potencjał: 52/100")
        r = self.client.get(reverse("radar"), {"sciezka": "transfer", "sygnal": "sredni"})
        self.assertEqual(r.context["total"], 1)
        self.assertEqual(self.client.get(reverse("radar"), {"sciezka": "bogus"}).context["total"], 2)

    def test_detail_without_analysis(self):
        a = self.mk(BASE)
        self.assertContains(self.client.get(reverse("detail", args=[a.pk])), "nie została jeszcze wykonana")


class SearchApiTests(TestCase):
    def setUp(self):
        src = Source.objects.create(name="T", entry_url="https://example.org/n/")
        for i, (title, text) in enumerate([
                ("Beton z PET", BASE), ("Dzień otwarty", "Szkoła zorganizowała dzień otwarty dla uczniów i rodziców w sobotę."),
                ("Grant", "Uczelnia otrzymała grant na badania nad sztuczną inteligencją w medycynie klinicznej.")]):
            Article.objects.create(source=src, original_url=f"https://example.org/n/{i}", title=title, text=text,
                                   content_hash=content_hash(text), status="fetched")
        analyze_pending()

    def test_returns_best_match_first_with_analysis(self):
        r = self.client.get(reverse("api_search"), {"q": "beton odpadów", "n": "2"}).json()
        self.assertEqual(r["results"][0]["title"], "Beton z PET")
        self.assertEqual(r["results"][0]["analysis"]["path"], "transfer")
        self.assertLessEqual(r["count"], 2)

    def test_stemming_and_no_match(self):
        self.assertEqual(self.client.get(reverse("api_search"), {"q": "betonu"}).json()["count"], 1)
        self.assertEqual(self.client.get(reverse("api_search"), {"q": "kosmonauta"}).json()["count"], 0)

    def test_requires_query(self):
        self.assertEqual(self.client.get(reverse("api_search")).status_code, 400)


class SubmitTests(TestCase):
    def test_pasted_text_is_saved_and_analyzed(self):
        r = self.client.post(reverse("submit"), {"title": "Mój beton", "text": BASE})
        a = Article.objects.get(title="Mój beton")
        self.assertRedirects(r, reverse("detail", args=[a.pk]))
        self.assertEqual((a.status, a.source.enabled, a.analysis.path), ("fetched", False, "transfer"))

    def test_duplicate_text_redirects_to_existing(self):
        self.client.post(reverse("submit"), {"text": BASE})
        r = self.client.post(reverse("submit"), {"title": "inny", "text": BASE})
        self.assertEqual(Article.objects.count(), 1)
        self.assertEqual(r.status_code, 302)

    def test_requires_text_or_url(self):
        r = self.client.post(reverse("submit"), {"text": "za krótko"})
        self.assertEqual((r.status_code, Article.objects.count()), (200, 0))
        self.assertContains(r, "Wklej opis")

    def test_url_is_fetched_and_extracted(self):
        html = (Path(__file__).parent / "fixtures" / "a1.html").read_text(encoding="utf-8")
        with mock.patch("web.views.safe_get", return_value=("https://example.org/news/a1", html)):
            r = self.client.post(reverse("submit"), {"url": "https://example.org/news/a1"})
        a = Article.objects.get()
        self.assertRedirects(r, reverse("detail", args=[a.pk]))
        self.assertEqual(a.original_url, "https://example.org/news/a1")

    def test_url_fetch_failure_shows_error(self):
        with mock.patch("web.views.safe_get", side_effect=OSError("boom")):
            r = self.client.post(reverse("submit"), {"url": "https://example.org/x"})
        self.assertContains(r, "Nie udało się pobrać")
        self.assertEqual(Article.objects.count(), 0)

    def test_form_page_renders(self):
        self.assertContains(self.client.get(reverse("submit")), "Zgłoś innowację")
