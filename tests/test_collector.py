from pathlib import Path
from unittest import mock
from django.test import TestCase
from collection.models import Source, Article
from collection.discovery import discover, normalize_url
from collection.netsafe import is_safe_url, FetchError
from collection.services import run_source

FX = Path(__file__).parent / "fixtures"
PAGES = {
    "https://example.org/news/": "listing.html", "https://example.org/news/a1": "a1.html",
    "https://example.org/news/a2": "a2.html", "https://example.org/news/a1-copy": "a1_copy.html",
}


def getter(url):
    if url in PAGES:
        return url, (FX / PAGES[url]).read_text(encoding="utf-8")
    raise FetchError("http_404")


def mk(**kw):
    d = dict(name="T", entry_url="https://example.org/news/", discovery_type="html", allowed_prefix="https://example.org/news/")
    d.update(kw)
    return Source.objects.create(**d)


class DiscoveryTests(TestCase):
    def test_html_filters_prefix_ext_and_tracking(self):
        urls = [u for u, _ in discover((FX / "listing.html").read_text(encoding="utf-8"), mk())]
        self.assertEqual(sorted(urls), ["https://example.org/news/a1", "https://example.org/news/a1-copy", "https://example.org/news/a2"])

    def test_rss_with_date(self):
        (u, pub), = discover((FX / "feed.xml").read_text(encoding="utf-8"), mk(discovery_type="rss"))
        self.assertEqual(u, "https://example.org/news/a1"); self.assertEqual(pub.year, 2025)

    def test_sitemap_prefix_filter(self):
        urls = [u for u, _ in discover((FX / "sitemap.xml").read_text(encoding="utf-8"), mk(discovery_type="sitemap"))]
        self.assertEqual(urls, ["https://example.org/news/a2"])

    def test_normalize_strips_fragment_and_tracking_keeps_real_params(self):
        self.assertEqual(normalize_url("HTTPS://Example.org/p?id=3&utm_source=x#frag"), "https://example.org/p?id=3")


class RunTests(TestCase):
    def setUp(self):
        # listing links are relative in the fixture; give the getter an absolute version
        self.listing = (FX / "listing.html").read_text(encoding="utf-8")

    def run_it(self, s):
        return run_source(s, getter=getter, sleep=lambda _: None)

    def test_end_to_end_no_manual_url_and_dedup(self):
        s = mk()
        st = self.run_it(s)
        self.assertEqual(st["discovered"], 3)
        self.assertEqual(Article.objects.filter(status="fetched").count(), 3)
        dups = Article.objects.filter(duplicate_of__isnull=False)
        self.assertEqual(dups.count(), 1)  # a1-copy has identical text
        self.assertIsNotNone(Article.objects.get(original_url="https://example.org/news/a1").fetched_at)

    def test_rerun_creates_no_duplicates_and_no_refetch(self):
        s = mk(); self.run_it(s)
        calls = []
        def counting(url):
            calls.append(url); return getter(url)
        st = run_source(s, getter=counting, sleep=lambda _: None)
        self.assertEqual(Article.objects.count(), 3)
        self.assertEqual(st["new"], 0)
        self.assertEqual(calls, ["https://example.org/news/"])  # only the listing, no article refetch

    def test_source_failure_is_recorded_not_raised(self):
        s = mk(entry_url="https://example.org/missing/", allowed_prefix="https://example.org/missing/")
        st = self.run_it(s); s.refresh_from_db()
        self.assertEqual(st["errors"], 1); self.assertIn("http_404", s.last_error)

    def test_article_error_does_not_stop_others(self):
        s = mk()
        def flaky(url):
            if url.endswith("a2"): raise FetchError("http_429")
            return getter(url)
        st = run_source(s, getter=flaky, sleep=lambda _: None)
        self.assertEqual(st["errors"], 1)
        self.assertEqual(Article.objects.filter(status="error").count(), 1)
        self.assertGreaterEqual(Article.objects.filter(status="fetched").count(), 2)


class SafetyTests(TestCase):
    def test_blocks_private_and_bad_schemes(self):
        for u in ["http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.5/", "http://169.254.169.254/", "file:///etc/passwd", "ftp://example.org/"]:
            self.assertFalse(is_safe_url(u), u)


class WebTests(TestCase):
    def test_pages_render(self):
        s = mk(); run_source(s, getter=getter, sleep=lambda _: None)
        self.assertContains(self.client.get("/"), "Prototyp monitorowania")
        self.assertEqual(self.client.get("/zrodla/").status_code, 200)
