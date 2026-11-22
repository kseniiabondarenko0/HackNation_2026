"""Currency of confirmed items (replaces the old age limit, see the official FAQ): the source page is re-checked from
time to time. A page that keeps failing sends the item back to 'Do weryfikacji'; nothing is deleted because of age."""
from datetime import timedelta

from django.conf import settings

from .models import Analysis


def due(now, limit):
    """Confirmed (glowna) analyses not checked for CURRENCY_DAYS, least recently checked first."""
    c = settings.RETENTION
    cutoff = (now - timedelta(days=c["CURRENCY_DAYS"])).isoformat()
    rows = []
    for an in Analysis.objects.filter(verdict="glowna", backend="ai").select_related("article").order_by("pk"):
        checked = (an.data.get("currency") or {}).get("checked_at", "")
        if checked < cutoff:
            rows.append((checked, an))
    rows.sort(key=lambda r: (r[0], r[1].pk))
    return [an for _, an in rows[:limit]]


def check(an, getter, now):
    """Re-fetch the source page. Returns 'aktywny' | 'niedostepny' | 'wstrzymano' (3 failed checks in a row)."""
    c = settings.RETENTION
    state = dict(an.data.get("currency") or {})
    try:
        getter(an.article.final_url or an.article.original_url)
        state.update(status="aktywny", failures=0)
    except Exception:
        state.update(status="niedostepny", failures=int(state.get("failures", 0)) + 1)
    state["checked_at"] = now.isoformat()
    an.data["currency"] = state
    outcome = state["status"]
    if state["failures"] >= c["CURRENCY_FAILS"] and an.verdict == "glowna":
        reason = (f"Strona źródłowa jest niedostępna w {state['failures']} kolejnych kontrolach: "
                  "sprawdź, czy rozwiązanie jest nadal aktualne.")
        an.data["verdict"] = {**an.data.get("verdict", {}), "id": "weryfikacja", "label": "Do weryfikacji", "reason": reason}
        an.verdict = "weryfikacja"
        outcome = "wstrzymano"
    an.save(update_fields=["data", "verdict", "updated_at"])
    return outcome
