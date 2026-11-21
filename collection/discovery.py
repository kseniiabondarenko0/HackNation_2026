"""Bounded discovery over already downloaded HTML, RSS and sitemap documents."""
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
import re
import feedparser
from lxml import etree, html as lhtml

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip", ".doc", ".docx",
            ".xls", ".xlsx", ".mp4", ".css", ".js", ".ico")


def normalize_url(url):
    p = urlsplit(url.strip())
    q = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                   if k.lower() not in TRACKING])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", q, ""))


def _prefix(source):
    return source.allowed_prefix or source.entry_url.rsplit("/", 1)[0] + "/"


def _ok(url, prefix, entry):
    try:
        p, allowed = urlsplit(url), urlsplit(prefix)
        return (p.scheme in ("http", "https") and not p.username and not p.password
                and p.netloc == allowed.netloc and p.path.startswith(allowed.path)
                and url != normalize_url(entry) and len(url) <= 800
                and not p.path.lower().endswith(SKIP_EXT))
    except ValueError:
        return False


def _unique(items):
    seen = set()
    for url, published in items:
        if url not in seen:
            seen.add(url)
            yield url, published


def discover_rss(text, source):
    out = []
    for entry in feedparser.parse(text).entries:
        link = entry.get("link")
        if not link:
            continue
        url = normalize_url(urljoin(source.entry_url, link))
        if not _ok(url, _prefix(source), source.entry_url):
            continue
        ts = entry.get("published_parsed")
        published = datetime(*ts[:6], tzinfo=timezone.utc) if ts else None
        out.append((url, published))
    return list(_unique(out))


def _xml(text):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    text = re.sub(r'^\s*<\?xml[^>]*\?>', '', text)
    return etree.fromstring(text.encode("utf-8"), parser=parser)


def sitemap_children(text, source):
    root = _xml(text)
    if etree.QName(root).localname != "sitemapindex":
        return []
    origin = urlsplit(source.entry_url)
    links = []
    for node in root.xpath("//*[local-name()='sitemap']/*[local-name()='loc']"):
        url = normalize_url((node.text or "").strip())
        p = urlsplit(url)
        if p.scheme in ("http", "https") and p.netloc == origin.netloc:
            links.append(url)
    return list(dict.fromkeys(links))


def discover_sitemap(text, source):
    root = _xml(text)
    out = []
    for node in root.xpath("//*[local-name()='url']/*[local-name()='loc']"):
        url = normalize_url((node.text or "").strip())
        if _ok(url, _prefix(source), source.entry_url):
            # lastmod is not a publication date.
            out.append((url, None))
    return list(_unique(out))


def discover_html(text, source):
    doc = lhtml.fromstring(text)
    out = []
    for anchor in doc.xpath("self::a[@href] | .//a[@href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            url = normalize_url(urljoin(source.entry_url, href))
        except ValueError:
            continue
        if urlsplit(url).path.rstrip("/") == urlsplit(source.entry_url).path.rstrip("/"):
            continue
        if _ok(url, _prefix(source), source.entry_url):
            out.append((url, None))
    return list(_unique(out))


def discover(text, source):
    return {"rss": discover_rss, "sitemap": discover_sitemap, "html": discover_html}[source.discovery_type](text, source)
