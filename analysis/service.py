from django.conf import settings
from collection.models import Article
from . import rules
from .core import VERSION, finalize
from .models import Analysis

# Backends take (text, title) and return a raw dict; finalize() validates it.
BACKENDS = {"rules": rules.analyze}


def _key(article, backend):
    return f"{VERSION}:{backend}:{article.content_hash}"


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
    data = finalize(BACKENDS[backend](article.text, article.title), article.text)
    obj, _ = Analysis.objects.update_or_create(article=article, defaults={
        "input_key": key, "backend": backend, "data": data, "potential": data["potential"],
        "completeness": data["completeness"], "path": (data["path"] or {}).get("id", ""),
        "signal": data["signal"], "sector": data["sector"][:40], "stage": data["stage"]})
    return obj, True


def analyze_pending(backend=None, force=False):
    """Analyze fetched, non-duplicate articles lacking an up-to-date analysis. Returns count."""
    backend = backend or settings.ANALYSIS["BACKEND"]
    keys = dict(Analysis.objects.values_list("article_id", "input_key"))
    done = 0
    for article in Article.objects.filter(status="fetched", duplicate_of__isnull=True).exclude(text=""):
        _, changed = analyze_article(article, backend, force, known_key=keys.get(article.pk, "-"))
        done += int(changed)
    return done
