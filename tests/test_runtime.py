from datetime import timedelta
from unittest import mock
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from collection.discovery import discover
from collection.models import Article, CollectionRun
from collection.netsafe import FetchError, is_safe_url, safe_get, _ROBOTS
from collection.services import run_source
from tests.test_collector import FX, getter, mk


class RuntimeTests(TestCase):
    def collect(self, source, **kwargs):
        return run_source(source, getter=kwargs.pop("getter", getter), sleep=lambda _: None, **kwargs)

    def test_run_history_and_schedule_are_persisted(self):
        source = mk()
        self.collect(source)
        source.refresh_from_db()
        run = CollectionRun.objects.get()
        self.assertEqual(run.status, "success")
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(source.last_stats["discovered"], 3)
        self.assertGreater(source.next_run_at, timezone.now())
        self.assertIsNone(source.locked_until)

    def test_parser_failure_does_not_abort_other_articles(self):
        from collection.extract import extract_article
        def parse(html, url):
            if url.endswith("a2"):
                raise ValueError("bad document")
            return extract_article(html, url)
        source = mk()
        with mock.patch("collection.services.extract_article", side_effect=parse):
            stats = self.collect(source)
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(Article.objects.filter(status="fetched").count(), 2)
        self.assertEqual(CollectionRun.objects.get().status, "partial")
        source.refresh_from_db()
        self.assertTrue(source.last_error)

    def test_persistent_backlog_is_drained_after_link_leaves_listing(self):
        source = mk()
        with override_settings(COLLECT={**settings.COLLECT, "MAX_NEW_PER_RUN": 1}):
            self.collect(source)
            self.assertEqual(Article.objects.filter(status="found").count(), 2)
            def short_listing(url):
                if url == source.entry_url:
                    return url, '<a href="/news/a1">one</a>'
                return getter(url)
            self.collect(source, getter=short_listing)
        self.assertEqual(Article.objects.filter(status="fetched").count(), 2)

    def test_recent_article_is_not_fetched_twice(self):
        source = mk()
        self.collect(source)
        calls = []
        def counted(url):
            calls.append(url)
            return getter(url)
        self.collect(source, getter=counted)
        self.assertEqual(calls, [source.entry_url])
        self.assertEqual(Article.objects.count(), 3)

    def test_old_articles_are_rechecked_without_new_rows(self):
        source = mk()
        self.collect(source)
        Article.objects.update(fetched_at=timezone.now() - timedelta(days=2))
        stats = self.collect(source)
        self.assertEqual(stats["unchanged"], 3)
        self.assertEqual(Article.objects.count(), 3)

    def test_changed_article_releases_alias_of_old_content(self):
        source = mk()
        self.collect(source)
        original = Article.objects.get(original_url="https://example.org/news/a1")
        Article.objects.filter(pk=original.pk).update(fetched_at=timezone.now() - timedelta(days=2))
        def changed(url):
            final, content = getter(url)
            if url.endswith("a1"):
                content = content.replace("monitorowania", "sprawdzania")
            return final, content
        stats = self.collect(source, getter=changed)
        self.assertEqual(stats["updated"], 1)
        self.assertIsNone(Article.objects.get(original_url="https://example.org/news/a1-copy").duplicate_of_id)

    def test_active_source_cannot_be_collected_concurrently(self):
        source = mk(locked_until=timezone.now() + timedelta(minutes=5))
        result = self.collect(source)
        self.assertTrue(result["busy"])
        self.assertEqual(CollectionRun.objects.count(), 0)

    def test_interrupted_run_releases_lock_and_keeps_honest_status(self):
        source = mk()
        with self.assertRaises(KeyboardInterrupt):
            self.collect(source, getter=mock.Mock(side_effect=KeyboardInterrupt))
        source.refresh_from_db()
        self.assertIsNone(source.locked_until)
        self.assertEqual(CollectionRun.objects.get().status, "interrupted")
        self.assertIsNone(source.last_success)

    def test_expired_run_is_marked_interrupted(self):
        source = mk(locked_until=timezone.now() - timedelta(minutes=1))
        previous = CollectionRun.objects.create(source=source)
        self.collect(source)
        previous.refresh_from_db()
        self.assertEqual(previous.status, "interrupted")

    def test_sitemap_index_and_lastmod_are_not_publication_date(self):
        source = mk(entry_url="https://example.org/sitemap.xml", discovery_type="sitemap")
        def sitemap_get(url):
            if url.endswith("sitemap.xml"):
                return url, '<sitemapindex><sitemap><loc>https://example.org/child.xml</loc></sitemap></sitemapindex>'
            if url.endswith("child.xml"):
                return url, '<urlset><url><loc>https://example.org/news/a1</loc><lastmod>2020-01-01</lastmod></url></urlset>'
            return getter(url)
        self.collect(source, getter=sitemap_get)
        self.assertEqual(Article.objects.count(), 1)
        published = Article.objects.get().published_at
        self.assertTrue(published is None or published.year != 2020)
        self.assertEqual(CollectionRun.objects.get().stats["discovery_pages"], 2)

    def test_failed_refresh_keeps_saved_text(self):
        source = mk()
        self.collect(source)
        Article.objects.update(fetched_at=timezone.now()-timedelta(days=2))
        saved_fetch_dates = dict(Article.objects.values_list("pk", "fetched_at"))
        def unavailable(url):
            if url == source.entry_url:
                return getter(url)
            raise FetchError("http_503")
        stats = self.collect(source, getter=unavailable)
        self.assertEqual(stats["errors"], 3)
        self.assertEqual(Article.objects.filter(status="fetched").count(), 3)
        self.assertTrue(all(a.text for a in Article.objects.all()))
        self.assertEqual(dict(Article.objects.values_list("pk", "fetched_at")), saved_fetch_dates)
        self.assertEqual(self.collect(source, getter=unavailable)["errors"], 0)


class DiscoveryPolicyTests(TestCase):
    def test_pwr_article_excludes_shared_sidebar(self):
        from collection.extract import extract_article
        body = ("Badacze opracowali nowy materiał budowlany z odzyskanego tworzywa. " * 15)
        document = ('<html><head><title>Nowy materiał</title></head><body>'
                    '<aside><p>REKLAMA MURALU ' + 'Wiadomość z innej strony. ' * 15 + '</p></aside>'
                    '<div class="module-content module-news module-details"><h1>Nowy materiał</h1>'
                    '<p>' + body + '</p></div></body></html>')
        result = extract_article(document, "https://pwr.edu.pl/uczelnia/aktualnosci/material.html")
        self.assertIn("nowy materiał budowlany", result["text"])
        self.assertNotIn("REKLAMA MURALU", result["text"])

    def test_rss_enforces_scope(self):
        source = mk(discovery_type="rss")
        text = '<rss><channel><item><link>https://evil.example/x</link></item><item><link>https://example.org/news/a1</link></item></channel></rss>'
        self.assertEqual(discover(text, source), [("https://example.org/news/a1", None)])

    def test_sitemap_lastmod_is_only_a_change_hint(self):
        source = mk(discovery_type="sitemap")
        self.assertIsNone(discover((FX / "sitemap.xml").read_text(encoding="utf-8"), source)[0][1])

    def test_bad_port_and_credentials_are_rejected(self):
        self.assertFalse(is_safe_url("http://example.org:invalid/"))
        self.assertFalse(is_safe_url("https://user:password@example.org/"))

    def test_robots_disallow_prevents_article_download(self):
        _ROBOTS.clear()
        try:
            with mock.patch("collection.netsafe.is_safe_url", return_value=True), mock.patch("collection.netsafe._download", return_value=("https://example.org/robots.txt", "User-agent: *\nDisallow: /news/")) as download:
                with self.assertRaisesRegex(FetchError, "robots_disallowed"):
                    from collection.netsafe import _robots_delay
                    _robots_delay("https://example.org/news/a1")
                self.assertEqual(download.call_count, 1)
        finally:
            _ROBOTS.clear()


class DashboardTests(TestCase):
    def test_status_history_and_invalid_filter_render(self):
        source = mk()
        run_source(source, getter=getter, sleep=lambda _: None)
        for url in ["/", "/?source=invalid", "/zrodla/", "/przebiegi/", "/health/", "/api/status/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/api/status/").json()["articles"], 2)
        self.assertContains(self.client.get("/przebiegi/"), "Zakończony")

    def test_manual_scan_requires_staff_and_only_changes_schedule(self):
        source = mk(next_run_at=timezone.now()+timedelta(hours=1))
        self.assertEqual(self.client.post(f"/zrodla/{source.pk}/sprawdz/").status_code, 302)
        source.refresh_from_db()
        self.assertGreater(source.next_run_at, timezone.now())
        user = get_user_model().objects.create_user(username="test-staff", password="test-only", is_staff=True)
        self.client.force_login(user)
        response = self.client.post(f"/zrodla/{source.pk}/sprawdz/")
        self.assertEqual(response.status_code, 302)
        source.refresh_from_db()
        self.assertLessEqual(source.next_run_at, timezone.now())
        self.assertEqual(CollectionRun.objects.count(), 0)
