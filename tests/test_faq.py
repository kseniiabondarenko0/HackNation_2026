"""Official FAQ requirements: no age-based rejection, currency check, areas/maturity filters, TRL, comparison."""
from datetime import date, timedelta
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analysis import ai, currency, retention
from analysis.core import AREAS, area_of, area_sectors
from analysis.models import Analysis
from collection.models import Article
from collection.netsafe import FetchError
from collection.window import cutoff, is_old
from tests.test_retention import RetentionBase, days_ago

WINDOW_OFF = override_settings(ANALYSIS={**settings.ANALYSIS, "WINDOW_MONTHS": 0})


class NoAgeLimitTests(SimpleTestCase):
    @WINDOW_OFF
    def test_old_publication_is_not_old_and_decide_ignores_the_date(self):
        self.assertFalse(is_old(date(2015, 1, 1)))
        self.assertEqual(cutoff(), date(1900, 1, 1))
        v = ai.decide(True, 70, date(2015, 1, 1), "wysoka", ["cytat cytat cytat cytat"], "")
        self.assertEqual(v["id"], "glowna")
        self.assertNotIn("window", v)

    @WINDOW_OFF
    def test_unknown_date_does_not_block_publication(self):
        v = ai.decide(True, 70, None, "wysoka", ["cytat cytat cytat cytat"], "")
        self.assertEqual(v["id"], "glowna")
        self.assertIn("nieustalona", v["reason"])

    @WINDOW_OFF
    def test_low_score_and_non_initiative_are_still_rejected(self):
        self.assertEqual(ai.decide(True, 30, date(2026, 1, 1), "wysoka", ["x"], "")["id"], "odrzucone")
        self.assertEqual(ai.decide(False, 90, date(2026, 1, 1), "wysoka", ["x"], "")["id"], "odrzucone")

    def test_trl_is_validated(self):
        for value, expected in ((6, 6), (0, None), (10, None), ("7", None), (True, None), (None, None)):
            art = mock.Mock(text="tekst", final_url="u", original_url="u")
            art.published_at = None
            art.source.name, art.source.get_organization_type_display.return_value = "Z", "Uczelnia"
            self.assertEqual(ai.finalize_ai({"trl": value}, art)["ai"]["trl"], expected, value)


class AreaTests(SimpleTestCase):
    def test_three_areas_cover_known_sectors(self):
        self.assertEqual(set(AREAS), {"technologiczne", "edukacyjne", "administracyjne"})
        self.assertEqual(area_of("Edukacja"), "edukacyjne")
        self.assertEqual(area_of("Administracja i samorząd"), "administracyjne")
        self.assertEqual(area_of("Lotnictwo i kosmos"), "technologiczne")
        self.assertEqual(area_of("Inne"), "")
        self.assertIsNone(area_sectors("zly"))


class CurrencyTests(RetentionBase):
    def mk_glowna(self):
        return self.mk(verdict="glowna", published=days_ago(400))     # old publication stays

    def test_old_confirmed_item_is_kept_and_checked(self):
        with WINDOW_OFF:
            a = self.mk_glowna()
            stats = retention.cleanup(getter=lambda url: (url, "<html></html>"))
        a.refresh_from_db()
        self.assertEqual((a.analysis.verdict, stats["currency_checked"]), ("glowna", 1))
        self.assertEqual(a.analysis.data["currency"]["status"], "aktywny")

    def test_recently_checked_item_is_not_checked_again(self):
        with WINDOW_OFF:
            self.mk_glowna()
            retention.cleanup(getter=lambda url: (url, ""))
            self.assertEqual(retention.cleanup(getter=lambda url: (url, ""))["currency_checked"], 0)

    def test_three_failed_checks_hold_the_item_for_verification_without_deleting_it(self):
        def boom(url):
            raise FetchError("network: ConnectError")
        with WINDOW_OFF:
            a = self.mk_glowna()
            for i in range(3):
                an = Analysis.objects.get(article=a)
                state = dict(an.data.get("currency") or {})
                state["checked_at"] = "2000-01-01T00:00:00"     # make it due again
                an.data["currency"] = state
                an.save()
                stats = retention.cleanup(getter=boom)
            Article.objects.filter(pk=a.pk).update(first_seen_at=timezone.now() - timedelta(hours=200))
            for _ in range(2):                                   # later cycles: the queue TTL must not delete it
                retention.cleanup(getter=boom)
        an = Analysis.objects.get(article=a)
        self.assertEqual((an.verdict, an.data["currency"]["failures"], stats["currency_held"]), ("weryfikacja", 3, 1))
        self.assertTrue(Article.objects.filter(pk=a.pk).exists())

    def test_check_resets_failures_when_the_page_works_again(self):
        with WINDOW_OFF:
            a = self.mk_glowna()
            an = Analysis.objects.get(article=a)
            an.data["currency"] = {"checked_at": "2000-01-01T00:00:00", "failures": 2, "status": "niedostepny"}
            an.save()
            retention.cleanup(getter=lambda url: (url, ""))
        self.assertEqual(Analysis.objects.get(article=a).data["currency"]["failures"], 0)


class ViewTests(RetentionBase):
    def mk_sector(self, sector, stage="pilot", trl=None):
        a = self.mk(verdict="glowna")
        an = Analysis.objects.get(article=a)
        an.sector, an.stage = sector, stage
        an.data.update(sector=sector, stage=stage, stage_label=stage)
        an.data["ai"]["trl"] = trl
        an.save()
        return a

    def ids(self, response):
        return {a.pk for a in response.context["articles"]}

    def test_area_and_maturity_filters_and_counters(self):
        t = self.mk_sector("Lotnictwo i kosmos", "prototype", 6)
        e = self.mk_sector("Edukacja", "in_use")
        ad = self.mk_sector("Administracja i samorząd", "pilot")
        base = reverse("radar")
        self.assertEqual(self.ids(self.client.get(base, {"obszar": "technologiczne"})), {t.pk})
        self.assertEqual(self.ids(self.client.get(base, {"obszar": "edukacyjne"})), {e.pk})
        self.assertEqual(self.ids(self.client.get(base, {"obszar": "administracyjne"})), {ad.pk})
        r = self.client.get(base, {"dojrzalosc": "pilot"})
        self.assertEqual(self.ids(r), {ad.pk})
        self.assertEqual(dict((k, n) for k, _, n in r.context["tabs"])["glowna"], 1)     # counter equals the list
        self.assertEqual(self.ids(self.client.get(base, {"obszar": "zly", "dojrzalosc": "zly"})), {t.pk, e.pk, ad.pk})

    def test_trl_badge_on_card_and_detail_is_labelled_as_estimate(self):
        a = self.mk_sector("Lotnictwo i kosmos", "prototype", 6)
        self.assertContains(self.client.get(reverse("radar")), "TRL ~6")
        d = self.client.get(reverse("detail", args=[a.pk]))
        self.assertContains(d, "szacunek AI")
        self.assertContains(d, "Obszar: Technologiczne")

    def test_no_trl_is_shown_as_missing_not_invented(self):
        a = self.mk_sector("Edukacja")
        self.assertNotContains(self.client.get(reverse("radar")), "TRL ~")
        self.assertContains(self.client.get(reverse("detail", args=[a.pk])), "brak danych / nie dotyczy")

    def test_compare_two_to_four_and_ignores_bad_ids(self):
        items = [self.mk_sector("Edukacja") for _ in range(5)]
        r = self.client.get(reverse("compare"), {"id": [i.pk for i in items] + ["x", "99999"]})
        self.assertEqual((r.status_code, len(r.context["cols"]), r.context["few"]), (200, 4, False))
        self.assertContains(r, "Szacunki AI")
        self.assertContains(r, "Dane zweryfikowane")

    def test_compare_needs_two_items(self):
        a = self.mk_sector("Edukacja")
        r = self.client.get(reverse("compare"), {"id": a.pk})
        self.assertTrue(r.context["few"])
        self.assertContains(r, "co najmniej dwie")
        self.assertEqual(self.client.get(reverse("compare")).status_code, 200)

    def test_list_offers_compare_checkboxes(self):
        self.mk_sector("Edukacja")
        r = self.client.get(reverse("radar"))
        self.assertContains(r, 'name="id"')
        self.assertContains(r, "Porównaj zaznaczone")
