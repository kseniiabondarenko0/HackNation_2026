"""Gemini analysis of one article: compact prompt, JSON schema, strict validation against the text.

Data the system can verify (page URL, date from page metadata, quotes found verbatim in the text) is kept apart
from what the model interpreted (score, explanation, sector...): data["verified"] vs data["ai"]. The other keys
mirror analysis.core.finalize, so listings, filters and the detail page keep working.
"""
import re
from datetime import date

from django.conf import settings

from collection.window import cutoff, to_date
from . import llm, regions, rules
from .core import PATHS, SIGNALS, STAGES, VERDICTS, norm, priority, signal_level, thresholds, verify_quote

AI_VERSION = "1"
SECTORS = [*rules.SECTORS, "Inne"]
TYPES = [*rules.INNOVATION_TYPES, "nieokreślony"]
CAVEAT = ("Ocena wygenerowana przez model Gemini na podstawie tekstu źródła: to interpretacja AI, a nie "
          "potwierdzony fakt. Zweryfikowane są tylko dane ze strony i cytaty występujące w tekście.")
SYSTEM = (
    "Jesteś analitykiem Podkarpackiego Centrum Innowacji. Oceniasz, czy tekst opisuje konkretną innowację "
    "(rozwiązanie, projekt, wdrożenie, prototyp, produkt, metodę) polskiej szkoły, uczelni, samorządu lub "
    "instytucji publicznej, i jaki ma potencjał. Zasady: "
    "1) Opieraj się WYŁĄCZNIE na podanym tekście; niczego nie zmyślaj (fakty, daty, nazwiska, źródła). "
    "2) score 0-100 = nowatorstwo, udokumentowane wyniki lub wdrożenie, możliwość przeniesienia/skalowania. "
    "Wydarzenia, ogłoszenia, rekrutacje, relacje, reklamy, akty prawne i programy finansowania bez konkretnego "
    "rozwiązania to is_initiative=false i score<=20. Innowacją może być też rozwiązanie edukacyjne, organizacyjne "
    "lub administracyjne, prototyp, pilotaż albo projekt studencki z konkretnym wynikiem: oceniaj udokumentowane "
    "wdrożenie i potencjał, nie tylko technologię; wiek publikacji sam nie obniża oceny. "
    "3) evidence: 1-4 DOSŁOWNE cytaty z tekstu (min. 20 znaków), które uzasadniają ocenę. "
    "4) missing_info: czego w tekście brakuje do rzetelnej oceny. "
    "5) uncertainty: jedno zdanie o niepewności oceny. "
    "6) published_date (RRRR-MM-DD) tylko gdy data jest w tekście, a date_evidence to dosłowny fragment z datą; "
    "inaczej null. "
    "7) credibility: wysoka = oficjalna instytucja i konkretne dane; niska = reklama, brak konkretów, nieznane źródło. "
    "8) trl (1-9, skala gotowości technologicznej) tylko gdy tekst opisuje stan gotowości rozwiązania "
    "technologicznego (1 idea, 4 walidacja w laboratorium, 6 prototyp w warunkach zbliżonych do rzeczywistych, "
    "7 demonstracja, 9 użytkowane); dla rozwiązań edukacyjnych i administracyjnych oraz bez danych null. "
    "Odpowiadaj po polsku, zwięźle: summary do 250 znaków, explanation do 600 znaków.")


def _arr(item):
    return {"type": "ARRAY", "items": item}


SCHEMA = {"type": "OBJECT", "properties": {
    "is_initiative": {"type": "BOOLEAN"}, "score": {"type": "INTEGER"},
    "summary": {"type": "STRING"}, "explanation": {"type": "STRING"},
    "evidence": _arr({"type": "STRING"}), "missing_info": _arr({"type": "STRING"}),
    "uncertainty": {"type": "STRING"},
    "sector": {"type": "STRING", "enum": SECTORS},
    "innovation_types": _arr({"type": "STRING", "enum": TYPES}),
    "stage": {"type": "STRING", "enum": list(STAGES)}, "trl": {"type": "INTEGER", "nullable": True},
    "path": {"type": "STRING", "enum": [*PATHS, "brak"]},
    "authors": _arr({"type": "STRING"}),
    "published_date": {"type": "STRING", "nullable": True}, "date_evidence": {"type": "STRING", "nullable": True},
    "credibility": {"type": "STRING", "enum": ["wysoka", "srednia", "niska"]},
    "credibility_reason": {"type": "STRING"}},
    "required": ["is_initiative", "score", "summary", "explanation", "evidence", "missing_info", "uncertainty",
                 "sector", "innovation_types", "stage", "path", "credibility", "credibility_reason"]}


def clean_text(text):
    """Whitespace-normalised text cut at a paragraph/sentence boundary: the only text that is sent to the model."""
    text = re.sub(r"[ \t ]+", " ", text or "")
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    limit = settings.LLM["MAX_TEXT_CHARS"]
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind("\n"), head.rfind(". "))
    return head[:cut + 1] if cut > limit // 2 else head


def build_prompt(article, text):
    src = article.source
    pub = to_date(article.published_at)
    window = (f" Akceptujemy tylko inicjatywy opublikowane od {cutoff():%Y-%m-%d}." if settings.ANALYSIS["WINDOW_MONTHS"] > 0 else "")
    return (f"Dzisiaj: {date.today():%Y-%m-%d}.{window}\n"
            f"Źródło: {src.name} ({src.get_organization_type_display()}), adres: "
            f"{article.final_url or article.original_url}\n"
            f"Data publikacji ze strony: {pub.isoformat() if pub else 'brak'}\n"
            f"Tytuł: {article.title}\nTekst:\n{text}")


def _date(value):
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def resolve_date(article, raw, text):
    """(date | None, origin). Page metadata first; a date found by the model counts only if its quote is in the text."""
    pub = to_date(article.published_at)
    if pub:
        return pub, "metadane strony"
    found, evidence = _date(raw.get("published_date")), (raw.get("date_evidence") or "").strip()
    if found and found <= date.today() and len(evidence) >= 6 and norm(evidence) in norm(text) \
            and str(found.year) in evidence:
        return found, "treść artykułu"
    return None, ""


def decide(is_initiative, score, pub, credibility, quotes, reason):
    """Verdict: glowna (published) only for a confirmed, recent, well-scored initiative from a credible source."""
    months, main = settings.ANALYSIS["WINDOW_MONTHS"], thresholds()["main"]
    if months > 0 and pub and pub < cutoff():
        vid, why = "odrzucone", f"Publikacja z {pub:%d.%m.%Y} jest starsza niż {months} mies. (granica {cutoff():%d.%m.%Y})."
        return {"id": vid, "label": VERDICTS[vid], "reason": why, "window": True}   # archived before removal
    elif not is_initiative:
        vid, why = "odrzucone", "Tekst nie opisuje konkretnej innowacji. " + reason
    elif score is None:
        vid, why = "weryfikacja", "Model nie podał oceny punktowej."
    elif score < main:
        vid, why = "odrzucone", f"Ocena {score}/100 poniżej progu publikacji ({main})."
    elif credibility == "niska":
        vid, why = "weryfikacja", "Niska wiarygodność źródła lub opisu: wymaga weryfikacji."
    elif not quotes:
        vid, why = "weryfikacja", "Brak cytatu z tekstu potwierdzającego ocenę."
    else:
        vid, why = "glowna", (f"Potwierdzona inicjatywa{f' z {pub:%d.%m.%Y}' if pub else ' (data publikacji nieustalona)'}; ocena {score}/100 (próg {main}), "
                              f"wiarygodność: {credibility}.")
    return {"id": vid, "label": VERDICTS[vid], "reason": why}


def finalize_ai(raw, article):
    """Validate the model's answer against the article text and build the stored analysis data."""
    text = article.text
    nt = norm(text)
    raw = raw or {}
    is_initiative = raw.get("is_initiative") is True
    score = raw.get("score") if isinstance(raw.get("score"), int) and 0 <= raw["score"] <= 100 else None
    quotes = [q for q in dict.fromkeys(raw.get("evidence") or []) if isinstance(q, str) and verify_quote(text, q)][:4]
    dropped = len([q for q in raw.get("evidence") or [] if q]) - len(quotes)
    pub, origin = resolve_date(article, raw, text)
    credibility = raw.get("credibility") if raw.get("credibility") in ("wysoka", "srednia", "niska") else "niska"
    explanation, summary = (raw.get("explanation") or "").strip()[:700], (raw.get("summary") or "").strip()[:300]
    stage = raw.get("stage") if raw.get("stage") in STAGES else "unknown"
    sector = raw.get("sector") if raw.get("sector") in SECTORS else "Inne"
    trl = raw.get("trl") if isinstance(raw.get("trl"), int) and not isinstance(raw.get("trl"), bool) and 1 <= raw["trl"] <= 9 else None
    missing = [m.strip()[:200] for m in raw.get("missing_info") or [] if isinstance(m, str) and m.strip()][:6]
    verdict = decide(is_initiative, score, pub, credibility, quotes, explanation[:160])
    region = regions.resolve(text)
    prio, prio_reasons = priority(sector, region["code"])
    level = signal_level(len(quotes))
    path_id = raw.get("path") if raw.get("path") in PATHS else None
    return {
        "lead": summary, "sector": sector, "stage": stage, "stage_label": STAGES[stage],
        "authors": [a for a in dict.fromkeys(raw.get("authors") or []) if isinstance(a, str) and norm(a) in nt][:5],
        "signal": level, "signal_label": SIGNALS[level], "signal_terms": [], "market": "",
        "criteria": [], "potential": score, "known": len(quotes), "total": 4,
        "completeness": min(100, 25 * len(quotes)),
        "path": ({"id": path_id, "label": PATHS[path_id], "missing": missing[:4],
                  "reasons": [f"Etap: {STAGES[stage]}", f"Ocena potencjału {score}/100 (Gemini)"]}
                 if path_id and score is not None else None),
        "dropped": [f"{dropped} cytat(ów) niewystępujących w tekście"] if dropped > 0 else [],
        "relevance": {"is_solution": is_initiative, "reason": explanation[:200], "evidence": quotes, "noise": []},
        "verdict": verdict, "priority": prio, "priority_reasons": prio_reasons, "region": region,
        "innovation_types": [t for t in raw.get("innovation_types") or [] if t in TYPES][:2] or ["nieokreślony"],
        "caveat": CAVEAT,
        # What the system can verify vs what the model interpreted (kept apart on purpose).
        "verified": {"url": article.final_url or article.original_url, "source": article.source.name,
                     "organization_type": article.source.get_organization_type_display(),
                     "published_at": pub.isoformat() if pub else "", "date_source": origin,
                     "quotes": quotes},
        "ai": {"provider": "", "model": "", "is_initiative": is_initiative, "score": score,
               "summary": summary, "explanation": explanation, "uncertainty": (raw.get("uncertainty") or "")[:300],
               "missing_info": missing, "credibility": credibility, "trl": trl,
               "credibility_reason": (raw.get("credibility_reason") or "")[:300]},
    }


def analyze(article):
    """Analysis data for one article. Out-of-window dates are rejected before any paid call."""
    if settings.ANALYSIS["WINDOW_MONTHS"] > 0 and (pub := to_date(article.published_at)) and pub < cutoff():
        return finalize_ai({}, article)
    raw, meta = llm.complete_json(SYSTEM, build_prompt(article, clean_text(article.text)), SCHEMA)
    data = finalize_ai(raw, article)
    data["ai"].update(provider=meta["provider"], model=meta["model"], tokens=[meta["in"], meta["out"]])
    return data
