"""Backend-independent analysis logic: rubric, quote verification, path choice.

Every backend returns a raw dict; finalize() is the single place that decides what is
accepted. A criterion keeps its score only if its quote really occurs in the article text.
"""
import re
from django.conf import settings

VERSION = "1"
CRITERIA = ("problem", "dowody", "wyniki", "przenosnosc", "gotowosc")
LABELS = {"problem": "Problem", "dowody": "Dowody", "wyniki": "Wyniki",
          "przenosnosc": "Przenośność", "gotowosc": "Gotowość"}
STAGES = {"idea": "Pomysł", "prototype": "Prototyp", "pilot": "Pilotaż",
          "in_use": "Użytkowane", "unknown": "Brak danych"}
PATHS = {"rozwoj": "Rozwój", "transfer": "Transfer", "komercjalizacja": "Komercjalizacja",
         "wdrozenie": "Wdrożenie"}
SIGNALS = {"brak": "brak sygnałów", "niski": "niskie", "sredni": "średnie", "wysoki": "wysokie"}
MIN_QUOTE = 20


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def verify_quote(text, quote):
    q = norm(quote)
    return len(q) >= MIN_QUOTE and q in norm(text)


def _score(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= 3 else None


def signal_level(count):
    return "brak" if count == 0 else "niski" if count == 1 else "sredni" if count <= 3 else "wysoki"


def choose_path(c, stage, market, authors):
    """Rule-based path with reasons and what is missing. None when data is too thin."""
    sc = lambda k: c[k]["score"] or 0
    missing = [f"{LABELS[k]}: brak danych" for k in CRITERIA if c[k]["score"] is None]
    if sc("wyniki") >= 2 and market:
        pid = "komercjalizacja"
        reasons = [f"Wyniki ocenione na {sc('wyniki')}/3", "W tekście jest sygnał rynkowy (patent, klient, licencja itp.)"]
    elif stage in ("pilot", "in_use") and sc("przenosnosc") >= 2:
        pid = "transfer"
        reasons = [f"Etap: {STAGES[stage]}", f"Przenośność oceniona na {sc('przenosnosc')}/3"]
    elif stage in ("pilot", "in_use"):
        pid = "wdrozenie"
        reasons = [f"Etap: {STAGES[stage]}"]
        missing.append("Brak opisanych warunków przeniesienia do innych jednostek")
    elif stage in ("idea", "prototype"):
        pid = "rozwoj"
        reasons = [f"Etap: {STAGES[stage]}"]
        if authors:
            reasons.append("Publicznie wskazani autorzy: " + ", ".join(authors))
        else:
            missing.append("Brak publicznie wskazanych autorów")
    else:
        return None
    return {"id": pid, "label": PATHS[pid], "reasons": reasons, "missing": missing}


def finalize(raw, text):
    """Validate a backend's raw output against the text and compute derived fields."""
    nt = norm(text)
    crit, dropped = {}, []
    for key in CRITERIA:
        item = (raw.get("criteria") or {}).get(key) or {}
        score, quote = _score(item.get("score")), (item.get("quote") or "").strip()
        if score is not None and not verify_quote(text, quote):
            dropped.append(LABELS[key])
            score = None
        crit[key] = {"score": score, "quote": quote if score is not None else ""}
    weights = settings.ANALYSIS["WEIGHTS"]
    known = [k for k in CRITERIA if crit[k]["score"] is not None]
    total = sum(weights[k] for k in known)
    potential = round(100 * sum(weights[k] * crit[k]["score"] for k in known) / (3 * total)) if total else None
    stage = raw.get("stage") if raw.get("stage") in STAGES else "unknown"
    authors = [a for a in dict.fromkeys(raw.get("authors") or []) if norm(a) in nt][:5]
    terms = [t for t in dict.fromkeys(raw.get("signal_terms") or []) if norm(t) in nt][:12]
    market = raw.get("market") if verify_quote(text, raw.get("market")) else ""
    lead = raw.get("lead") if verify_quote(text, raw.get("lead")) else ""
    level = signal_level(len(terms))
    return {
        "lead": lead, "sector": raw.get("sector") or "Inne", "stage": stage, "stage_label": STAGES[stage],
        "authors": authors, "signal": level, "signal_label": SIGNALS[level], "signal_terms": terms,
        "market": market,
        "criteria": [{"key": k, "label": LABELS[k], **crit[k]} for k in CRITERIA],
        "potential": potential, "known": len(known), "total": len(CRITERIA),
        "completeness": round(100 * len(known) / len(CRITERIA)),
        "path": choose_path(crit, stage, market, authors),
        "dropped": dropped,
        "caveat": raw.get("caveat", ""),
    }
