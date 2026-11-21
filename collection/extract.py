import hashlib, re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from lxml import html as lhtml
import trafilatura


def _article_document(html, url):
    """Keep PWr's article body and metadata, excluding its shared sidebar news."""
    if urlsplit(url).hostname not in {"pwr.edu.pl", "www.pwr.edu.pl"}:
        return html
    doc = lhtml.fromstring(html)
    sections = doc.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " module-news ")'
                         ' and contains(concat(" ", normalize-space(@class), " "), " module-details ")]')
    if not sections:
        return html
    page = lhtml.Element("html")
    head = doc.find("head")
    if head is not None:
        page.append(head)
    body = lhtml.Element("body")
    body.append(sections[0])
    page.append(body)
    return lhtml.tostring(page, encoding="unicode")


def extract_article(html: str, url: str):
    """Return dict(title, text, published_at) or None when no main text is found."""
    data = trafilatura.bare_extraction(_article_document(html, url), url=url,
                                     with_metadata=True, favor_precision=True)
    if not data:
        return None
    d = data if isinstance(data, dict) else data.as_dict()
    text = (d.get("text") or "").strip()
    pub = None
    if d.get("date"):
        try:
            pub = datetime.fromisoformat(d["date"].replace("Z", "+00:00"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except ValueError:
            pub = None
    return {"title": (d.get("title") or "").strip(), "text": text, "published_at": pub}


def content_hash(text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
