"""Collector: discover -> fetch -> extract -> store. `getter(url) -> (final_url, text)` is injectable for tests."""
import time
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from .discovery import discover
from .extract import extract_article, content_hash
from .models import Article, Source
from .netsafe import safe_get, FetchError


def run_source(source: Source, getter=safe_get, sleep=time.sleep) -> dict:
    c = settings.COLLECT
    stats = {"discovered": 0, "new": 0, "fetched": 0, "duplicates": 0, "skipped": 0, "errors": 0}
    try:
        _, listing = getter(source.entry_url)
        links = discover(listing, source)
    except Exception as e:  # source-level failure must not stop other sources
        source.last_error = f"{type(e).__name__}: {e}"[:500]
        source.next_run_at = timezone.now() + timedelta(minutes=source.interval_min)
        source.save(update_fields=["last_error", "next_run_at"])
        stats["errors"] += 1
        return stats
    stats["discovered"] = len(links)
    pending = []
    for url, pub in links:
        a, created = Article.objects.get_or_create(original_url=url, defaults={"source": source, "published_at": pub})
        if created:
            stats["new"] += 1
        if a.status in ("found", "error") and len(pending) < c["MAX_NEW_PER_RUN"]:
            pending.append(a)
    for a in pending:
        sleep(c["DELAY_S"])
        _fetch_article(a, getter, stats)
    source.last_success = timezone.now()
    source.last_error = ""
    source.next_run_at = source.last_success + timedelta(minutes=source.interval_min)
    source.save(update_fields=["last_success", "last_error", "next_run_at"])
    return stats


def _fetch_article(a: Article, getter, stats):
    try:
        final_url, html = getter(a.original_url)
    except FetchError as e:
        a.status, a.error = "error", str(e)[:300]
        a.save(update_fields=["status", "error"])
        stats["errors"] += 1
        return
    data = extract_article(html, final_url)
    if not data or len(data["text"]) < settings.COLLECT["MIN_TEXT_CHARS"]:
        a.status, a.error, a.final_url = "skipped", "too_little_text", final_url
        a.save(update_fields=["status", "error", "final_url"])
        stats["skipped"] += 1
        return
    h = content_hash(data["text"])
    twin = Article.objects.filter(content_hash=h).exclude(pk=a.pk).first()
    a.final_url, a.title, a.text, a.content_hash = final_url, data["title"], data["text"], h
    a.published_at = a.published_at or data["published_at"]
    a.fetched_at, a.status, a.error, a.duplicate_of = timezone.now(), "fetched", "", twin
    a.save()
    stats["duplicates" if twin else "fetched"] += 1


def due_sources():
    now = timezone.now()
    return Source.objects.filter(enabled=True).filter(models_q_due(now))


def models_q_due(now):
    from django.db.models import Q
    return Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)
