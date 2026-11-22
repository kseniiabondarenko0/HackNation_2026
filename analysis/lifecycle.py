"""Invalidate published evidence when the source text changes, retaining the last analysis snapshot."""
from .models import Analysis


def invalidate(article, previous_text):
    analysis = Analysis.objects.filter(article=article).first()
    if analysis is None:
        return
    old = analysis.data or {}
    previous = old.get("_previous") if old.get("stale") else None
    if previous is None:
        previous = {"text": previous_text, "input_key": analysis.input_key,
                    "analyzed_at": analysis.updated_at.isoformat(),
                    "data": {k: v for k, v in old.items() if k != "_previous"}}
    reason = "Treść źródła zmieniła się. Poprzednia ocena i cytaty wymagają nowej analizy."
    analysis.data = {"stale": True, "_previous": previous,
                     "verdict": {"id": "weryfikacja", "label": "Do weryfikacji", "reason": reason}}
    analysis.verdict = "weryfikacja"
    analysis.potential, analysis.completeness = None, 0
    analysis.signal, analysis.sector, analysis.stage, analysis.path, analysis.priority = "brak", "", "", "", 0
    # Keep the old input_key: analyze_pending will detect that this version needs another analysis.
    # Handling fields and their history belong to the innovation and are intentionally preserved.
    analysis.save(update_fields=["data", "verdict", "potential", "completeness", "signal", "sector",
                                 "stage", "path", "priority", "updated_at"])
