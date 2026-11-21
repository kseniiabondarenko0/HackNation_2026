import hashlib, re
from datetime import datetime, timezone
import trafilatura


def extract_article(html: str, url: str):
    """Return dict(title, text, published_at) or None when no main text is found."""
    data = trafilatura.bare_extraction(html, url=url, with_metadata=True, favor_precision=True)
    if not data:
        return None
    d = data if isinstance(data, dict) else data.as_dict()
    text = (d.get("text") or "").strip()
    pub = None
    if d.get("date"):
        try:
            pub = datetime.fromisoformat(d["date"]).replace(tzinfo=timezone.utc)
        except ValueError:
            pub = None
    return {"title": (d.get("title") or "").strip(), "text": text, "published_at": pub}


def content_hash(text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
