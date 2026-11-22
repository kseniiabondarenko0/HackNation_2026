"""Currency of confirmed items (replaces the old age limit, see the official FAQ): the source page is re-checked from
time to time. A page that keeps failing sends the item back to 'Do weryfikacji'; nothing is deleted because of age."""
from datetime import timedelta

from django.conf import settings

from .models import Analysis


def due(now, limit):
    """Confirmed analyses and previously confirmed items held after an outage, oldest check first."""
    c = settings.RETENTION
    cutoff = (now - timedelta(days=c["CURRENCY_DAYS"])).isoformat()
    rows = []
    for an in Analysis.objects.filter(verdict__in=("glowna", "weryfikacja"), backend="ai").select_related("article").order_by("pk"):
        state = an.data.get("currency") or {}
        if an.verdict != "glowna" and state.get("failures", 0) < c["CURRENCY_FAILS"]:
            continue
        checked = state.get("checked_at", "")
        if checked < cutoff:
            rows.append((checked, an))
    rows.sort(key=lambda r: (r[0], r[1].pk))
    return [an for _, an in rows[:limit]]


def check(an, getter, now):
    """Re-fetch the source page. Returns 'aktywny' | 'niedostepny' | 'wstrzymano' (3 failed checks in a row)."""
    c = settings.RETENTION
    state = dict(an.data.get("currency") or {})
    held = an.verdict == "weryfikacja" and state.get("failures", 0) >= c["CURRENCY_FAILS"]
    try:
        getter(an.article.final_url or an.article.original_url)
        state.update(status="aktywny", failures=0)
        if held and not an.data.get("stale"):
            previous = state.pop("previous_verdict", None)
            if not previous:  # recovery of cards held before this mechanism was introduced
                from .ai import decide
                from collection.window import to_date
                ai = an.data.get("ai") or {}
                previous = decide(ai.get("is_initiative") is True, ai.get("score"), to_date(an.article.published_at),
                                  ai.get("credibility", "niska"), (an.data.get("verified") or {}).get("quotes") or [],
                                  ai.get("explanation", ""))
            an.data["verdict"], an.verdict = previous, previous["id"]
    except Exception:
        state.update(status="niedostepny", failures=int(state.get("failures", 0)) + 1)
    state["checked_at"] = now.isoformat()
    an.data["currency"] = state
    outcome = state["status"]
    if state["failures"] >= c["CURRENCY_FAILS"] and an.verdict == "glowna":
        state["previous_verdict"] = dict(an.data.get("verdict") or {"id": "glowna", "label": "Interesujące", "reason": ""})
        reason = (f"Strona źródłowa jest niedostępna w {state['failures']} kolejnych kontrolach: "
                  "sprawdź, czy rozwiązanie jest nadal aktualne.")
        an.data["verdict"] = {**an.data.get("verdict", {}), "id": "weryfikacja", "label": "Do weryfikacji", "reason": reason}
        an.verdict = "weryfikacja"
        outcome = "wstrzymano"
    an.save(update_fields=["data", "verdict", "updated_at"])
    return outcome
