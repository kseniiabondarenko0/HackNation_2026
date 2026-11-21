"""Expert review of publications, the 'Skuteczność' page and PCI priority."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from analysis.core import finalize, priority
from analysis.models import Analysis
from analysis.rules import analyze
from analysis.service import analyze_pending
from analysis.tabs import TABS
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


class TabsAndPagesTests(TestCase):
    """Automatic assessment only: no expert login/decision UI, three lists with counters equal to the lists."""
    def setUp(self):
        src = Source.objects.create(name="T", entry_url="https://example.org/n/")
        for i, (title, text) in enumerate([("Beton", BASE), ("Dzień otwarty", OPEN_DAY), ("Dron", DRONE)]):
            Article.objects.create(source=src, original_url=f"https://example.org/n/{i}", title=title, text=text,
                                   content_hash=content_hash(text), status="fetched")
        analyze_pending()
        self.beton = Article.objects.get(title="Beton")
        self.open_day = Article.objects.get(title="Dzień otwarty")

    def test_priority_sort(self):
        r = self.client.get(reverse("radar"), {"sort": "priorytet", "widok": "wszystkie"})
        self.assertEqual(r.context["articles"][0].title, "Dron")

    def test_no_expert_moderation_in_ui(self):
        with self.assertRaises(NoReverseMatch):
            reverse("review", args=[self.beton.pk])
        for url in (reverse("radar"), reverse("detail", args=[self.beton.pk]), reverse("detail", args=[self.open_day.pk]),
                    reverse("effectiveness"), reverse("about"), reverse("overview")):
            body = self.client.get(url).content.decode().lower()
            for banned in ("zaloguj się jako ekspert", "zatwierdzone przez eksperta", "zatwierdź jako innowację",
                           "decyzja eksperta", "widok=odrzucone", "widok=zatwierdzone"):
                self.assertNotIn(banned, body, (url, banned))

    def test_counters_equal_lists_also_with_filters(self):
        for extra in ({}, {"sciezka": "transfer"}, {"woj": "podkarpackie"}, {"q": "dron"}, {"sektor": "Edukacja"}):
            for view in TABS:
                r = self.client.get(reverse("radar"), {**extra, "widok": view})
                counters = {k: n for k, _, n in r.context["tabs"]}
                self.assertEqual(counters[view], r.context["total"], (extra, view))

    def test_removed_tab_in_old_bookmark_falls_back_without_echo(self):
        for old in ("odrzucone", "zatwierdzone"):
            r = self.client.get(reverse("radar"), {"widok": old})
            self.assertEqual(r.context["view"], "glowna")
            self.assertNotIn(f"widok={old}", r.content.decode())

    def test_tabs_are_exactly_three(self):
        r = self.client.get(reverse("radar"))
        self.assertEqual([label for _, label, _ in r.context["tabs"]], ["Interesujące", "Do weryfikacji", "Wszystkie"])

    def test_waiting_and_all_tabs_follow_analysis_state(self):
        src = Source.objects.get(name="T")
        fresh = Article.objects.create(source=src, original_url="https://example.org/n/new", title="Nowy", text=BASE + " x",
                                       content_hash=content_hash(BASE + " x"), status="fetched")
        ids = lambda view: {a.pk for a in self.client.get(reverse("radar"), {"widok": view}).context["articles"]}
        self.assertIn(fresh.pk, ids("weryfikacja"))      # not analysed yet -> temporary queue
        self.assertNotIn(fresh.pk, ids("glowna"))
        self.assertNotIn(fresh.pk, ids("wszystkie"))     # "Wszystkie" = passed the check
        self.assertNotIn(self.open_day.pk, ids("wszystkie"))  # judged not an innovation -> not listed
        self.assertIn(self.beton.pk, ids("wszystkie"))

    def test_effectiveness_page(self):
        r = self.client.get(reverse("effectiveness"))
        self.assertContains(r, "Aktualne materiały w bazie")
        self.assertContains(r, "Test na oznaczonych przykładach")
        self.assertEqual(r.context["stored"], 3)
        kept = Analysis.objects.filter(verdict__in=("glowna", "weryfikacja")).count()
        self.assertEqual(r.context["waiting"], 3 - kept)


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
