"""Persistent collection runs, bounded work and per-source recovery."""
import logging
import time
from datetime import timedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from . import archive as archive_mod
from .discovery import discover, sitemap_children
from .extract import extract_article, content_hash
from .models import Article, Source, CollectionRun, Rejected
from .netsafe import safe_get
from .window import is_old, cutoff

logger = logging.getLogger(__name__)


def models_q_due(now):
    return Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)


def due_sources():
    now = timezone.now()
    return Source.objects.filter(enabled=True, status="active").filter(models_q_due(now)).filter(
        Q(locked_until__isnull=True) | Q(locked_until__lte=now)).order_by("next_run_at", "pk")


def reject_article(article, reason, score=None, digest=None, archive=False):
    """Move an article into the compact Rejected registry (URL, hash, reason) and delete the row.

    archive=True (older than the window) appends the full record to the archive FIRST; if that fails nothing is deleted.
    Never touches manual submissions (analysis.retention removes those separately). Returns True when it was rejected."""
    if hasattr(article, "submission"):
        return False
    if archive:
        archive_mod.append([article], reason)
    Rejected.objects.update_or_create(url=article.original_url, defaults={
        "content_hash": article.content_hash if digest is None else digest, "reason": reason[:200], "score": score})
    article.delete()
    return True


def _discover(source, getter, sleep, stats):
    pages, visited, links = [source.entry_url], set(), {}
    while pages and len(visited) < settings.COLLECT["MAX_DISCOVERY_PAGES"]:
        url = pages.pop(0)
        if url in visited:
            continue
        if visited:
            sleep(settings.COLLECT["DELAY_S"])
        visited.add(url)
        _, listing = getter(url)
        stats["discovery_pages"] += 1
        if source.discovery_type == "sitemap":
            pages.extend(u for u in sitemap_children(listing, source) if u not in visited)
        for article_url, published in discover(listing, source):
            links.setdefault(article_url, published)
            if len(links) >= settings.COLLECT["MAX_LINKS_PER_RUN"]:
                return list(links.items())
    return list(links.items())


def run_source(source, getter=None, sleep=time.sleep):
    getter = getter or safe_get
    c, now = settings.COLLECT, timezone.now()
    stats = dict.fromkeys(("discovered", "discovery_pages", "new", "fetched", "updated",
                           "duplicates", "skipped", "errors", "unchanged"), 0)
    claimed = Source.objects.filter(pk=source.pk, enabled=True, status="active").filter(
        Q(locked_until__isnull=True) | Q(locked_until__lte=now)).update(
            locked_until=now + timedelta(seconds=c["LEASE_SECONDS"]))
    if not claimed:
        return {**stats, "busy": True}
    CollectionRun.objects.filter(source=source, status="running").update(
        status="interrupted", finished_at=now, error="Poprzedni proces został przerwany.")
    run = CollectionRun.objects.create(source=source)
    error, status = "", "success"
    deadline = time.monotonic() + c["MAX_RUN_SECONDS"]
    try:
        links = _discover(source, getter, sleep, stats)
        stats["discovered"] = len(links)
        if not links:
            raise ValueError("Nie znaleziono linków do artykułów. Sprawdź typ źródła i prefiks adresu.")
        known_rejected = set(Rejected.objects.filter(url__in=[u for u, _ in links]).values_list("url", flat=True))
        for url, published in links:
            if url in known_rejected:
                stats["rejected_known"] = stats.get("rejected_known", 0) + 1
                continue
            if is_old(published):   # listing already shows the date: no fetch, no storage
                stats["too_old"] = stats.get("too_old", 0) + 1
                continue
            _, created = Article.objects.get_or_create(original_url=url,
                defaults={"source": source, "published_at": published})
            stats["new"] += int(created)
        pending = Article.objects.filter(source=source).filter(
            Q(status="found") | Q(status="error", fetch_attempts__lt=c["MAX_ATTEMPTS"])
        ).filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)).order_by("first_seen_at", "pk")
        pending = list(pending[:c["MAX_NEW_PER_RUN"]])
        room = c["MAX_NEW_PER_RUN"] - len(pending)
        if room:
            old = Article.objects.filter(source=source, status="fetched",
                fetched_at__lte=now - timedelta(hours=c["RECHECK_HOURS"])).filter(
                    Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)).order_by("fetched_at", "pk")
            pending.extend(list(old[:room]))
        for article in pending:
            if time.monotonic() >= deadline:
                break
            sleep(c["DELAY_S"])
            try:
                _fetch_article(article, getter, stats)
            except Exception as exc:
                logger.exception("Article processing failed: %s", article.original_url)
                _mark_error(article, exc, stats)
        if stats["errors"]:
            status = "partial"
            error = f"Błędy artykułów: {stats['errors']}. Szczegóły w dzienniku i na liście źródeł."
    except (KeyboardInterrupt, SystemExit):
        status, error = "interrupted", "Proces zatrzymany; niezakończone artykuły pozostają w kolejce."
        raise
    except Exception as exc:
        stats["errors"] += 1
        status, error = "error", f"{type(exc).__name__}: {exc}"[:500]
        logger.warning("Source failed: %s: %s", source.name, error)
    finally:
        finished = timezone.now()
        run.status, run.error, run.stats, run.finished_at = status, error, stats, finished
        run.save(update_fields=["status", "error", "stats", "finished_at"])
        updates = {"last_checked": finished, "last_error": error, "last_stats": stats,
                   "next_run_at": finished + timedelta(minutes=1 if status == "interrupted" else max(1, source.interval_min)),
                   "locked_until": None}
        if status in ("success", "partial"):
            updates["last_success"] = finished
        Source.objects.filter(pk=source.pk).update(**updates)
        source.refresh_from_db()
    return stats


def _mark_error(article, exc, stats):
    article.error = f"{type(exc).__name__}: {exc}"[:300]
    article.fetch_attempts += 1
    retry_minutes = min(60, 5 * 2 ** min(article.fetch_attempts, 4))
    if article.text and article.fetch_attempts >= settings.COLLECT["MAX_ATTEMPTS"]:
        retry_minutes = settings.COLLECT["RECHECK_HOURS"] * 60
    article.next_retry_at = timezone.now() + timedelta(minutes=retry_minutes)
    if not article.text:
        article.status = "error"
    article.save()
    stats["errors"] += 1


def _fetch_article(article, getter, stats):
    try:
        final_url, html = getter(article.original_url)
        data = extract_article(html, final_url)
    except Exception as exc:
        _mark_error(article, exc, stats)
        return
    if not data or len(data["text"]) < settings.COLLECT["MIN_TEXT_CHARS"]:
        if article.text:
            _mark_error(article, ValueError("Za mało tekstu podczas ponownego sprawdzenia."), stats)
        else:
            article.status, article.error, article.final_url = "skipped", "Za mało treści artykułu.", final_url
            article.save(update_fields=["status", "error", "final_url"])
            stats["skipped"] += 1
        return
    digest = content_hash(data["text"])
    if not article.content_hash:   # new article only: rows already in the base are never removed here
        if is_old(data["published_at"]):
            article.final_url, article.title, article.text = final_url, data["title"][:500], data["text"]
            article.published_at = data["published_at"]   # in memory only: the archive gets the full record
            reject_article(article, f"Starsze niż okno {settings.ANALYSIS['WINDOW_MONTHS']} mies. "
                                    f"(publikacja {data['published_at']:%d.%m.%Y}, granica {cutoff():%d.%m.%Y}).", digest=digest, archive=True)
            stats["too_old"] = stats.get("too_old", 0) + 1
            return
        known = Rejected.objects.filter(content_hash=digest).first()
        if known:   # same text under another URL as an already rejected item
            reject_article(article, "Duplikat odrzuconego tekstu: " + known.reason, digest=digest)
            stats["rejected_known"] = stats.get("rejected_known", 0) + 1
            return
    if article.content_hash == digest:
        article.fetched_at, article.error, article.fetch_attempts, article.next_retry_at = timezone.now(), "", 0, None
        article.save(update_fields=["fetched_at", "error", "fetch_attempts", "next_retry_at"])
        stats["unchanged"] += 1
        return
    was_fetched = bool(article.content_hash)
    twin = Article.objects.filter(content_hash=digest, duplicate_of__isnull=True).exclude(pk=article.pk).order_by("pk").first()
    article.final_url, article.title, article.text = final_url, data["title"][:500], data["text"]
    article.content_hash, article.duplicate_of = digest, twin
    article.published_at = data["published_at"] or article.published_at
    article.fetched_at, article.status, article.error = timezone.now(), "fetched", ""
    article.fetch_attempts, article.next_retry_at = 0, None
    article.save()
    Article.objects.filter(duplicate_of=article).exclude(content_hash=digest).update(duplicate_of=None)
    stats["duplicates" if twin else "updated" if was_fetched else "fetched"] += 1
