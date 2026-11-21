from django.test import TestCase
from django.urls import reverse
from analysis.service import analyze_article
from collection.extract import content_hash
from collection.models import Article, Source
from matching.models import Recipient, split_list
from matching.recipients import match_recipients
from matching.similar import similar

CONCRETE = ("Naukowcy z Politechniki opracowali innowacyjny prototyp betonu z odpadów PET. "
            "Celem projektu jest rozwiązanie problemu składowania odpadów tworzyw sztucznych. "
            "Prototyp betonu został przetestowany w laboratorium, a wyniki pokazują redukcję emisji o 20%. "
            "Rozwiązanie jest skalowalne i może trafić do innych miast.")
CONCRETE2 = ("Studenci zbadali beton z dodatkiem odpadów PET z butelek. Beton z recyklingu tworzyw sztucznych "
             "ma mniejszą emisję i podobną wytrzymałość. Odpady PET mogą zastąpić część kruszywa.")
SCHOOL = ("Nauczyciele szkoły podstawowej przygotowali nową metodę lekcji matematyki dla uczniów. "
          "Uczniowie pracują w parach z grami planszowymi; metoda jest stosowana od roku w trzech klasach.")


class Base(TestCase):
    def setUp(self):
        self.src = Source.objects.create(name="Test", entry_url="https://example.org/news/")

    def art(self, title, text, **kw):
        return Article.objects.create(source=self.src, original_url=f"https://example.org/{content_hash(text)[:10]}",
                                      title=title, text=text, content_hash=content_hash(text), status="fetched", **kw)


class SimilarTests(Base):
    def test_finds_related_article_with_shared_terms_and_skips_unrelated(self):
        a = self.art("Beton z odpadów PET", CONCRETE)
        b = self.art("Beton z butelek", CONCRETE2)
        self.art("Gry na lekcjach", SCHOOL)
        res = similar(a)
        self.assertEqual([r["article"] for r in res], [b])
        self.assertIn("betonu", res[0]["shared"])   # surface form from the current article
        self.assertTrue(0 < res[0]["percent"] <= 100)

    def test_excludes_self_duplicates_and_empty_corpus(self):
        a = self.art("Beton z odpadów PET", CONCRETE)
        self.assertEqual(similar(a), [])
        dup = Article.objects.create(source=self.src, original_url="https://example.org/dup", title="Kopia",
                                     text=CONCRETE + " ", content_hash="x", status="fetched", duplicate_of=a)
        self.assertEqual(similar(a), [])
        self.assertEqual(similar(dup), [])


class RecipientTests(Base):
    def test_seeded_profiles_exist(self):
        self.assertGreaterEqual(Recipient.objects.filter(active=True).count(), 8)

    def test_split_list(self):
        self.assertEqual(split_list(" Beton, odpad ,,beton "), ["beton", "odpad"])

    def test_ranking_and_explanations(self):
        a = self.art("Beton z odpadów PET", CONCRETE)
        an, _ = analyze_article(a)
        res = match_recipients(a, an.data)
        self.assertTrue(res)
        top = res[0]
        self.assertTrue(all(res[i]["score"] >= res[i + 1]["score"] for i in range(len(res) - 1)))
        self.assertTrue(top["reasons"])
        self.assertTrue(any("Wspólne słowa kluczowe" in r or "Sektor" in r for r in top["reasons"]))
        names = [m["recipient"].name for m in res]
        self.assertFalse(any("Szkoła" in n for n in names))

    def test_school_text_matches_school_profile(self):
        a = self.art("Gry na lekcjach", SCHOOL)
        an, _ = analyze_article(a)
        self.assertIn("Szkoła", match_recipients(a, an.data)[0]["recipient"].name)

    def test_inactive_and_unrelated_profiles_are_skipped(self):
        Recipient.objects.all().delete()
        Recipient.objects.create(name="Off", institution_type="firma", needs="x", tags="beton", active=False)
        Recipient.objects.create(name="Unrelated", institution_type="firma", needs="x", tags="kosmos",
                                 paths="rozwoj, transfer", stages="pilot")
        a = self.art("Beton z odpadów PET", CONCRETE)
        self.assertEqual(match_recipients(a, analyze_article(a)[0].data), [])

    def test_works_without_analysis(self):
        a = self.art("Beton z odpadów PET", CONCRETE)
        self.assertTrue(match_recipients(a, None))


class PageTests(Base):
    def test_detail_shows_rubric_path_similar_and_recipients(self):
        a = self.art("Beton z odpadów PET", CONCRETE)
        b = self.art("Beton z butelek", CONCRETE2)
        analyze_article(a)
        body = self.client.get(reverse("detail", args=[a.pk])).content.decode()
        for text in ("Rubryka oceny", "Sugerowana ścieżka", "Podobne rozwiązania", "Potencjalni odbiorcy",
                     "Dlaczego ten odbiorca", "nie oznacza, że odbiorca jest zainteresowany", b.title):
            self.assertIn(text, body)

    def test_detail_without_analysis_or_matches(self):
        Recipient.objects.all().delete()
        a = self.art("Gry na lekcjach", SCHOOL)
        r = self.client.get(reverse("detail", args=[a.pk]))
        self.assertContains(r, "Nie znaleziono w bazie")
        self.assertContains(r, "Żaden aktywny profil")

    def test_about_page(self):
        self.art("Beton z odpadów PET", CONCRETE)
        r = self.client.get(reverse("about"))
        for text in ("Źródła danych", "Założenia", "Ograniczenia", "Czego system NIE twierdzi",
                     "Skalowalność", "Bezpieczeństwo", "Test", "Dowody ×2"):
            self.assertContains(r, text)
        self.assertContains(self.client.get(reverse("radar")), reverse("about"))
