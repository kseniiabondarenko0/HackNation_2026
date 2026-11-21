"""Backend-independent analysis logic: rubric, quote verification, path choice.

Every backend returns a raw dict; finalize() is the single place that decides what is
accepted. A criterion keeps its score only if its quote really occurs in the article text.
"""
import re
from django.conf import settings
from . import regions

VERSION = "5"  # 3: PCI priority (sectors aviation/space, automotive; Podkarpacie)
CRITERIA = ("problem", "dowody", "wyniki", "przenosnosc", "gotowosc")
LABELS = {"problem": "Problem", "dowody": "Dowody", "wyniki": "Wyniki",
          "przenosnosc": "Przenośność", "gotowosc": "Gotowość"}
STAGES = {"idea": "Pomysł", "prototype": "Prototyp", "pilot": "Pilotaż",
          "in_use": "Użytkowane", "unknown": "Brak danych"}
PATHS = {"rozwoj": "Rozwój", "transfer": "Transfer", "komercjalizacja": "Komercjalizacja",
         "wdrozenie": "Wdrożenie"}
SIGNALS = {"brak": "brak sygnałów", "niski": "niskie", "sredni": "średnie", "wysoki": "wysokie"}
MIN_QUOTE = 20
# Three areas of the official FAQ, derived from the AI sector (no extra model call): the rest of the sectors is technological.
AREAS = {"technologiczne": "Technologiczne", "edukacyjne": "Edukacyjne", "administracyjne": "Administracyjne"}
_AREA_SECTORS = {"edukacyjne": ["Edukacja"], "administracyjne": ["Administracja i samorząd", "Pomoc społeczna i włączenie"]}


def area_sectors(area):
    """Sector names (Analysis.sector) belonging to an area; None for an unknown area."""
    if area not in AREAS:
        return None
    if area in _AREA_SECTORS:
        return _AREA_SECTORS[area]
    from .rules import SECTORS
    other = {s for v in _AREA_SECTORS.values() for s in v} | {"Inne"}
    return [s for s in SECTORS if s not in other]


def area_of(sector):
    return next((a for a in AREAS if sector in (area_sectors(a) or [])), "")


VERDICTS = {"glowna": "Interesujące", "weryfikacja": "Do weryfikacji", "odrzucone": "Odrzucone"}
# Potential (0-100) thresholds; overridable via settings.ANALYSIS["THRESHOLDS"].
DEFAULT_THRESHOLDS = {"main": 50, "reject": 25, "min_completeness": 60}
# PCI priority areas (task text). Only for ordering — never changes potential or verdict.
PRIORITY_SECTORS = ("Lotnictwo i kosmos", "Motoryzacja", "IT i sztuczna inteligencja", "Zdrowie i medycyna")
def priority(sector, region_code):
    """(points, reasons): +2 PCI priority sector, +1 the priority voivodeship (settings, default podkarpackie)."""
    points, reasons = 0, []
    sectors = settings.ANALYSIS.get("PRIORITY_SECTORS", PRIORITY_SECTORS)
    if sector in sectors:
        points += 2
        reasons.append(f"Obszar priorytetowy PCI: {sector}")
    wanted = settings.ANALYSIS.get("PRIORITY_REGION", "podkarpackie")
    if wanted and region_code == wanted:
        points += 1
        reasons.append(f"Województwo priorytetowe: {wanted}")
    return points, reasons


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


def thresholds():
    return {**DEFAULT_THRESHOLDS, **settings.ANALYSIS.get("THRESHOLDS", {})}


def check_relevance(raw, text):
    """Validate the backend's relevance gate. A positive answer must cite text that really occurs."""
    rel = raw.get("relevance") or {}
    evidence = [q for q in rel.get("evidence") or [] if verify_quote(text, q)][:3]
    is_solution = rel.get("is_solution") if rel.get("is_solution") in (True, False, None) else None
    reason = (rel.get("reason") or "").strip()
    if is_solution is True and not evidence:
        is_solution = None
        reason = "Backend uznał tekst za opis rozwiązania, ale bez cytatu z tekstu; potrzebna weryfikacja."
    if not rel:
        reason = "Backend nie ocenił, czy tekst opisuje rozwiązanie."
    return {"is_solution": is_solution, "reason": reason, "evidence": evidence,
            "noise": list(rel.get("noise") or [])}


def decide(rel, potential, completeness):
    """Verdict for the radar: main list, human review, or rejected. Always with a reason in Polish."""
    t = thresholds()
    if rel["is_solution"] is False:
        vid, reason = "odrzucone", rel["reason"]
    elif rel["is_solution"] is None:
        vid, reason = "weryfikacja", rel["reason"] or "Nie udało się ustalić, czy tekst opisuje rozwiązanie."
    elif potential is None:
        vid, reason = "weryfikacja", "Tekst opisuje rozwiązanie, ale brak danych do oceny potencjału."
    elif potential < t["reject"]:
        vid, reason = "odrzucone", f"Potencjał {potential}/100 poniżej progu odrzucenia ({t['reject']})."
    elif potential >= t["main"] and completeness >= t["min_completeness"]:
        vid, reason = "glowna", (f"Opis rozwiązania; potencjał {potential}/100 (próg {t['main']}), "
                                 f"kompletność dowodów {completeness}%.")
    elif potential >= t["main"]:
        vid, reason = "weryfikacja", (f"Potencjał {potential}/100, ale kompletność dowodów tylko {completeness}% "
                                      f"(wymagane {t['min_completeness']}%).")
    else:
        vid, reason = "weryfikacja", (f"Potencjał {potential}/100 między progiem odrzucenia ({t['reject']}) "
                                      f"a progiem listy głównej ({t['main']}).")
    return {"id": vid, "label": VERDICTS[vid], "reason": reason}


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
    completeness = round(100 * len(known) / len(CRITERIA))
    rel = check_relevance(raw, text)
    region = regions.resolve(text)
    prio, prio_reasons = priority(raw.get("sector") or "Inne", region["code"])
    return {
        "lead": lead, "sector": raw.get("sector") or "Inne", "stage": stage, "stage_label": STAGES[stage],
        "authors": authors, "signal": level, "signal_label": SIGNALS[level], "signal_terms": terms,
        "market": market,
        "criteria": [{"key": k, "label": LABELS[k], **crit[k]} for k in CRITERIA],
        "potential": potential, "known": len(known), "total": len(CRITERIA),
        "completeness": completeness,
        "path": choose_path(crit, stage, market, authors),
        "dropped": dropped,
        "relevance": rel,
        "verdict": decide(rel, potential, completeness),
        "priority": prio, "priority_reasons": prio_reasons, "region": region,
        "innovation_types": [t for t in (raw.get("innovation_types") or ["nieokreślony"]) if isinstance(t, str)][:2],
        "caveat": raw.get("caveat", ""),
    }
