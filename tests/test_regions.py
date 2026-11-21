"""Voivodeship filter: any of the 16 voivodeships can be chosen (curators: any voivodeship may be used)."""
from django.test import TestCase
from django.urls import reverse
from analysis.examples import EXAMPLES
from analysis.models import Analysis
from analysis.regions import CODES, detect, resolve
from analysis.service import analyze_pending
from collection.extract import content_hash
from collection.models import Article, Source
from matching.models import Recipient
from matching.recipients import match_recipients


def ex(i):
    return next(e for e in EXAMPLES if e["id"] == i)


class DetectTests(TestCase):
    def test_sixteen_voivodeships(self):
        self.assertEqual(len(CODES), 16)

    def test_detect_cities_and_tricky_names(self):
        cases = {"Politechnika Wrocławska": "dolnośląskie", "w Białymstoku": "podlaskie",
                 "Biała Podlaska wdrożyła": "lubelskie", "Katowice, Górny Śląsk": "śląskie",
                 "województwo kujawsko-pomorskie": "kujawsko-pomorskie", "Szczecin": "zachodniopomorskie",
                 "w Łodzi": "łódzkie", "Urząd Gminy Jasło": "podkarpackie"}
        for text, code in cases.items():
            self.assertEqual(detect(text)[0], code, text)
        self.assertEqual(detect("Jarosław Nowak powiedział")[0], "")  # a first name is not a town

    def test_resolve_order_text_then_source_then_choice(self):
        self.assertEqual(resolve("Nic o miejscu.", "mazowieckie")["how"], "siedziba instytucji źródła")
        self.assertEqual(resolve("Projekt z Gdańska.", "mazowieckie")["code"], "pomorskie")
        self.assertEqual(resolve("Projekt z Gdańska.", "mazowieckie", "opolskie")["code"], "opolskie")
        self.assertEqual(resolve("Nic.")["code"], "")


class RegionFilterTests(TestCase):
    def setUp(self):
        warsaw = Source.objects.create(name="PW", entry_url="https://pw.example/n/", region="mazowieckie")
        national = Source.objects.create(name="NCBR", entry_url="https://ncbr.example/n/")
        for src, i, url in ((warsaw, "beton-pet", 1), (warsaw, "czujnik-sepsy", 2), (national, "ai-rtg", 3)):
            e = ex(i)
            Article.objects.create(source=src, original_url=f"https://x.example/{url}", title=e["title"],
                                   text=e["text"], content_hash=content_hash(e["text"]), status="fetched")
        analyze_pending()

    def regions(self):
        return dict(Analysis.objects.values_list("article__title", "region"))

    def test_text_wins_over_source_seat(self):
        r = self.regions()
        self.assertEqual(r["Beton z odpadów PET"], "dolnośląskie")  # "Politechniki Wrocławskiej" in the text

    def test_radar_and_export_filter(self):
        counts = {}
        for code in {c or "ogólnopolskie" for c in self.regions().values()}:
            counts[code] = self.client.get(reverse("radar"), {"woj": code, "widok": "wszystkie"}).context["total"]
        self.assertEqual(sum(counts.values()), 3)
        self.assertEqual(counts["dolnośląskie"], 1)
        r = self.client.get(reverse("export", args=["json"]), {"woj": "dolnośląskie", "widok": "wszystkie"}).json()
        self.assertEqual([x["wojewodztwo"] for x in r["results"]], ["dolnośląskie"])
        self.assertContains(self.client.get(reverse("radar")), "Wszystkie województwa")

    def test_same_voivodeship_gives_a_matching_point(self):
        a = Article.objects.get(title="Beton z odpadów PET")
        base = Recipient.objects.create(name="Firma X", institution_type="firma", needs="beton",
                                        tags="beton, odpad", region="")
        local = Recipient.objects.create(name="Firma Y", institution_type="firma", needs="beton",
                                         tags="beton, odpad", region="dolnośląskie")
        found = {m["recipient"].name: m for m in match_recipients(a, a.analysis.data, recipients=[base, local])}
        self.assertEqual(found["Firma Y"]["score"], found["Firma X"]["score"] + 1)
        self.assertIn("To samo województwo: dolnośląskie", found["Firma Y"]["reasons"])
