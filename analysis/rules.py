"""Deterministic Polish keyword backend: works offline, no LLM. Signals, not verdicts."""
import re

P = lambda p: re.compile(p, re.I)
SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
CAVEAT = ("Analiza regułowa (słowa kluczowe): wskazuje sygnały w tekście, "
          "nie potwierdza innowacyjności ani sukcesu rozwiązania.")

SIGNAL = [P(p) for p in (r"innowacyjn\w*|innowacj\w*", r"nowatorsk\w*", r"prototyp\w*", r"patent\w*",
          r"wdrożono|wdrożeni\w*|wdrożon\w*", r"opracowa\w*", r"pilotaż\w*", r"start-?up\w*", r"wynalaz\w*",
          r"autorsk\w*", r"projekt\w* badawcz\w*", r"unikaln\w*", r"nową technologi\w*")]
CRIT = {
    "problem": P(r"problem|wyzwani|potrzeb|rozwiązać|zapobieg|utrudni|w celu |celem "),
    "dowody": P(r"wdrożono|został\w* wdrożon|przetestowan|zweryfikowan|certyfik|patent|pilotaż|stosowan|zastosowan|wykorzystywan"),
    "wyniki": P(r"\d+\s?%|skuteczn|oszczędn|redukcj|zmniejszy|zwiększy|poprawi|wyniki|wzrosł|spadł"),
    "przenosnosc": P(r"skalowaln|replikow|upowszechn|przeniesi|inn\w+ (miast|szkoł|uczelni|jednostk|gmin)|licencj|partner|uniwersaln"),
}
STAGE_ORDER = [
    ("in_use", P(r"wdrożono|został\w* wdrożon|jest już (stosowan|używan)|użytkowan|funkcjonuje od|działa od|stosowan\w* od")),
    ("pilot", P(r"pilotaż|przetestowan|testowan|faza testow")),
    ("prototype", P(r"prototyp|demonstrator")),
    ("idea", P(r"pomysł|koncepcj|planuj|zamierza|opracowuj")),
]
STAGE_SCORE = {"idea": 1, "prototype": 2, "pilot": 2, "in_use": 3}
MARKET = P(r"patent|licencj|komercjaliz|zamawiając|klient|spin-?off|start-?up|inwestor")
AUTHOR = re.compile(r"\b(?:prof\. dr hab\.|dr hab\.|dr inż\.|mgr inż\.|prof\.|dr|mgr|inż\.)\s+"
                    r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?")
SECTORS = {
    "Zdrowie i medycyna": P(r"zdrow|medycz|pacjent|szpital|terapi|klinicz|rehabilit"),
    "Energia i środowisko": P(r"energi|odnawialn|klimat|środowisk|recykl|odpad|emisj|fotowolta|wodór"),
    "Materiały i budownictwo": P(r"beton|materiał|budow|konstrukc|kompozyt"),
    "IT i sztuczna inteligencja": P(r"sztuczn\w+ inteligencj|\bAI\b|algorytm|oprogramowani|aplikacj|cyber"),
    "Edukacja": P(r"uczni|nauczyci|szkoł|dydakty|edukac|studen"),
    "Rolnictwo i żywność": P(r"rolnic|żywno|upraw|zwierz|agro|hodow|weterynar"),
    "Transport i mobilność": P(r"transport|pojazd|kolej|mobiln|dron|samochod"),
    "Administracja i samorząd": P(r"samorząd|gmin|urząd|mieszkańc|usług\w+ publiczn"),
}


def sentences(text):
    out = (re.sub(r"\s+", " ", s).strip() for s in SPLIT.split(text or ""))
    return [s[:300] for s in out if len(s) >= 25]


def _hits(sents, pattern):
    return [s for s in sents if pattern.search(s)]


def analyze(text, title=""):
    sents = sentences(text)
    criteria = {}
    for key, pattern in CRIT.items():
        found = _hits(sents, pattern)
        criteria[key] = {"score": min(3, len(found)), "quote": found[0]} if found else {"score": None, "quote": ""}
    stage, stage_quote = "unknown", ""
    for name, pattern in STAGE_ORDER:
        found = _hits(sents, pattern)
        if found:
            stage, stage_quote = name, found[0]
            break
    criteria["gotowosc"] = ({"score": STAGE_SCORE[stage], "quote": stage_quote} if stage != "unknown"
                            else {"score": None, "quote": ""})
    market = _hits(sents, MARKET)
    haystack = f"{title}\n{text}"
    counts = {name: len(p.findall(haystack)) for name, p in SECTORS.items()}
    best = max(counts, key=counts.get)
    return {
        "lead": next((s for s in sents if len(s) >= 40), ""),
        "sector": best if counts[best] else "Inne",
        "stage": stage, "criteria": criteria,
        "authors": [m.group(0) for m in AUTHOR.finditer(text or "")][:8],
        "signal_terms": [m.group(0) for p in SIGNAL if (m := p.search(text or ""))],
        "market": market[0] if market else "",
        "caveat": CAVEAT,
    }
