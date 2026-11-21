from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from analysis.examples import EXAMPLES
from analysis.service import analyze_pending
from collection.extract import content_hash
from collection.models import Article, Source
from matching.models import Recipient
from matching.recipients import match_articles


def ex(i):
    return next(e for e in EXAMPLES if e["id"] == i)


class NeedsTests(TestCase):
    def setUp(self):
        src = Source.objects.create(name="T", entry_url="https://example.org/n/")
        for n, i in enumerate(("gmina-decyzje", "mops-seniorzy", "dozynki", "beton-pet")):
            e = ex(i)
            Article.objects.create(source=src, original_url=f"https://example.org/n/{n}", title=e["title"],
                                   text=e["text"], content_hash=content_hash(e["text"]), status="fetched")
        analyze_pending()

    def test_seeded_profiles_for_priority_and_social(self):
        names = " ".join(Recipient.objects.values_list("name", flat=True))
        for word in ("lotnicz", "motoryzac", "pomocy społecznej"):
            self.assertIn(word, names)

    def test_submit_need_and_see_matching_innovations(self):
        r = self.client.post(reverse("need_submit"), {
            "name": "Gmina Testowa", "institution_type": "samorzad", "needs": "Szybsza obsługa mieszkańców w urzędzie.",
            "tags": "wniosk, urzęd, obsług", "sectors": ["Administracja i samorząd"], "paths": ["transfer"]})
        need = Recipient.objects.get(name="Gmina Testowa")
        self.assertRedirects(r, reverse("need_detail", args=[need.pk]))
        self.assertFalse(need.is_example)
        page = self.client.get(reverse("need_detail", args=[need.pk]))
        titles = [m["article"].title for m in page.context["matches"]]
        self.assertEqual(titles[0], "Gmina skróciła czas wydawania decyzji")
        self.assertNotIn("Dożynki gminne 2026", titles)  # rejected publications are never offered

    def test_contact_requires_consent_and_is_staff_only(self):
        data = {"name": "Szkoła X", "institution_type": "szkola", "needs": "Metody nauczania matematyki.",
                "tags": "matemat, uczni", "contact": "dyrektor@szkola.example"}
        r = self.client.post(reverse("need_submit"), data)
        self.assertContains(r, "zgodę")
        self.client.post(reverse("need_submit"), {**data, "consent": "on"})
        need = Recipient.objects.get(name="Szkoła X")
        self.assertTrue(need.consent)
        self.assertNotContains(self.client.get(reverse("need_detail", args=[need.pk])), "dyrektor@szkola.example")
        self.client.force_login(User.objects.create_user("e", password="x", is_staff=True))
        self.assertContains(self.client.get(reverse("need_detail", args=[need.pk])), "dyrektor@szkola.example")

    def test_social_profile_matches_social_innovation(self):
        prof = Recipient.objects.get(name__startswith="Ośrodek pomocy społecznej")
        self.assertEqual(match_articles(prof)[0]["article"].title, "Senioralna sieć wsparcia")

    def test_needs_list(self):
        self.assertContains(self.client.get(reverse("needs")), "Zgłoś potrzebę")
