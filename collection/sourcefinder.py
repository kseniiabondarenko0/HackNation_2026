"""Automatic source discovery: search queries -> candidate sites -> probe -> 'kandydat' awaiting an expert.

Every page request goes through ``safe_get`` (SSRF checks, robots.txt, per-host delay, size limits).
Search APIs (SearXNG, Brave) are optional, configured by the administrator, and only return URLs;
the URLs they return are probed like any other untrusted address.
"""
import json
import logging
import re
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx
from django.conf import settings
from django.utils import timezone
from lxml import html as lhtml

from .discovery import discover_html, discover_rss, normalize_url
from .models import DiscoveryRun, Source
from .netsafe import FetchError, robots_info, safe_get

logger = logging.getLogger(__name__)
DATA = Path(__file__).resolve().parent / "data"

NEWS_HINTS = ("aktualnosci", "aktualności", "wiadomosci", "wiadomości", "news", "komunikaty",
              "informacje-prasowe", "wydarzenia", "blog")
RELEVANCE = {"innowac": 3, "transfer technologii": 4, "transferu technologii": 4, "komercjaliz": 4,
             "wdroż": 3, "wdroz": 3, "startup": 2, "start-up": 2, "patent": 2, "spin-off": 3, "spin off": 3,
             "park naukowo": 3, "park technolog": 3, "inkubator": 2, "projekt pilotaż": 3, "pilotaż": 2,
             "badania": 1, "naukow": 1, "przedsiębior": 1, "współpraca z biznesem": 3}
BLOCKED_HOSTS = ("facebook.com", "youtube.com", "linkedin.com", "twitter.com", "x.com", "instagram.com",
                 "tiktok.com", "wikipedia.org", "google.com", "google.pl", "onet.pl", "wp.pl", "interia.pl",
                 "gazeta.pl", "money.pl", "tvn24.pl", "rp.pl", "pb.pl", "businessinsider.com.pl",
                 "allegro.pl", "olx.pl", "pracuj.pl", "bip.gov.pl")
GENERIC_TITLE = ("strona główna", "aktualności", "wiadomości", "home", "news", "start", "aktualnosci")
ORG_RULES = [("ctt", ("transfer technologii", "transferu technologii", "ctt.", "cittru", "uott", "cziitt")),
             ("tech_park", ("park naukowo", "park technolog", "technopark", "pnt.", "ppnt", "gpnt", "kpt.", "lpnt")),
             ("research", ("instytut", "lukasiewicz", "łukasiewicz", "pan.pl")),
             ("university", ("uniwersytet", "politechnika", "akademia", "uczelnia", ".edu.pl")),
             ("agency", (".gov.pl", "agencja", "narodowe centrum", "fundacja na rzecz nauki")),
             ("local_gov", ("urząd miasta", "urząd marszałkowski", "powiat", "gmina"))]


def cfg():
    return settings.DISCOVERY


def host_of(url):
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_candidate_host(host):
    if not host or not any(host.endswith(tld) for tld in cfg()["ALLOWED_TLDS"]):
        return False
    return not any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def known_hosts():
    hosts = set()
    for entry, feed in Source.objects.values_list("entry_url", "feed_url"):
        hosts.update(h for h in (host_of(entry), host_of(feed or "")) if h)
    return hosts


def relevance(text):
    low = (text or "").lower()
    return sum(min(low.count(k), 3) * w for k, w in RELEVANCE.items())


def classify(host, title, text=""):
    # The name (host + title) decides first; page text is only a fallback, because news pages
    # of every institution mention "transfer technologii" or "uczelnia".
    for sample in (f"{host} {title}".lower(), (text or "")[:3000].lower()):
        for org, keys in ORG_RULES:
            if any(k in sample for k in keys):
                return org
    return "other"


def clean_title(title, host):
    parts = [p.strip() for p in re.split(r"\s+[|–—-]\s+|\s*\|\s*", title or "") if p.strip()]
    parts = [p for p in parts if p.lower() not in GENERIC_TITLE] or [host]
    return max(parts, key=len)[:200]


# ---------------------------------------------------------------- search providers
def provider_searxng(query, limit):
    base = cfg()["SEARXNG_URL"]
    if not base:
        return None
    r = httpx.get(base.rstrip("/") + "/search", timeout=15,
                  params={"q": query, "format": "json", "language": "pl"},
                  headers={"User-Agent": settings.COLLECT["USER_AGENT"]})
    r.raise_for_status()
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("content", "")}
            for x in r.json().get("results", [])[:limit]]


def provider_brave(query, limit):
    key = cfg()["BRAVE_API_KEY"]
    if not key:
        return None
    r = httpx.get("https://api.search.brave.com/res/v1/web/search", timeout=15,
                  params={"q": query, "country": "pl", "search_lang": "pl", "count": min(limit, 20)},
                  headers={"X-Subscription-Token": key, "Accept": "application/json"})
    r.raise_for_status()
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("description", "")}
            for x in r.json().get("web", {}).get("results", [])[:limit]]


def _stems(text):
    return {w[:5] for w in re.findall(r"\w+", (text or "").lower()) if len(w) >= 4}


def load_seeds():
    path = DATA / "discovery_seeds.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def provider_seeds(query, limit):
    """Offline fallback: curated list of Polish institutions, ranked by overlap with the query."""
    q = _stems(query)
    ranked = []
    for seed in load_seeds():
        overlap = len(q & _stems(" ".join([seed.get("name", ""), *seed.get("tags", [])])))
        if overlap:
            ranked.append((overlap, seed))
    ranked.sort(key=lambda x: -x[0])
    return [{"url": s["url"], "title": s.get("name", ""), "snippet": ", ".join(s.get("tags", []))}
            for _, s in ranked[:limit]]


def provider_links(getter, limit):
    """Link graph: institutions that monitored sources link to (partners, parks, CTTs)."""
    out, seen = [], set()
    sources = Source.objects.filter(status="active", enabled=True).exclude(entry_url__startswith="https://radar.local")
    for source in sources[:cfg()["MAX_LINK_SOURCES"]]:
        try:
            base, page = getter(source.entry_url)
            doc = lhtml.fromstring(page)
        except Exception as exc:
            logger.info("links provider skipped %s: %s", source.entry_url, exc)
            continue
        for a in doc.xpath(".//a[@href]"):
            try:
                url = normalize_url(urljoin(base, a.get("href", "")))
            except ValueError:
                continue
            host = host_of(url)
            if host in seen or host == host_of(base) or not is_candidate_host(host):
                continue
            seen.add(host)
            out.append({"url": f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/",
                        "title": (a.text_content() or "").strip()[:200], "snippet": f"link z: {source.name}"})
            if len(out) >= limit:
                return out
    return out


QUERY_PROVIDERS = {"searxng": provider_searxng, "brave": provider_brave, "seeds": provider_seeds}


# ---------------------------------------------------------------- probing
def _page_info(base, page):
    doc = lhtml.fromstring(page)
    title = (doc.findtext(".//title") or "").strip()
    feeds = []
    for link in doc.xpath(".//link[@rel='alternate'][@href]"):
        if any(t in (link.get("type") or "").lower() for t in ("rss", "atom")):
            feeds.append(urljoin(base, link.get("href")))
    news = []
    for a in doc.xpath(".//a[@href]"):
        try:
            url = normalize_url(urljoin(base, a.get("href", "")))
        except ValueError:
            continue
        path = urlsplit(url).path.lower().rstrip("/")
        last = path.rsplit("/", 1)[-1]
        if urlsplit(url).netloc == urlsplit(base).netloc and last in NEWS_HINTS:
            news.append(url)
    text = " ".join(doc.xpath("//body//text()"))[:20000]
    return title, list(dict.fromkeys(feeds)), list(dict.fromkeys(news)), text


def _is_listing(url):
    return any(h in urlsplit(url).path.lower() for h in NEWS_HINTS)


def infer_prefix(listing_url, page):
    """Narrowest prefix under which the listing page links to at least 3 articles."""
    p = urlsplit(listing_url)
    root = f"{p.scheme}://{p.netloc}"
    probe = SimpleNamespace(entry_url=listing_url, allowed_prefix=root + "/", discovery_type="html")
    links = [u for u, _ in discover_html(page, probe)]
    own = listing_url.rstrip("/") + "/"
    if sum(u.startswith(own) for u in links) >= 3:
        return own, [u for u in links if u.startswith(own)]
    dirs = Counter()
    for u in links:
        segs = [s for s in urlsplit(u).path.split("/") if s]
        if len(segs) >= 2:
            dirs[root + "/" + "/".join(segs[:-1]) + "/"] += 1
    for prefix, count in dirs.most_common():
        if count >= 3 and any(h in prefix.lower() for h in NEWS_HINTS):
            return prefix, [u for u in links if u.startswith(prefix)]
    if dirs and dirs.most_common(1)[0][1] >= 5:
        prefix = dirs.most_common(1)[0][0]
        return prefix, [u for u in links if u.startswith(prefix)]
    return own, [u for u in links if u.startswith(own)]


def _feed_links(final, body):
    """(prefix, links) when `body` is a feed whose items share one host, else ("", [])."""
    links = [e.get("link") for e in feedparser.parse(body).entries if e.get("link")]
    hosts = Counter(urlsplit(urljoin(final, l)).netloc for l in links)
    if not hosts or hosts.most_common(1)[0][1] < 3:
        return "", []
    prefix = f"{urlsplit(final).scheme}://{hosts.most_common(1)[0][0]}/"
    src = SimpleNamespace(entry_url=final, allowed_prefix=prefix, discovery_type="rss")
    return prefix, [u for u, _ in discover_rss(body, src)]


def _looks_like_feed(page):
    head = (page.decode("utf-8", "ignore") if isinstance(page, bytes) else page)[:600].lower()
    return "<rss" in head or "<feed" in head or "<rdf:rdf" in head


def probe_site(url, getter=None, robots=None):
    """Check that a site can be monitored politely and propose its collector configuration."""
    getter, robots = getter or safe_get, robots or robots_info
    p = urlsplit(url)
    home = f"{p.scheme}://{p.netloc}/"
    report = {"input": url, "ok": False, "errors": [], "entry_url": "", "discovery_type": "html",
              "allowed_prefix": "", "feed_url": "", "sitemap_url": "", "robots_allowed": None,
              "article_links": 0, "sample": [], "title": "", "score": 0, "organization_type": "other",
              "checked_at": timezone.now().isoformat(timespec="seconds")}
    try:
        rob = robots(home)
        report["robots_allowed"] = rob["allowed"]
        report["sitemap_url"] = (rob["sitemaps"] or [""])[0]
        if not rob["allowed"]:
            report["errors"].append("robots.txt blokuje stronę główną")
            return report
    except FetchError as exc:
        report["errors"].append(f"robots: {exc}")
        return report
    page_url, page = None, None
    for candidate in dict.fromkeys([url, home]):
        try:
            page_url, page = getter(candidate)
            break
        except FetchError as exc:
            report["errors"].append(f"{candidate}: {exc}")
    if page is None:
        return report
    if _looks_like_feed(page):  # entry_url is itself a feed
        prefix, found = _feed_links(page_url, page)
        if len(found) >= 3:
            report.update(ok=True, entry_url=page_url, feed_url=page_url, discovery_type="rss", allowed_prefix=prefix,
                          article_links=len(found), sample=found[:3], score=relevance(" ".join(found)))
        else:
            report["errors"].append("kanał RSS ma za mało linków do artykułów")
        return report
    title, feeds, news, text = _page_info(page_url, page)
    report["title"] = clean_title(title, host_of(page_url))
    report["score"] = relevance(f"{title} {text}")
    report["organization_type"] = classify(host_of(page_url), title, text)
    # 1) RSS/Atom feed advertised by the page
    for feed_url in feeds[:2]:
        try:
            final, body = getter(feed_url)
        except FetchError as exc:
            report["errors"].append(f"feed: {exc}")
            continue
        prefix, found = _feed_links(final, body)
        if len(found) >= 3:
            report.update(ok=True, entry_url=final, feed_url=final, discovery_type="rss",
                          allowed_prefix=prefix, article_links=len(found), sample=found[:3])
            return report
    # 2) HTML news listing: the page itself, or a "news" link found on it
    listings = ([page_url] if _is_listing(page_url) else []) + news[:3]
    for listing_url in listings:
        try:
            final, body = (page_url, page) if listing_url == page_url else getter(listing_url)
        except FetchError as exc:
            report["errors"].append(f"{listing_url}: {exc}")
            continue
        prefix, found = infer_prefix(final, body)
        if len(found) >= 3:
            report.update(ok=True, entry_url=final, discovery_type="html", allowed_prefix=prefix,
                          article_links=len(found), sample=found[:3])
            if not report["score"]:
                report["score"] = relevance(body)
            return report
    report["errors"].append("nie znaleziono listy publikacji (RSS ani strony z aktualnościami)")
    return report


def apply_probe(source, report):
    """Store a probe result on a source. Never silently changes a source that already has articles."""
    source.probe_report, source.probed_at = report, timezone.now()
    source.robots_allowed = report["robots_allowed"]
    if report["sitemap_url"]:
        source.sitemap_url = report["sitemap_url"]
    if report["ok"]:
        source.feed_url = report["feed_url"] or source.feed_url
        if not source.articles.exists() and not Source.objects.filter(
                entry_url=report["entry_url"]).exclude(pk=source.pk).exists():
            source.entry_url, source.discovery_type = report["entry_url"], report["discovery_type"]
            source.allowed_prefix = report["allowed_prefix"]
    elif report["robots_allowed"] is False:
        source.enabled = False
        source.last_error = "Wyłączone: robots.txt nie pozwala na zbieranie."
    else:
        source.last_error = "Weryfikacja nieudana: " + "; ".join(report["errors"])[:400]
    source.save()
    return source


# ---------------------------------------------------------------- discovery run
def run_discovery(queries=None, providers=None, limit=None, getter=None, robots=None, dry_run=False, log=None):
    c = cfg()
    queries = [q.strip() for q in (queries or c["QUERIES"]) if q.strip()]
    providers = providers or c["PROVIDERS"]
    limit = limit or c["MAX_CANDIDATES"]
    getter = getter or safe_get
    log = log or (lambda msg: logger.info(msg))
    run = DiscoveryRun.objects.create(queries=queries, providers=providers)
    stats = {"hits": 0, "unique_hosts": 0, "known": 0, "probed": 0, "probe_failed": 0,
             "created": 0, "provider_errors": {}, "providers_used": [], "candidates": []}
    try:
        hits = []
        for name in providers:
            if name == "links":
                found = provider_links(getter, c["MAX_PER_QUERY"] * 2)
                hits += [dict(h, provider="links", query="") for h in found]
                stats["providers_used"].append("links")
                continue
            fn = QUERY_PROVIDERS.get(name)
            if fn is None:
                stats["provider_errors"][name] = "nieznany dostawca"
                continue
            for i, query in enumerate(queries):
                try:
                    found = fn(query, c["MAX_PER_QUERY"])
                except Exception as exc:
                    stats["provider_errors"][name] = f"{type(exc).__name__}: {exc}"[:200]
                    break
                if found is None:           # provider not configured (no URL / API key)
                    break
                if name not in stats["providers_used"]:
                    stats["providers_used"].append(name)
                hits += [dict(h, provider=name, query=query) for h in found]
                if name in ("searxng", "brave") and i < len(queries) - 1:
                    time.sleep(c["SEARCH_DELAY_S"])
        stats["hits"] = len(hits)
        known, by_host = known_hosts(), {}
        for h in hits:
            host = host_of(h.get("url", ""))
            if not is_candidate_host(host):
                continue
            if host in known:
                stats["known"] += 1
                continue
            by_host.setdefault(host, h)
        stats["unique_hosts"] = len(by_host)
        for host, h in list(by_host.items())[:c["MAX_PROBES"]]:
            if stats["created"] >= limit:
                break
            stats["probed"] += 1
            try:
                report = probe_site(h["url"], getter=getter, robots=robots)
            except Exception as exc:
                logger.warning("probe failed %s: %s", host, exc)
                report = {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}
            if not report["ok"] or report["score"] < c["MIN_SCORE"]:
                stats["probe_failed"] += 1
                log(f"  odrzucono {host}: " + ("; ".join(report.get("errors", [])) or f"wynik {report.get('score')}"))
                continue
            name = report["title"] or clean_title(h.get("title"), host)
            stats["candidates"].append({"host": host, "name": name, "entry_url": report["entry_url"],
                                        "type": report["discovery_type"], "score": report["score"],
                                        "provider": h["provider"], "query": h["query"]})
            log(f"  kandydat {host}: {name} ({report['discovery_type']}, linków {report['article_links']}, wynik {report['score']})")
            if dry_run or Source.objects.filter(entry_url=report["entry_url"]).exists():
                continue
            Source.objects.create(
                name=name, entry_url=report["entry_url"], allowed_prefix=report["allowed_prefix"],
                discovery_type=report["discovery_type"], organization_type=report["organization_type"],
                feed_url=report["feed_url"], sitemap_url=report["sitemap_url"],
                robots_allowed=report["robots_allowed"], probe_report=report, probed_at=timezone.now(),
                status="candidate", enabled=False, origin="discovery",
                discovery_query=(h["query"] or h["provider"])[:300], discovery_score=report["score"],
                discovered_at=timezone.now(), interval_min=c["CANDIDATE_INTERVAL_MIN"])
            stats["created"] += 1
    except Exception as exc:
        run.error = f"{type(exc).__name__}: {exc}"[:500]
        logger.exception("Discovery run failed")
    finally:
        run.stats, run.finished_at = stats, timezone.now()
        run.save()
    return run


def maybe_run_discovery():
    """Called by the worker: automatic discovery every DISCOVERY_AUTO_HOURS (0 = off)."""
    hours = cfg()["AUTO_HOURS"]
    if hours <= 0:
        return None
    last = DiscoveryRun.objects.order_by("-started_at").first()
    if last and (timezone.now() - last.started_at).total_seconds() < hours * 3600:
        return None
    return run_discovery()


def approve(source):
    Source.objects.filter(pk=source.pk).update(status="active", enabled=True, reviewed_at=timezone.now(),
                                               next_run_at=timezone.now(), last_error="")


def reject(source):
    Source.objects.filter(pk=source.pk).update(status="rejected", enabled=False, reviewed_at=timezone.now())
