import logging
from datetime import datetime, time as dtime
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from collection.models import Article, Rejected
from collection.services import reject_article
from collection.window import cutoff
from . import ai, llm, llmbase, rules
from . import regions
from .core import VERSION, finalize, priority
from .models import Analysis

logger = logging.getLogger(__name__)

# Backends take (text, title) and return a raw dict; finalize() validates it.
# "ai" (Gemini free tier -> Groq free plan, analysis/llm.py) works on the whole article and decides the verdict itself.
BACKENDS = {"rules": rules.analyze, "ai": None}
MAX_ANALYSIS_ATTEMPTS = 3
last_stats = {}   # outcome of the latest analyze_pending() run, read by the management command


def _key(article, backend):
    if backend == "ai":   # text + prompt version only: switching provider or model never re-spends tokens
        return f"{ai.AI_VERSION}ai:{article.content_hash}:{article.source.region or '-'}"
    return f"{VERSION}:{backend}:{article.content_hash}:{article.source.region or '-'}"


def analyze_article(article, backend=None, force=False, known_key=None):
    """Return (Analysis, created_or_updated). Cached by article text hash + backend + version."""
    backend = backend or settings.ANALYSIS["BACKEND"]
    if backend not in BACKENDS:
        raise ValueError(f"Nieznany backend analizy: {backend}")
    key = _key(article, backend)
    if not force:
        existing = Analysis.objects.filter(article=article).first() if known_key is None else None
        if (existing and existing.input_key == key) or known_key == key:
            return existing, False
    if backend == "ai":
        data = ai.analyze(article)
        if data["verified"]["date_source"] == "treść artykułu" and not article.published_at:
            day = datetime.fromisoformat(data["verified"]["published_at"]).date()
            article.published_at = timezone.make_aware(datetime.combine(day, dtime()))
            article.save(update_fields=["published_at"])
        if data["verdict"]["id"] == "odrzucone" and reject_article(
                article, data["verdict"]["reason"], data["potential"], digest=article.content_hash,
                archive=data["verdict"].get("window", False)):
            return None, True   # only URL, hash and reason stay (Rejected); the text and analysis are gone
    else:
        data = finalize(BACKENDS[backend](article.text, article.title), article.text)
    sub = getattr(article, "submission", None)
    data["region"] = regions.resolve(f"{article.title}\n{article.text}", article.source.region,
                                     sub.region if sub else "")
    data["priority"], data["priority_reasons"] = priority(data["sector"], data["region"]["code"])
    obj, _ = Analysis.objects.update_or_create(article=article, defaults={
        "input_key": key, "backend": backend, "data": data, "potential": data["potential"],
        "completeness": data["completeness"], "path": (data["path"] or {}).get("id", ""),
        "signal": data["signal"], "sector": data["sector"][:40], "stage": data["stage"],
        "verdict": data["verdict"]["id"], "priority": data.get("priority", 0), "region": data["region"]["code"]})
    if data["verdict"]["id"] != "glowna":
        logger.info("Artykuł #%s -> %s: %s", article.pk, data["verdict"]["label"], data["verdict"]["reason"])
    return obj, True


def _analyze_pending_ai(force, max_calls):
    """AI pass: newest first, only the 8-month window, dedup before the call, bounded by the free-tier call budget.

    When no provider is available the articles stay queued; nothing is analysed by a formula instead."""
    stats = {"analyzed": 0, "rejected": 0, "cached": 0, "failed": 0, "stopped": ""}
    last_stats.clear()
    last_stats.update(stats)
    if not llm.chain():
        stats["stopped"] = "brak kluczy AI (GEMINI_API_KEY / GROQ_API_KEY)"
        last_stats.update(stats)
        return 0
    budget = min(max_calls or settings.LLM["MAX_CALLS_PER_RUN"], llm.remaining_calls())
    keys = dict(Analysis.objects.values_list("article_id", "input_key"))
    rejected_hashes = set(Rejected.objects.exclude(content_hash="").values_list("content_hash", flat=True))
    pending = (Article.objects.select_related("source").filter(status="fetched", duplicate_of__isnull=True)
               .exclude(text="").filter(analysis_attempts__lt=MAX_ANALYSIS_ATTEMPTS)
               .filter(Q(published_at__isnull=True) | Q(published_at__gte=timezone.make_aware(
                   datetime.combine(cutoff(), dtime()))))
               .order_by("-published_at", "-pk"))
    calls = 0
    for article in pending.iterator():
        if not force and keys.get(article.pk) == _key(article, "ai"):
            stats["cached"] += 1
            continue
        if article.content_hash in rejected_hashes and reject_article(
                article, "Duplikat odrzuconego tekstu.", digest=article.content_hash):
            stats["rejected"] += 1
            continue
        if calls >= budget:
            stats["stopped"] = ("dostawcy AI wstrzymani lub bez limitu: artykuły czekają w kolejce" if budget == 0
                                else "limit wywołań na przebieg")
            break
        calls += 1
        try:
            obj, _ = analyze_article(article, "ai", force=True)
        except llmbase.LLMError as exc:
            if exc.kind in llmbase.BATCH_ERRORS:
                stats["stopped"] = str(exc)
                logger.warning("Analiza AI wstrzymana (artykuły zostają w kolejce): %s", exc)
                break
            Article.objects.filter(pk=article.pk).update(
                analysis_attempts=article.analysis_attempts + 1, analysis_error=str(exc)[:300])
            stats["failed"] += 1
            continue
        stats["rejected" if obj is None else "analyzed"] += 1
    last_stats.update(stats)
    return stats["analyzed"] + stats["rejected"]


def pipeline_counts():
    """Items per pipeline stage (see Article.pipeline_status); odrzucono = the Rejected registry (URL + hash only)."""
    arts = Article.objects
    no_analysis = Q(analysis__isnull=True)
    published = Q(analysis__verdict="glowna")
    return {
        "znaleziono": arts.filter(status="found").count(),
        "zweryfikowano": arts.filter(status="fetched").filter(no_analysis, analysis_attempts__lt=MAX_ANALYSIS_ATTEMPTS).count(),
        "przeanalizowano": arts.filter(analysis__isnull=False).exclude(published).count(),
        "opublikowano": arts.filter(published).count(),
        "odrzucono": Rejected.objects.count() + arts.filter(status="skipped").count(),
        "błąd": arts.filter(Q(status="error") | (no_analysis & Q(analysis_attempts__gte=MAX_ANALYSIS_ATTEMPTS))).count(),
    }


def analyze_pending(backend=None, force=False, max_calls=None):
    """Analyze fetched, non-duplicate articles lacking an up-to-date analysis. Returns count."""
    backend = backend or settings.ANALYSIS["BACKEND"]
    if backend == "ai":
        return _analyze_pending_ai(force, max_calls)
    keys = dict(Analysis.objects.values_list("article_id", "input_key"))
    by_ai = set(Analysis.objects.filter(backend="ai").values_list("article_id", flat=True))   # never downgraded to rules
    done = 0
    for article in Article.objects.select_related("source").filter(status="fetched", duplicate_of__isnull=True).exclude(text=""):
        if article.pk in by_ai and not force:
            continue
        _, changed = analyze_article(article, backend, force, known_key=keys.get(article.pk, "-"))
        done += int(changed)
    return done
