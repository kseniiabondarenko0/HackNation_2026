"""Scenario behaviour, source grounding, privacy and the shared free budget; never real API keys."""
from copy import deepcopy
from datetime import date, timedelta
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analysis import retention, service, transfer
from analysis.llmbase import LLMError
from analysis.models import LLMUsage, TransferScenario
from collection.models import Article
from tests.test_ai import GEM, GRQ_OFF, GRQ_ON, Net, QUOTE, g_reply, mk_article, q_reply

PROFILE = {"organization_type": "school", "goal": "Skrócić czas sprawdzania prac uczniów.",
           "resources": "Dwoje nauczycieli i sala komputerowa.",
           "constraints": "Brak dodatkowego budżetu i administratora IT."}
REPORT = {"verdict": "conditional", "reason": "Cel odpowiada opisowi, ale brakuje warunków licencyjnych i kosztów.",
          "evidence": [QUOTE], "blockers": ["Brak administratora może utrudnić utrzymanie systemu."],
          "questions": ["Jakie są koszty, warunki licencji i wymagane zasoby?"],
          "steps": ["Omów warunki i bezpieczeństwo danych z autorem.", "Porównaj ocenę na zanonimizowanej próbce; ustal decyzję kontynuuj/zatrzymaj."],
          "metrics": ["Czas oceny jednej pracy względem dotychczasowego sposobu."]}


@override_settings(GEMINI=GEM, GROQ=GRQ_OFF)
class TransferTests(TestCase):
    def setUp(self):
        self.a = mk_article(text=("Opis metody oceny prac uczniowskich. " * 6) + QUOTE)
        self.url = reverse("transfer", args=[self.a.pk])

    def generate(self, profile=None, owner="browser-one", report=None):
        net = Net([g_reply(report if report is not None else deepcopy(REPORT))])
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            result = transfer.generate(self.a, profile or PROFILE, owner)
        return result, net

    def test_actual_adapter_checks_quotes_and_splits_facts_from_proposals(self):
        (report, cached), net = self.generate()
        self.assertFalse(cached)
        self.assertEqual(report.status, "ready")
        self.assertEqual(report.data["verified"], {"quotes": [QUOTE]})
        self.assertEqual(report.data["ai"]["steps"], REPORT["steps"])
        self.assertNotIn("reason", report.data["verified"])
        self.assertEqual(report.data["provider"], "gemini")
        sent = net.calls[0][1]["json"]
        self.assertIn(PROFILE["constraints"], sent["contents"][0]["parts"][0]["text"])
        self.assertEqual(LLMUsage.objects.get(provider="gemini").calls, 1)

    def test_cache_hit_makes_no_network_call_even_when_budget_is_exhausted(self):
        (report, _), _ = self.generate()
        LLMUsage.objects.update(calls=GEM["MAX_CALLS_PER_DAY"])
        with mock.patch("analysis.llmbase.httpx.post") as post:
            again, cached = transfer.generate(self.a, {**PROFILE, "goal": "  " + PROFILE["goal"] + "\n"}, "browser-one")
        self.assertTrue(cached)
        self.assertEqual(again.pk, report.pk)
        post.assert_not_called()

    def test_changed_conditions_and_changed_text_require_new_reports(self):
        (first, _), _ = self.generate()
        (second, cached), _ = self.generate({**PROFILE, "constraints": "Mamy administratora i budżet, warunki licencji do ustalenia."})
        self.assertFalse(cached)
        self.assertNotEqual(first.pk, second.pk)
        # Deliberately leave Article.content_hash unchanged: the cache must still invalidate.
        self.a.text += " Dodatkowe wymaganie integracji i utrzymania systemu."
        self.a.save(update_fields=["text"])
        self.assertFalse(transfer.is_current(first, self.a))
        (third, cached), _ = self.generate()
        self.assertFalse(cached)
        self.assertNotEqual(first.pk, third.pk)

    def test_unverifiable_quotation_is_not_saved_as_a_report(self):
        bad = {**REPORT, "evidence": ["Ten cytat został wymyślony i nie ma go w źródle."]}
        with self.assertRaises(LLMError) as raised:
            self.generate(report=bad)
        self.assertEqual(raised.exception.kind, "bad_response")
        saved = TransferScenario.objects.get()
        self.assertEqual((saved.status, saved.data), ("error", {}))
        self.assertEqual(saved.profile, PROFILE)

    def test_malformed_report_is_not_saved_as_success(self):
        for bad in ({**REPORT, "steps": "do something"}, {**REPORT, "verdict": "guaranteed"},
                    {**REPORT, "metrics": []}, {**REPORT, "reason": ""}):
            with self.subTest(bad=bad), self.assertRaises(LLMError):
                self.generate(owner=str(len(TransferScenario.objects.all())), report=bad)
        self.assertFalse(TransferScenario.objects.filter(status="ready").exists())

    def test_shared_daily_limit_prevents_http_and_keeps_retryable_inputs(self):
        LLMUsage.objects.create(provider="gemini", day=date.today(), calls=GEM["MAX_CALLS_PER_DAY"])
        with mock.patch("analysis.llmbase.httpx.post") as post:
            response = self.client.post(self.url, PROFILE)
        self.assertContains(response, "Wyczerpano dzienny limit")
        self.assertContains(response, PROFILE["constraints"])
        self.assertEqual(TransferScenario.objects.get().status, "error")
        post.assert_not_called()

    @override_settings(GROQ=GRQ_ON)
    def test_provider_fallback_uses_the_existing_adapter(self):
        net = Net([g_reply({"wrong": "shape"})], [q_reply(REPORT)])
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            report, _ = transfer.generate(self.a, PROFILE, "one")
        self.assertEqual(report.data["provider"], "groq")
        self.assertEqual(net.count(), 2)

    def test_duplicate_submit_and_error_cooldown_do_not_spend_again(self):
        key, source_hash = transfer.input_key(self.a, PROFILE)
        report = TransferScenario.objects.create(article=self.a, owner="one", input_key=key, source_hash=source_hash,
                                                 profile=PROFILE, locked_until=timezone.now() + timedelta(minutes=2))
        with mock.patch("analysis.llmbase.httpx.post") as post:
            with self.assertRaises(LLMError):
                transfer.generate(self.a, PROFILE, "one")
        post.assert_not_called()
        TransferScenario.objects.filter(pk=report.pk).update(status="error", locked_until=timezone.now() - timedelta(seconds=1))
        (recovered, _), net = self.generate(owner="one")
        self.assertEqual(recovered.pk, report.pk)
        self.assertEqual(recovered.status, "ready")
        self.assertEqual(net.count(), 1)

    def test_browser_session_owns_reports_and_get_never_calls_ai(self):
        net = Net([g_reply(REPORT)])
        with mock.patch("analysis.llmbase.httpx.post", side_effect=net):
            response = self.client.post(self.url, PROFILE)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        with mock.patch("analysis.llmbase.httpx.post") as post:
            page = self.client.get(location)
            self.assertContains(page, REPORT["reason"])
            self.assertContains(page, QUOTE)
            self.assertIn("no-store", page["Cache-Control"])
            self.assertEqual(Client().get(location).status_code, 404)
            self.assertEqual(Client().get(self.url + "?from=" + str(TransferScenario.objects.get().pk)).status_code, 404)
        post.assert_not_called()
        self.assertEqual(net.count(), 1)

    def test_editing_an_older_scenario_prefills_that_scenario(self):
        for profile in (PROFILE, {**PROFILE, "goal": "Inny cel i inny problem szkoły do rozwiązania."}):
            with mock.patch("analysis.llmbase.httpx.post", side_effect=Net([g_reply(REPORT)])):
                self.client.post(self.url, profile)
        first = TransferScenario.objects.order_by("created_at").first()
        response = self.client.get(self.url + "?from=" + str(first.pk))
        self.assertEqual(response.context["form"].initial["goal"], PROFILE["goal"])
        self.assertEqual(self.client.get(self.url + "?from=not-a-uuid").status_code, 404)

    def test_changed_source_withdraws_quotes_and_conclusions_from_saved_result(self):
        with mock.patch("analysis.llmbase.httpx.post", side_effect=Net([g_reply(REPORT)])):
            response = self.client.post(self.url, PROFILE)
        Article.objects.filter(pk=self.a.pk).update(text="Całkowicie zmieniona publikacja. " * 8)
        page = self.client.get(response["Location"])
        self.assertContains(page, "Źródło zmieniło się")
        self.assertNotContains(page, QUOTE)
        self.assertNotContains(page, REPORT["reason"])
        self.assertContains(page, PROFILE["goal"])

    def test_change_during_generation_does_not_publish_a_stale_result(self):
        def change(*args):
            Article.objects.filter(pk=self.a.pk).update(text="Zmieniony tekst. " * 30)
            return {"verified": {"quotes": [QUOTE]}}
        with mock.patch("analysis.transfer._build_report", side_effect=change), self.assertRaises(LLMError):
            transfer.generate(self.a, PROFILE, "one")
        self.assertEqual(TransferScenario.objects.get().status, "error")

    def test_invalid_input_bot_or_csrf_rejection_costs_nothing(self):
        with mock.patch("analysis.llmbase.httpx.post") as post:
            self.assertEqual(self.client.post(self.url, {}).status_code, 200)
            rejected = self.client.post(self.url, {**PROFILE, "strona_www": "spam"})
            self.assertFormError(rejected.context["form"], "strona_www", "Formularz odrzucony.")
            strict = Client(enforce_csrf_checks=True)
            self.assertEqual(strict.post(self.url, PROFILE).status_code, 403)
        self.assertFalse(TransferScenario.objects.exists())
        post.assert_not_called()

    def test_article_withdrawn_during_generation_does_not_cause_a_server_error(self):
        def withdraw(*args):
            Article.objects.filter(pk=self.a.pk).delete()
            return {"verified": {"quotes": [QUOTE]}}
        with mock.patch("analysis.transfer._build_report", side_effect=withdraw), self.assertRaises(LLMError) as raised:
            transfer.generate(self.a, PROFILE, "one")
        self.assertEqual(raised.exception.kind, "unavailable")
        self.assertFalse(TransferScenario.objects.exists())

    def test_session_hourly_limit_still_allows_existing_cached_result(self):
        for i in range(8):
            self.generate(profile={**PROFILE, "goal": f"Potrzeba organizacji numer {i}."})
        with mock.patch("analysis.llmbase.httpx.post") as post, self.assertRaises(LLMError) as raised:
            transfer.generate(self.a, PROFILE, "browser-one")
        self.assertEqual(raised.exception.kind, "budget")
        post.assert_not_called()
        _, cached = transfer.generate(self.a, {**PROFILE, "goal": "Potrzeba organizacji numer 0."}, "browser-one")
        self.assertTrue(cached)

    def test_collector_leaves_the_reserved_calls_for_interactive_use(self):
        reserve = settings.LLM["SCENARIO_RESERVE"]
        LLMUsage.objects.create(provider="gemini", day=date.today(), calls=GEM["MAX_CALLS_PER_DAY"] - reserve)
        with mock.patch("analysis.llmbase.httpx.post") as post:
            self.assertEqual(service.analyze_pending("ai"), 0)
        post.assert_not_called()
        (report, _), net = self.generate()
        self.assertEqual(report.status, "ready")
        self.assertEqual(net.count(), 1)

    def test_collector_stops_after_using_the_unreserved_part(self):
        reserve = settings.LLM["SCENARIO_RESERVE"]
        LLMUsage.objects.create(provider="gemini", day=date.today(), calls=GEM["MAX_CALLS_PER_DAY"] - reserve - 1)
        mk_article(2)
        # This test checks the reservation, without relying on the article scoring schema.
        def consume(*args, **kwargs):
            from analysis.llmbase import record
            record("gemini")
            return mock.Mock(), False
        with mock.patch("analysis.service.analyze_article", side_effect=consume) as analyze:
            self.assertEqual(service.analyze_pending("ai"), 1)
        self.assertEqual(analyze.call_count, 1)

    def test_private_scenarios_expire_without_deleting_the_article(self):
        (report, _), _ = self.generate()
        TransferScenario.objects.filter(pk=report.pk).update(created_at=timezone.now() - timedelta(days=8))
        ctx = mock.Mock(now=timezone.now(), stats={"scenarios_dropped": 0})
        retention._scenarios(ctx)
        self.assertEqual(ctx.stats["scenarios_dropped"], 1)
        self.assertFalse(TransferScenario.objects.exists())
        self.assertTrue(Article.objects.filter(pk=self.a.pk).exists())

    def test_an_expired_cache_entry_is_recomputed_even_before_worker_cleanup(self):
        (old, _), _ = self.generate()
        TransferScenario.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))
        (new, cached), _ = self.generate()
        self.assertFalse(cached)
        self.assertNotEqual(new.pk, old.pk)
