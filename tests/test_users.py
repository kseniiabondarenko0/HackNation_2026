"""Schools, private persons and private firms use the site too (curators' remark)."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from analysis.examples import EXAMPLES
from collection.models import Article, Submission
from matching.models import Recipient


def ex(i):
    return next(e for e in EXAMPLES if e["id"] == i)


class SubmissionTests(TestCase):
    def post(self, **extra):
        e = ex("szkola-matematyka")
        data = {"submitter_type": "person", "region": "podkarpackie", "title": e["title"], "text": e["text"], **extra}
        return self.client.post(reverse("submit"), data)

    def test_private_person_submits_with_consent_and_private_name(self):
        r = self.post(author_name="Anna Kowalska", contact="anna@example.org", consent="on")
        a = Article.objects.get()
        self.assertRedirects(r, reverse("detail", args=[a.pk]))
        s = a.submission
        self.assertEqual((s.submitter_type, s.region, s.author_name, s.show_name), ("person", "podkarpackie", "Anna Kowalska", False))
        self.assertEqual(a.analysis.region, "podkarpackie")
        page = self.client.get(reverse("detail", args=[a.pk]))
        self.assertContains(page, "Osoba prywatna")
        self.assertNotContains(page, "Anna Kowalska")       # not public without "show name"
        self.assertNotContains(page, "anna@example.org")
        self.client.force_login(User.objects.create_user("e", password="x", is_staff=True))
        page = self.client.get(reverse("detail", args=[a.pk]))
        self.assertContains(page, "anna@example.org")

    def test_personal_data_needs_consent(self):
        r = self.post(author_name="Anna Kowalska")
        self.assertContains(r, "zaznacz zgodę")
        self.assertEqual(Article.objects.count(), 0)

    def test_public_name_when_chosen(self):
        self.post(author_name="Anna Kowalska", consent="on", show_name="on")
        a = Article.objects.get()
        self.assertContains(self.client.get(reverse("detail", args=[a.pk])), "Autor: Anna Kowalska")

    def test_honeypot_rejects_bots(self):
        r = self.post(strona_www="http://spam.example")
        self.assertEqual(Article.objects.count(), 0)
        self.assertEqual(r.status_code, 200)

    def test_firm_submission_filter_and_export(self):
        self.post(submitter_type="company", organization="Firma ABC")
        self.assertEqual(self.client.get(reverse("radar"), {"kto": "company", "widok": "wszystkie"}).context["total"], 1)
        self.assertEqual(self.client.get(reverse("radar"), {"kto": "school", "widok": "wszystkie"}).context["total"], 0)
        rows = self.client.get(reverse("export", args=["json"]), {"widok": "wszystkie"}).json()["results"]
        self.assertEqual(rows[0]["typ_instytucji"], "Firma prywatna")
        self.assertNotIn("Anna", str(rows))

    def test_submission_without_type_still_works(self):
        e = ex("gmina-decyzje")
        self.client.post(reverse("submit"), {"title": e["title"], "text": e["text"]})
        self.assertEqual(Submission.objects.get().submitter_type, "other")


class NeedsAndPagesTests(TestCase):
    def test_private_person_can_submit_a_need(self):
        self.client.post(reverse("need_submit"), {"name": "Jan", "institution_type": "osoba",
                                                  "needs": "Szukam pomocy dla seniora.", "tags": "senior"})
        self.assertEqual(Recipient.objects.get(name="Jan").get_institution_type_display(), "Osoba prywatna")

    def test_need_honeypot(self):
        self.client.post(reverse("need_submit"), {"name": "Bot", "institution_type": "firma", "needs": "x",
                                                  "tags": "x", "strona_www": "spam"})
        self.assertFalse(Recipient.objects.filter(name="Bot").exists())

    def test_for_whom_page(self):
        r = self.client.get(reverse("for_whom"))
        for who in ("Szkoła", "Firma prywatna", "Osoba prywatna", "Samorząd"):
            self.assertContains(r, who)
