"""Find article links from a source: RSS/Atom, sitemap, or an HTML listing. Pure functions over fetched text."""
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
import feedparser
from lxml import etree, html as lhtml

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".mp4", ".css", ".js")


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", q, ""))


def _prefix(source) -> str:
    return source.allowed_prefix or source.entry_url.rsplit("/", 1)[0] + "/"


def _ok(url, prefix, entry):
    return url.startswith(prefix) and url != entry and not url.lower().endswith(SKIP_EXT)


def discover_rss(text, source):
    feed = feedparser.parse(text)
    out = []
    for e in feed.entries:
        link = e.get("link")
        if not link:
            continue
        ts = e.get("published_parsed") or e.get("updated_parsed")
        pub = datetime(*ts[:6], tzinfo=timezone.utc) if ts else None
        out.append((normalize_url(urljoin(source.entry_url, link)), pub))
    return out


def discover_sitemap(text, source):
    root = etree.fromstring(text.encode("utf-8", errors="replace"), parser=etree.XMLParser(resolve_entities=False, no_network=True))
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    prefix, out = _prefix(source), []
    for u in root.findall(".//s:url", ns):
        loc = (u.findtext("s:loc", namespaces=ns) or "").strip()
        if loc and _ok(normalize_url(loc), prefix, source.entry_url):
            lm = u.findtext("s:lastmod", namespaces=ns)
            pub = None
            if lm:
                try:
                    pub = datetime.fromisoformat(lm.replace("Z", "+00:00"))
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                except ValueError:
                    pub = None
            out.append((normalize_url(loc), pub))
    return out


def discover_html(text, source):
    doc = lhtml.fromstring(text)
    doc.make_links_absolute(source.entry_url)
    prefix, seen, out = _prefix(source), set(), []
    for a in doc.iterfind(".//a[@href]"):
        url = normalize_url(a.get("href"))
        if _ok(url, prefix, normalize_url(source.entry_url)) and url not in seen:
            seen.add(url)
            out.append((url, None))
    return out


def discover(text, source):
    fn = {"rss": discover_rss, "sitemap": discover_sitemap, "html": discover_html}[source.discovery_type]
    return fn(text, source)
