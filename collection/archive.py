"""Archive of articles that leave the current base (older than the window). Append-only gzip JSON Lines.

Written BEFORE a row is deleted: if writing fails nothing is deleted. Bounded: only the newest
RETENTION["ARCHIVE_MAX_RECORDS"] records are kept. Read with: gzip -dc archive/old_articles.jsonl.gz"""
import gzip
import json
from datetime import datetime

from django.conf import settings


def path():
    return settings.ARCHIVE_DIR / "old_articles.jsonl.gz"


def _record(article, reason):
    analysis = getattr(article, "analysis", None)
    return {"archived_at": datetime.now().isoformat(timespec="seconds"), "reason": reason,
            "id": article.pk, "url": article.original_url, "final_url": article.final_url,
            "title": article.title, "text": article.text, "content_hash": article.content_hash,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            "first_seen_at": article.first_seen_at.isoformat() if article.first_seen_at else None,
            "source": {"name": article.source.name, "entry_url": article.source.entry_url},
            "analysis": ({"backend": analysis.backend, "verdict": analysis.verdict, "potential": analysis.potential,
                          "data": analysis.data} if analysis else None)}


def trim(max_records):
    """Keep only the newest max_records records (the archive must not grow without limit). Returns how many were dropped."""
    p = path()
    if not p.exists():
        return 0
    with gzip.open(p, "rb") as fh:
        lines = fh.read().splitlines()
    if len(lines) <= max_records:
        return 0
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wb") as fh:
        fh.write(b"\n".join(lines[-max_records:]) + b"\n")
    tmp.replace(p)
    return len(lines) - max_records


def append(articles, reason):
    """Append the articles; returns how many were written. Raises OSError on failure (callers must not delete then)."""
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(p, "ab") as fh:
        for article in articles:
            fh.write((json.dumps(_record(article, reason), ensure_ascii=False) + "\n").encode("utf-8"))
            n += 1
    if n:
        trim(settings.RETENTION["ARCHIVE_MAX_RECORDS"])
    return n
