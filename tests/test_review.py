"""Expert review of publications, the 'Skuteczność' page and PCI priority."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from analysis.core import finalize, priority
from analysis.models import Analysis
from analysis.rules import analyze
from analysis.service import analyze_pending
from collection.extract import content_hash
from collection.models import Article, Source
from .test_analysis import BASE

OPEN_DAY = "Szkoła zorganizowała dzień otwarty dla uczniów i rodziców w sobotę. Zapraszamy wszystkich chętnych."
DRONE = ("Inżynierowie z Rzeszowa opracowali prototyp drona do inspekcji linii energetycznych. "
         "Problemem operatorów są kosztowne przeglądy linii. Dron przetestowano w pilotażu w warunkach rzeczywistych, "
         "czas inspekcji skrócił się o 40%. Rozwiązanie można przenieść do innych regionów.")


class PriorityTests(TestCase):
    def test_sector_and_region(self):
        self.assertEqual(priority("Lotnictwo i kosmos", "podkarpackie")[0], 3)
        self.assertEqual(priority("Edukacja", "mazowieckie")[0], 0)
        with self.settings(ANALYSIS={**__import__("django.conf").conf.settings.ANALYSIS, "PRIORITY_REGION": "mazowieckie"}):
            self.assertEqual(priority("Edukacja", "mazowieckie")[0], 1)

    def test_drone_text_is_aviation_and_podkarpacie(self):
        d = finalize(analyze(DRONE, "Dron"), DRONE)
        self.assertEqual((d["sector"], d["priority"]), ("Lotnictwo i kosmos", 3))
        self.assertEqual(d["region"]["code"], "podkarpackie")
        self.assertTrue(any("podkarpackie" in r for r in d["priority_reasons"]))


class ReviewTests(TestCase):
    def setUp(self):
        src = Source.objects.create(name="T", entry_url="https://example.org/n/")
        for i, (title, text) in enumerate([("Beton", BASE), ("Dzień otwarty", OPEN_DAY), ("Dron", DRONE)]):
            Article.objects.create(source=src, original_url=f"https://example.org/n/{i}", title=title, text=text,
                                   content_hash=content_hash(text), status="fetched")
        analyze_pending()
        self.beton = Article.objects.get(title="Beton")
        self.open_day = Article.objects.get(title="Dzień otwarty")
        self.staff = User.objects.create_user("ekspert", password="x", is_staff=True)

    def total(self, view):
        return self.client.get(reverse("radar"), {"widok": view}).context["total"]

    def test_requires_staff(self):
        self.client.post(reverse("review", args=[self.beton.pk]), {"decyzja": "zatwierdz"})
        self.assertEqual(Analysis.objects.get(article=self.beton).review_status, "nowy")

    def test_reject_needs_reason_and_moves_to_rejected_tab(self):
        self.client.force_login(self.staff)
        url = reverse("review", args=[self.beton.pk])
        before = self.total("glowna")
        self.client.post(url, {"decyzja": "odrzuc"})
        self.assertEqual(Analysis.objects.get(article=self.beton).review_status, "nowy")
        self.client.post(url, {"decyzja": "odrzuc", "uwaga": "relacja z wydarzenia"})
        self.assertEqual(self.total("glowna"), before - 1)
        self.assertContains(self.client.get(reverse("radar"), {"widok": "odrzucone"}), "relacja z wydarzenia")
        self.client.post(url, {"decyzja": "cofnij"})
        an = Analysis.objects.get(article=self.beton)
        self.assertEqual((an.review_status, an.review_note, an.reviewed_by), ("nowy", "", ""))

    def test_expert_can_rescue_rejected_publication(self):
        self.assertEqual(Analysis.objects.get(article=self.open_day).verdict, "odrzucone")
        self.client.force_login(self.staff)
        self.client.post(reverse("review", args=[self.open_day.pk]), {"decyzja": "zatwierdz"})
        self.assertEqual(self.total("zatwierdzone"), 1)
        ids = [a.pk for a in self.client.get(reverse("radar")).context["articles"]]
        self.assertIn(self.open_day.pk, ids)

    def test_review_survives_reanalysis(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("review", args=[self.beton.pk]), {"decyzja": "zatwierdz"})
        analyze_pending(force=True)
        self.assertEqual(Analysis.objects.get(article=self.beton).review_status, "zatwierdzony")

    def test_priority_sort(self):
        r = self.client.get(reverse("radar"), {"sort": "priorytet", "widok": "wszystkie"})
        self.assertEqual(r.context["articles"][0].title, "Dron")

    def test_detail_shows_filter_and_form(self):
        self.assertContains(self.client.get(reverse("detail", args=[self.open_day.pk])), "Zaloguj się jako ekspert")
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("detail", args=[self.beton.pk])), "Zatwierdź jako innowację")

    def test_effectiveness_page(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("review", args=[self.beton.pk]), {"decyzja": "zatwierdz"})
        r = self.client.get(reverse("effectiveness"))
        self.assertContains(r, "Lejek")
        self.assertContains(r, "Test na oznaczonych przykładach")
        main = next(a for a in r.context["agreement"] if a["id"] == "glowna")
        self.assertEqual((main["approved"], main["rate"]), (1, 100))
        self.assertEqual(r.context["collected"], 3)


class NonTechnologicalInnovationTests(TestCase):
    """Task text: an innovation may be organisational, educational, social or process-related."""

    def test_examples_classified_with_path_and_type(self):
        from analysis.examples import EXAMPLES
        cases = {"szkola-matematyka": "edukacyjna", "gmina-decyzje": "organizacyjna",
                 "mops-seniorzy": "społeczna", "szpital-kolejka": "organizacyjna"}
        for ex in EXAMPLES:
            if ex["id"] in cases:
                d = finalize(analyze(ex["text"], ex["title"]), ex["text"])
                self.assertNotEqual(d["verdict"]["id"], "odrzucone", ex["id"])
                self.assertIsNotNone(d["path"], ex["id"])
                self.assertEqual(d["innovation_types"][0], cases[ex["id"]], ex["id"])

    def test_filter_has_no_errors_on_labeled_examples(self):
        from analysis.evaluation import evaluate
        self.assertEqual(evaluate()["errors"], [])


class HandlingTests(TestCase):
    """Task, section 9: what happens with an innovation after it has been identified."""

    def setUp(self):
        src = Source.objects.create(name="T", entry_url="https://example.org/n/")
        self.a = Article.objects.create(source=src, original_url="https://example.org/n/1", title="Beton", text=BASE,
                                        content_hash=content_hash(BASE), status="fetched")
        analyze_pending()
        self.client.force_login(User.objects.create_user("ekspert", password="x", is_staff=True))
        from matching.models import Recipient
        self.partner = Recipient.objects.filter(active=True).first()

    def test_handover_requires_partner_and_keeps_history(self):
        url = reverse("handling", args=[self.a.pk])
        self.client.post(url, {"etap": "kontakt", "uwaga": "mail do autora"})
        self.client.post(url, {"etap": "przekazano"})  # refused: no partner
        an = Analysis.objects.get(article=self.a)
        self.assertEqual(an.handling, "kontakt")
        self.client.post(url, {"etap": "przekazano", "partner": self.partner.pk})
        self.client.post(url, {"etap": "wdrozono", "uwaga": "umowa licencyjna"})
        an.refresh_from_db()
        self.assertEqual((an.handling, an.handling_partner_id), ("wdrozono", self.partner.pk))
        self.assertEqual([h["status"] for h in an.handling_log], ["kontakt", "przekazano", "wdrozono"])
        r = self.client.get(reverse("detail", args=[self.a.pk]))
        self.assertContains(r, "Co dalej z tą innowacją")
        self.assertContains(r, "umowa licencyjna")
        funnel = dict((label, n) for label, n, _ in self.client.get(reverse("effectiveness")).context["funnel"])
        self.assertEqual(funnel["Wdrożone / skomercjalizowane"], 1)

    def test_handling_survives_reanalysis(self):
        self.client.post(reverse("handling", args=[self.a.pk]), {"etap": "kontakt"})
        analyze_pending(force=True)
        self.assertEqual(Analysis.objects.get(article=self.a).handling, "kontakt")
