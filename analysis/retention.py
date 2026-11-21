"""Automatic storage policy. Runs on every collection cycle (worker) and as `manage.py cleanup_storage`.

The base keeps only
  * Interesujące   - AI-confirmed, current innovations (score >= threshold, date inside the window), and
  * Do weryfikacji - a short, bounded queue of unconfirmed items (TTL RETENTION["QUEUE_TTL_HOURS"], max QUEUE_MAX).
Everything else is deleted. Of a deleted item only URL + content hash stay (Rejected) so it is never fetched or paid for
again; those entries expire as well, and the archive of items older than the window is capped.
An item with an unknown date is not dropped before its date was looked up in the primary source.
A SQLite backup is taken before the first deletion of the day (kept: RETENTION["BACKUP_KEEP"])."""
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from collection import archive
from collection.extract import extract_article
from collection.models import Article, Rejected
from collection.netsafe import safe_get
from collection.services import reject_article
from collection.window import cutoff, is_old, to_date
from . import ai
from . import currency
from .models import Analysis
from .service import MAX_ANALYSIS_ATTEMPTS
from .tabs import WAITING

logger = logging.getLogger(__name__)
STAT_KEYS = ("legacy", "old", "rejected", "junk", "expired", "date_checked", "date_resolved", "found_dropped",
             "evicted", "currency_checked", "currency_held", "tombstones_dropped", "backup", "errors")
last_stats = {}
_last_run = [0.0]
MIN_INTERVAL_S = 300          # the worker polls every few seconds; the cleanup itself does not need to


def cfg():
    return settings.RETENTION


# ------------------------------------------------------------------ backup
def backup_dir():
    return settings.ARCHIVE_DIR / "backups"


def backup_db(force=False):
    """Copy of the SQLite database (online backup API, safe while the server runs).

    At most one per BACKUP_EVERY_HOURS unless force. Returns the path, or None when the database is not a file."""
    name = str(connection.settings_dict["NAME"])
    if connection.vendor != "sqlite" or name == ":memory:" or "mode=memory" in name or not Path(name).exists():
        return None
    c, folder = cfg(), backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    existing = sorted(folder.glob("db_*.sqlite3"))
    if not force and existing and time.time() - existing[-1].stat().st_mtime < c["BACKUP_EVERY_HOURS"] * 3600:
        return existing[-1]
    target = folder / f"db_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"
    src, dst = sqlite3.connect(name, timeout=30), sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(folder.glob("db_*.sqlite3"))[:-c["BACKUP_KEEP"]]:
        old.unlink()
    return target


class _Ctx:
    def __init__(self, now, getter, dry):
        self.now, self.getter, self.dry = now, getter, dry
        self.stats = dict.fromkeys(STAT_KEYS, 0)
        self.stats["backup"] = ""
        self._backed = False

    def backup(self):
        """Called before the first deletion. If the backup fails the deletion does not happen."""
        if not (self.dry or self._backed):
            path = backup_db()
            self.stats["backup"] = str(path or "")
            self._backed = True


def _chunks(pks, n=400):
    pks = list(pks)
    for i in range(0, len(pks), n):
        yield pks[i:i + n]


def _drop(pks):
    """Delete rows without leaving a trace (items that were never evaluated)."""
    for chunk in _chunks(pks):
        Article.objects.filter(pk__in=chunk).delete()


def _reason(analysis, default):
    return ((analysis.data or {}).get("verdict") or {}).get("reason") or default


# ------------------------------------------------------------------ steps
def _legacy(ctx):
    """AI mode: analyses made by another backend (the old rule filter) confirm nothing -> the items re-enter the queue.

    They are not analysed again in bulk: the queue is bounded, newest first, within the free AI limits."""
    if settings.ANALYSIS["BACKEND"] != "ai":
        return
    qs = Analysis.objects.exclude(backend="ai").filter(
        verdict__in=("glowna", "weryfikacja"), handling="brak", article__submission__isnull=True)
    n = qs.count()
    if n:
        ctx.backup()
        qs.delete()
        ctx.stats["legacy"] += n


def _window(ctx):
    """Older than the window: the full record goes to the archive FIRST, then the row is removed."""
    old = list(Article.objects.filter(published_at__date__lt=cutoff(), submission__isnull=True)
               .select_related("analysis", "source"))
    if not old:
        return
    ctx.backup()
    if not ctx.dry:
        archive.append(old, f"Starsze niż okno ({cutoff():%d.%m.%Y})")   # OSError -> nothing is deleted
    for a in old:
        reject_article(a, f"Starsze niż okno (publikacja {a.published_at:%d.%m.%Y}).", digest=a.content_hash)
    ctx.stats["old"] += len(old)


def _rejected(ctx):
    """Verdict 'odrzucone' (score below the threshold, not an innovation): nothing but URL + hash is kept."""
    limit = ctx.now - timedelta(hours=cfg()["QUEUE_TTL_HOURS"])
    for a in list(Article.objects.filter(analysis__verdict="odrzucone").select_related("analysis")):
        ctx.backup()
        if hasattr(a, "submission"):   # the submitter sees the result for a while, then it goes as well
            if a.first_seen_at < limit:
                a.delete()
                ctx.stats["rejected"] += 1
            continue
        reject_article(a, _reason(a.analysis, "Odrzucone przez analizę AI."), a.analysis.potential, a.content_hash)
        ctx.stats["rejected"] += 1


def _junk(ctx):
    """Duplicates, pages with too little text, exhausted fetch/analysis errors: the row has no value."""
    qs = (Article.objects.filter(submission__isnull=True).filter(
        Q(duplicate_of__isnull=False) | Q(status="skipped")
        | Q(status="error", fetch_attempts__gte=settings.COLLECT["MAX_ATTEMPTS"])
        | Q(status="fetched", analysis__isnull=True, analysis_attempts__gte=MAX_ANALYSIS_ATTEMPTS)))
    for a in list(qs):
        ctx.backup()
        if a.duplicate_of_id:
            reject_article(a, "Duplikat treści innej publikacji.", digest="")   # no hash: it must not block the original
        elif a.status == "skipped":
            reject_article(a, "Za mało treści artykułu.", digest="")
        elif a.status == "error":
            reject_article(a, "Błąd pobierania.", digest="")
        else:
            reject_article(a, "Analiza AI nieudana: " + (a.analysis_error or "brak odpowiedzi")[:120], digest=a.content_hash)
        ctx.stats["junk"] += 1


def _recheck_date(ctx, article):
    """Look the date up in the primary source. 'found' | 'none' | 'error' | 'skip' (dry run)."""
    if ctx.dry:
        return "skip"
    Article.objects.filter(pk=article.pk).update(date_checks=F("date_checks") + 1)
    try:
        final_url, html = ctx.getter(article.original_url)
        data = extract_article(html, final_url)
    except Exception as exc:
        logger.info("Kontrola daty nieudana (%s): %s", article.original_url, exc)
        return "error"
    ctx.stats["date_checked"] += 1
    if data and data.get("published_at"):
        Article.objects.filter(pk=article.pk).update(published_at=data["published_at"])
        return "found"
    return "none"


def redecide(article):
    """New verdict from the STORED AI answer once the date is known: only the deterministic rule runs, no AI call."""
    analysis = getattr(article, "analysis", None)
    data = (analysis.data if analysis else None) or {}
    if not analysis or analysis.backend != "ai" or not data.get("ai"):
        return None
    pub, ai_part = to_date(article.published_at), data["ai"]
    verdict = ai.decide(ai_part.get("is_initiative") is True, ai_part.get("score"), pub,
                        ai_part.get("credibility") or "niska", (data.get("verified") or {}).get("quotes") or [],
                        (ai_part.get("explanation") or "")[:160])
    data["verdict"] = verdict
    data.setdefault("verified", {}).update(published_at=pub.isoformat() if pub else "",
                                           date_source="metadane strony (kontrola źródła)")
    analysis.data, analysis.verdict = data, verdict["id"]
    analysis.save(update_fields=["data", "verdict", "updated_at"])
    return verdict


def _ttl(ctx):
    """Unconfirmed items live QUEUE_TTL_HOURS. An undated one first gets its date looked up in the primary source."""
    c, limit = cfg(), ctx.now - timedelta(hours=cfg()["QUEUE_TTL_HOURS"])
    fetched = (Article.objects.filter(WAITING, status="fetched", duplicate_of__isnull=True, submission__isnull=True,
                                      first_seen_at__lt=limit).select_related("analysis", "source"))
    checks = 0
    for a in list(fetched):
        if a.published_at is None and a.date_checks < c["DATE_CHECKS"]:
            if checks >= c["DATE_CHECKS_PER_CYCLE"]:
                continue                                    # next cycle
            checks += 1
            outcome = _recheck_date(ctx, a)
            if outcome in ("error", "skip"):
                continue                                    # checked again later (at most DATE_CHECKS times)
            if outcome == "found":
                a = Article.objects.select_related("analysis", "source").get(pk=a.pk)
                ctx.stats["date_resolved"] += 1
                if is_old(a.published_at):
                    ctx.backup()
                    reject_article(a, f"Starsze niż okno (publikacja {a.published_at:%d.%m.%Y}).",
                                   digest=a.content_hash, archive=True)
                    ctx.stats["old"] += 1
                    continue
                verdict = redecide(a)
                if verdict and verdict["id"] == "glowna":
                    continue                                # confirmed after all: leaves the queue
                if verdict and verdict["id"] == "odrzucone":
                    ctx.backup()
                    reject_article(a, verdict["reason"], (a.analysis.data.get("ai") or {}).get("score"), a.content_hash,
                                   archive=bool(verdict.get("window")))
                    ctx.stats["rejected"] += 1
                    continue
        ctx.backup()
        reject_article(a, f"Niepotwierdzone w ciągu {c['QUEUE_TTL_HOURS']} h.", digest=a.content_hash)
        ctx.stats["expired"] += 1
    # links that were found but never fetched, and failing fetches, simply expire without a trace
    stale = list(Article.objects.filter(status__in=("found", "error"), submission__isnull=True, first_seen_at__lt=limit)
                 .values_list("pk", flat=True))
    if stale:
        ctx.backup()
        _drop(stale)
        ctx.stats["found_dropped"] += len(stale)


def _caps(ctx):
    """Bounded queue: fetched items waiting for the AI (QUEUE_MAX) and discovered links (FOUND_MAX); the oldest go first."""
    c = cfg()
    extra = list(Article.objects.filter(status__in=("found", "error"), submission__isnull=True)
                 .order_by("-first_seen_at").values_list("pk", flat=True)[c["FOUND_MAX"]:])
    if extra:
        ctx.backup()
        _drop(extra)
        ctx.stats["found_dropped"] += len(extra)
    waiting = (Article.objects.filter(WAITING, status="fetched", duplicate_of__isnull=True, submission__isnull=True)
               .order_by(F("published_at").desc(nulls_last=True), "-first_seen_at", "-pk"))
    over = list(waiting.select_related("analysis")[c["QUEUE_MAX"]:])
    for a in over:
        ctx.backup()
        reject_article(a, "Kolejka pełna: najstarsze niepotwierdzone odpadają.", digest=a.content_hash)
        ctx.stats["evicted"] += 1


def _currency(ctx):
    """Confirmed items: the source page is re-checked (CURRENCY_DAYS apart, a few per cycle); no age-based removal."""
    if ctx.dry:
        return
    for an in currency.due(ctx.now, cfg()["CURRENCY_PER_CYCLE"]):
        ctx.stats["currency_checked"] += 1
        if currency.check(an, ctx.getter, ctx.now) == "wstrzymano":
            ctx.stats["currency_held"] += 1


def _tombstones(ctx):
    """The registry of removed items expires too: after window + 1 month (12 months without a window)."""
    c = cfg()
    expiry = ctx.now - timedelta(days=31 * (settings.ANALYSIS["WINDOW_MONTHS"] + 1 if settings.ANALYSIS["WINDOW_MONTHS"] > 0 else 12))
    n = Rejected.objects.filter(rejected_at__lt=expiry).delete()[0]
    over = list(Rejected.objects.order_by("-rejected_at", "-pk").values_list("pk", flat=True)[c["TOMBSTONE_MAX"]:])
    for chunk in _chunks(over):
        Rejected.objects.filter(pk__in=chunk).delete()
    ctx.stats["tombstones_dropped"] += n + len(over)


STEPS = (_legacy, _window, _rejected, _junk, _ttl, _caps, _currency, _tombstones)


def cleanup(dry=False, getter=None, now=None, before=None):
    """Apply the storage policy once. dry=True computes the same numbers and rolls everything back.

    before: optional callable run first (inside the transaction of a dry run)."""
    ctx = _Ctx(now or timezone.now(), getter or safe_get, dry)
    with transaction.atomic() if dry else _nullctx():
        if before:
            before()
        for step in STEPS:
            try:
                step(ctx)
            except Exception as exc:   # one failing step (e.g. a full disk for the backup) must not stop the others
                ctx.stats["errors"] += 1
                logger.exception("Czyszczenie bazy: krok %s nieudany: %s", step.__name__, exc)
        if dry:
            transaction.set_rollback(True)
    last_stats.clear()
    last_stats.update(ctx.stats)
    if not dry and any(v for k, v in ctx.stats.items() if k != "backup"):
        logger.info("Czyszczenie bazy: %s", {k: v for k, v in ctx.stats.items() if v})
    return dict(ctx.stats)


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def maybe_cleanup(ran_sources=False, getter=None):
    """Worker hook: after every cycle that collected something, otherwise at most every few minutes."""
    now = time.monotonic()
    if not ran_sources and now - _last_run[0] < MIN_INTERVAL_S:
        return None
    _last_run[0] = now
    return cleanup(getter=getter)


def counts():
    """What the base holds right now (for the status line and the checks): the tabs plus the technical remainder."""
    from .tabs import tab_q
    base = Article.objects.filter(status="fetched", duplicate_of__isnull=True)
    return {"interesujace": base.filter(tab_q("glowna")).count(), "do_weryfikacji": base.filter(tab_q("weryfikacja")).count(),
            "wszystkie": base.filter(tab_q("wszystkie")).count(),
            "znalezione": Article.objects.filter(status="found").count(), "rejestr_usunietych": Rejected.objects.count()}
