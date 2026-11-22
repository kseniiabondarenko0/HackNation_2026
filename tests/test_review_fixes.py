"""Poprawki po przeglądzie: formaty eksportu, wersja, opis testu na stronie skuteczności, data na pierwszym ekranie."""
from datetime import datetime, timezone as dt_tz

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from analysis.models import Analysis
from collection.extract import content_hash
from collection.models import Article, Source


class ExportAndStatusTests(TestCase):
    def test_known_formats_work(self):
        self.assertEqual(self.client.get("/api/innowacje.json").status_code, 200)
        self.assertIn("text/csv", self.client.get("/api/innowacje.csv")["Content-Type"])

    def test_unknown_format_is_404(self):
        for fmt in ("xml", "html", "txt"):
            self.assertEqual(self.client.get(f"/api/innowacje.{fmt}").status_code, 404, fmt)

    def test_version_comes_from_settings(self):
        self.assertEqual(self.client.get("/health/").json()["version"], settings.APP_VERSION)
        self.assertEqual(self.client.get("/api/status/").json()["version"], settings.APP_VERSION)


class EffectivenessWordingTests(TestCase):
    def test_rule_filter_test_is_labelled_honestly(self):
        html = self.client.get(reverse("effectiveness")).content.decode()
        self.assertIn("Test filtra regułowego", html)
        self.assertIn("nie została jeszcze zmierzona", html)


class HeroDateTests(TestCase):
    def test_hero_shows_publication_date_not_load_date(self):
        src = Source.objects.create(name="Z", entry_url="https://example.pl/")
        a = Article.objects.create(
            source=src, original_url="https://example.pl/a", title="Pilotaż", text="Opis wdrożenia. " * 20,
            content_hash=content_hash("hero"), status="fetched",
            published_at=datetime(2026, 11, 3, tzinfo=dt_tz.utc))
        Analysis.objects.create(article=a, backend="ai", verdict="glowna", potential=80, completeness=50, data={})
        html = self.client.get(reverse("overview")).content.decode()
        self.assertIn("Opublikowano 03.11.2026", html)
