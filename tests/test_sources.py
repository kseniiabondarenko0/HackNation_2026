"""Offline tests for source registry, probing, discovery and candidate review."""
import json
from io import StringIO
from unittest import mock
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from collection import sourcefinder
from collection.models import DiscoveryRun, Source
from collection.netsafe import FetchError
from collection.services import due_sources

ARTICLES = "".join(f'<a href="/aktualnosci/wdrozenie-{i}">Wdrożenie {i}</a>' for i in range(5))
SITES = {
    # site with an RSS feed
    "https://park.example.pl/": '<html><head><title>Strona główna | Park Naukowo-Technologiczny Testowy</title>'
        '<link rel="alternate" type="application/rss+xml" href="/feed/"></head>'
        '<body>Innowacje, transfer technologii i komercjalizacja.</body></html>',
    "https://park.example.pl/feed/": '<?xml version="1.0"?><rss><channel>' + "".join(
        f"<item><title>N{i}</title><link>https://park.example.pl/n/{i}</link></item>" for i in range(4))
        + "</channel></rss>",
    # site with an HTML news listing linked from the home page
    "https://uczelnia.example.pl/": '<html><head><title>Politechnika Testowa</title></head><body>'
        '<a href="/aktualnosci">Aktualności</a> innowacje wdrożenie</body></html>',
    "https://uczelnia.example.pl/aktualnosci": "<html><body>" + ARTICLES + "</body></html>",
    # reachable site without any listing
    "https://pusta.example.pl/": "<html><head><title>Pusta</title></head><body>innowacje</body></html>",
    # monitored source page linking to partners
    "https://known.example.pl/news/": '<html><body><a href="https://park.example.pl/o-nas">Park</a>'
        '<a href="https://www.facebook.com/x">FB</a><a href="https://uczelnia.example.pl/">Uczelnia</a></body></html>',
}


def getter(url):
    if url in SITES:
        return url, SITES[url]
    raise FetchError("http_404")


def robots(url):
    if "zablokowana" in url:
        return {"allowed": False, "sitemaps": [], "crawl_delay": None}
    return {"allowed": True, "sitemaps": [url + "sitemap.xml"], "crawl_delay": 1}


class ProbeTests(TestCase):
    def test_rss_site(self):
        r = sourcefinder.probe_site("https://park.example.pl/", getter=getter, robots=robots)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual((r["discovery_type"], r["feed_url"]), ("rss", "https://park.example.pl/feed/"))
        self.assertEqual(r["organization_type"], "tech_park")
        self.assertEqual(r["title"], "Park Naukowo-Technologiczny Testowy")
        self.assertEqual(r["sitemap_url"], "https://park.example.pl/sitemap.xml")
        self.assertGreater(r["score"], 0)

    def test_feed_as_entry_url(self):
        # regression: an RSS entry_url with an XML declaration used to crash the HTML parser
        r = sourcefinder.probe_site("https://park.example.pl/feed/", getter=getter, robots=robots)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual((r["discovery_type"], r["entry_url"]), ("rss", "https://park.example.pl/feed/"))
        self.assertEqual(r["allowed_prefix"], "https://park.example.pl/")

    def test_html_listing_found_from_home_page_after_404(self):
        r = sourcefinder.probe_site("https://uczelnia.example.pl/stara-strona", getter=getter, robots=robots)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(r["entry_url"], "https://uczelnia.example.pl/aktualnosci")
        self.assertEqual(r["allowed_prefix"], "https://uczelnia.example.pl/aktualnosci/")
        self.assertEqual(r["article_links"], 5)
        self.assertEqual(r["organization_type"], "university")

    def test_robots_block_and_missing_listing(self):
        r = sourcefinder.probe_site("https://zablokowana.example.pl/", getter=getter, robots=robots)
        self.assertFalse(r["ok"]); self.assertFalse(r["robots_allowed"])
        r = sourcefinder.probe_site("https://pusta.example.pl/", getter=getter, robots=robots)
        self.assertFalse(r["ok"]); self.assertIn("nie znaleziono", r["errors"][-1])

    def test_apply_probe_keeps_sources_with_articles_and_disables_on_robots(self):
        s = Source.objects.create(name="U", entry_url="https://uczelnia.example.pl/stara")
        sourcefinder.apply_probe(s, sourcefinder.probe_site(s.entry_url, getter=getter, robots=robots))
        s.refresh_from_db()
        self.assertEqual(s.entry_url, "https://uczelnia.example.pl/aktualnosci")
        b = Source.objects.create(name="B", entry_url="https://zablokowana.example.pl/")
        sourcefinder.apply_probe(b, sourcefinder.probe_site(b.entry_url, getter=getter, robots=robots))
        b.refresh_from_db()
        self.assertFalse(b.enabled); self.assertIn("robots", b.last_error)


@override_settings(DISCOVERY={**settings.DISCOVERY,
                              "SEARXNG_URL": "", "BRAVE_API_KEY": "", "MIN_SCORE": 1, "SEARCH_DELAY_S": 0,
                              "AUTO_APPROVE": False})   # these tests cover manual approval of candidates
class DiscoveryTests(TestCase):
    SEEDS = [{"name": "Park testowy", "url": "https://park.example.pl/", "tags": ["park naukowo-technologiczny"]},
             {"name": "Pusta", "url": "https://pusta.example.pl/", "tags": ["park naukowo-technologiczny"]},
             {"name": "Inne", "url": "https://inne.example.pl/", "tags": ["rolnictwo"]}]

    def run_discovery(self, **kw):
        with mock.patch.object(sourcefinder, "load_seeds", return_value=self.SEEDS):
            return sourcefinder.run_discovery(getter=getter, robots=robots, **kw)

    def test_seed_provider_creates_disabled_candidates(self):
        run = self.run_discovery(queries=["park naukowo-technologiczny aktualności"], providers=["seeds", "brave"])
        self.assertEqual(run.stats["created"], 1)
        self.assertEqual(run.stats["probe_failed"], 1)          # pusta: no listing
        self.assertEqual(run.stats["providers_used"], ["seeds"])  # brave has no key -> skipped
        c = Source.objects.get()
        self.assertEqual((c.status, c.enabled, c.origin), ("candidate", False, "discovery"))
        self.assertEqual(c.discovery_type, "rss")
        self.assertNotIn(c, due_sources())
        self.assertEqual(DiscoveryRun.objects.count(), 1)

    def test_known_and_rejected_hosts_are_not_proposed_again(self):
        Source.objects.create(name="P", entry_url="https://www.park.example.pl/x", status="rejected", enabled=False)
        run = self.run_discovery(queries=["park naukowo-technologiczny"], providers=["seeds"])
        self.assertEqual(run.stats["known"], 1)
        self.assertEqual(Source.objects.filter(status="candidate").count(), 0)

    def test_link_graph_provider_and_dry_run(self):
        Source.objects.create(name="K", entry_url="https://known.example.pl/news/")
        run = self.run_discovery(queries=["x"], providers=["links"], dry_run=True)
        hosts = {c["host"] for c in run.stats["candidates"]}
        self.assertEqual(hosts, {"park.example.pl", "uczelnia.example.pl"})   # facebook filtered
        self.assertEqual(Source.objects.count(), 1)                            # dry run saves nothing

    def test_search_api_provider(self):
        fake = mock.Mock(); fake.json.return_value = {"results": [
            {"url": "https://uczelnia.example.pl/", "title": "PT", "content": ""},
            {"url": "https://example.com/", "title": "not .pl", "content": ""}]}
        with override_settings(DISCOVERY={**sourcefinder.cfg(), "SEARXNG_URL": "http://localhost:8888"}), \
                mock.patch("collection.sourcefinder.httpx.get", return_value=fake) as get:
            run = sourcefinder.run_discovery(queries=["wdrożono innowację uczelnia"], providers=["searxng"],
                                             getter=getter, robots=robots)
        self.assertEqual(get.call_args.kwargs["params"]["q"], "wdrożono innowację uczelnia")
        self.assertEqual(run.stats["created"], 1)
        self.assertEqual(Source.objects.get().discovery_query, "wdrożono innowację uczelnia")

    def test_provider_error_is_recorded(self):
        with override_settings(DISCOVERY={**sourcefinder.cfg(), "BRAVE_API_KEY": "k"}), \
                mock.patch("collection.sourcefinder.httpx.get", side_effect=RuntimeError("boom")):
            run = sourcefinder.run_discovery(queries=["a"], providers=["brave"], getter=getter, robots=robots)
        self.assertIn("boom", run.stats["provider_errors"]["brave"])

    def test_auto_discovery_respects_interval(self):
        with override_settings(DISCOVERY={**sourcefinder.cfg(), "AUTO_HOURS": 0}):
            self.assertIsNone(sourcefinder.maybe_run_discovery())
        DiscoveryRun.objects.create()
        with override_settings(DISCOVERY={**sourcefinder.cfg(), "AUTO_HOURS": 24}):
            self.assertIsNone(sourcefinder.maybe_run_discovery())


class RegistryAndReviewTests(TestCase):
    def test_registry_file_is_valid(self):
        entries = json.loads((sourcefinder.DATA / "sources.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(entries), 25)
        urls = [e["entry_url"] for e in entries]
        self.assertEqual(len(urls), len(set(urls)))
        types = {k for k, _ in Source.ORG}
        for e in entries:
            self.assertTrue(e["entry_url"].startswith("https://"), e)
            self.assertIn(e["organization_type"], types)
        seeds = sourcefinder.load_seeds()
        self.assertTrue(all(sourcefinder.is_candidate_host(sourcefinder.host_of(s["url"])) for s in seeds))

    def test_seed_sources_loads_verified_as_active_and_rest_as_candidates(self):
        call_command("seed_sources", stdout=StringIO())
        entries = json.loads((sourcefinder.DATA / "sources.json").read_text(encoding="utf-8"))
        verified = sum(bool(e.get("verified")) for e in entries)
        self.assertEqual(Source.objects.filter(status="active", enabled=True).count(), verified)
        self.assertEqual(Source.objects.filter(status="candidate", enabled=False).count(), len(entries) - verified)
        call_command("seed_sources", stdout=StringIO())   # idempotent
        self.assertEqual(Source.objects.count(), len(entries))

    def test_probe_command_activates_registry_candidate(self):
        s = Source.objects.create(name="U", entry_url="https://uczelnia.example.pl/", status="candidate",
                                  enabled=False, origin="registry")
        with mock.patch("collection.management.commands.probe_sources.probe_site",
                        side_effect=lambda u: sourcefinder.probe_site(u, getter=getter, robots=robots)):
            call_command("probe_sources", stdout=StringIO())
        s.refresh_from_db()
        self.assertEqual((s.status, s.enabled), ("active", True))
        self.assertEqual(s.entry_url, "https://uczelnia.example.pl/aktualnosci")

    def test_probe_command_rejects_candidate_duplicating_active_source(self):
        twin = Source.objects.create(name="U", entry_url="https://uczelnia.example.pl/aktualnosci", status="active")
        dup = Source.objects.create(name="U (kandydat)", entry_url="https://uczelnia.example.pl/", status="candidate",
                                    enabled=False, origin="registry")
        with mock.patch("collection.management.commands.probe_sources.probe_site",
                        side_effect=lambda u: sourcefinder.probe_site(u, getter=getter, robots=robots)):
            call_command("probe_sources", stdout=StringIO())
        dup.refresh_from_db()
        self.assertEqual((dup.status, dup.enabled), ("rejected", False))
        self.assertIn(f"#{twin.pk}", dup.last_error)

    def test_staff_can_approve_and_reject_from_sources_page(self):
        a = Source.objects.create(name="Kand A", entry_url="https://a.example.pl/", status="candidate", enabled=False)
        b = Source.objects.create(name="Kand B", entry_url="https://b.example.pl/", status="candidate", enabled=False)
        page = self.client.get("/zrodla/")
        self.assertContains(page, "Kandydaci źródeł")
        self.assertNotContains(page, "Zatwierdź</button>")
        self.assertEqual(self.client.post(f"/zrodla/{a.pk}/zatwierdz/").status_code, 302)
        a.refresh_from_db(); self.assertEqual(a.status, "candidate")      # anonymous: nothing changes
        self.client.force_login(get_user_model().objects.create_user("x", is_staff=True))
        self.assertContains(self.client.get("/zrodla/"), "Zatwierdź</button>")
        self.client.post(f"/zrodla/{a.pk}/zatwierdz/"); self.client.post(f"/zrodla/{b.pk}/odrzuc/")
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.status, a.enabled), ("active", True))
        self.assertIn(a, due_sources())
        self.assertEqual((b.status, b.enabled), ("rejected", False))
        self.assertEqual(self.client.post(f"/zrodla/{b.pk}/zatwierdz/").status_code, 404)
