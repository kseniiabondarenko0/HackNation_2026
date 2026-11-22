"""Tryb pokazowy (DEMO_MODE): kolektor w tle nie zużywa limitu AI, a interfejs informuje o tym uczciwie."""
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from collection.models import Source

CMD = "collection.management.commands.collect_sources"


class DemoModeTests(TestCase):
    def test_collector_stays_idle_without_fetching_cleaning_or_calling_ai(self):
        out = StringIO()
        with override_settings(DEMO_MODE=True), \
             mock.patch(f"{CMD}.time.sleep", side_effect=KeyboardInterrupt), \
             mock.patch(f"{CMD}.due_sources") as due, mock.patch(f"{CMD}.run_source") as run, \
             mock.patch("analysis.service.analyze_pending") as analyze, \
             mock.patch("analysis.retention.maybe_cleanup") as cleanup, \
             mock.patch("collection.sourcefinder.maybe_run_discovery") as discovery:
            call_command("collect_sources", stdout=out)
        for spy in (due, run, analyze, cleanup, discovery):
            spy.assert_not_called()
        self.assertIn("Tryb pokazowy", out.getvalue())

    def test_explicit_single_run_still_works_in_demo_mode(self):
        source = Source.objects.create(name="Źródło testowe", entry_url="https://example.org/")
        with override_settings(DEMO_MODE=True), \
             mock.patch(f"{CMD}.due_sources", return_value=[source]), \
             mock.patch(f"{CMD}.run_source", return_value={}) as run, \
             mock.patch("collection.sourcefinder.maybe_run_discovery", return_value=None), \
             mock.patch("analysis.retention.maybe_cleanup", return_value=None), \
             mock.patch("analysis.service.analyze_pending"):
            call_command("collect_sources", once=True, stdout=StringIO())
        run.assert_called_once_with(source)

    def test_collector_runs_normally_without_demo_mode(self):
        source = Source.objects.create(name="Źródło testowe", entry_url="https://example.org/")
        with override_settings(DEMO_MODE=False), \
             mock.patch(f"{CMD}.time.sleep", side_effect=KeyboardInterrupt), \
             mock.patch(f"{CMD}.due_sources", return_value=[source]), \
             mock.patch(f"{CMD}.run_source", return_value={}) as run, \
             mock.patch("collection.sourcefinder.maybe_run_discovery", return_value=None), \
             mock.patch("analysis.retention.maybe_cleanup", return_value=None), \
             mock.patch("analysis.service.analyze_pending"):
            call_command("collect_sources", stdout=StringIO())
        run.assert_called_once_with(source)

    def test_notices_and_status_flag_appear_only_in_demo_mode(self):
        with override_settings(DEMO_MODE=True):
            self.assertIs(self.client.get("/api/status/").json()["demo_mode"], True)
            self.assertContains(self.client.get("/zrodla/"), "Tryb pokazowy")
            self.assertContains(self.client.get("/"), "tryb pokazowy")
        with override_settings(DEMO_MODE=False):
            self.assertIs(self.client.get("/api/status/").json()["demo_mode"], False)
            self.assertNotContains(self.client.get("/zrodla/"), "Tryb pokazowy")
            self.assertNotContains(self.client.get("/"), "tryb pokazowy")


class StaticServingTests(TestCase):
    def test_css_is_served_from_app_dirs_when_collectstatic_was_not_run(self):
        """Szybki start bez Dockera (DJANGO_DEBUG=0 z .env.example) ma style bez `collectstatic`."""
        with tempfile.TemporaryDirectory() as empty, override_settings(STATIC_ROOT=empty):
            response = self.client_class().get("/static/web/radar.css")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/css", response["Content-Type"])
            response.close()
