"""Deterministic Polish keyword backend: works offline, no LLM. Signals, not verdicts."""
import re

P = lambda p: re.compile(p, re.I)
SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
CAVEAT = ("Analiza regułowa (słowa kluczowe): wskazuje sygnały w tekście, "
          "nie potwierdza innowacyjności ani sukcesu rozwiązania.")

SIGNAL = [P(p) for p in (r"innowacyjn\w*|innowacj\w*", r"nowatorsk\w*", r"prototyp\w*", r"patent\w*",
          r"wdrożono|wdrożeni\w*|wdrożon\w*", r"opracowa\w*", r"pilotaż\w*", r"start-?up\w*", r"wynalaz\w*",
          r"autorsk\w*", r"projekt\w* badawcz\w*", r"unikaln\w*", r"nową technologi\w*")]
# Rubric cues in tiers: a criterion gets the score of the strongest tier found anywhere in the text
# (never the number of matching sentences, which only measured article length).
PROBLEM = P(r"problem\w*|wyzwani\w*|potrzeb\w*|rozwiązać|zapobieg\w*|utrudni\w*|trudnoś\w*|zagrożeni\w*|"
            r"brakuje|niedob[oó]r\w*|uciążliw\w*|kolejk\w*|czeka\w*|izolacj\w*|"
            r"(?:wcześniej|dotychczas|dotąd)\b[^.]{0,60}(?:trzeba|musie\w*|czeka\w*|trwał\w*|brak\w*)")
STAKEHOLDER = P(r"pacjent|mieszkańc|rolnik|firm|przedsiębior|szpital|uczni|lekarz|kierowc|użytkownik|"
                r"gmin|samorząd|przemysł|producent")
QUANT = P(r"\d+(?:[.,]\d+)?\s?(?:%|proc|razy|-?krotn|kwh|mwh|ton|kg|zł|godzin|minut|sekund|dni|lat)")
COMPARE = P(r"redukcj\w*|zmniejsz\w*|zwiększ\w*|poprawi\w*|wzr[oó]s\w*|spad\w*|obniż\w*|skróci\w*|"
            r"oszczędn\w*|skuteczn\w*|wydajn\w*|dokładn\w*|szybsz\w*|tańsz\w*|lepsz\w*")
RESULT_WORD = P(r"wynik\w*|wykazał\w*|pokazuj\w*|potwierdzi\w*|osiągn\w*")
EVID_3 = P(r"wdrożono|został\w* wdrożon\w*|jest (?:już )?(?:stosowan|używan|wykorzystywan)\w*|certyfik\w*|"
           r"przejęł\w*|przejął|przejęt\w*|wprowadzon\w* (?:w|we) \d+|stosuj\w* (?:już )?(?:od|w)\b|"
           r"(?:uzyskał\w*|otrzymał\w*|przyznan\w*|udzielon\w*) patent\w*|patent\w* (?:został\w* )?(?:udzielon|przyznan)\w*")
EVID_2 = P(r"pilotaż\w*|w warunkach rzeczywist\w*|zweryfikowan\w*|przetestowan\w*|testowan\w*|testy|"
           r"przez (?:\d+|dwa|trzy|cztery|pięć|sześć|rok|pół roku)\w* ?(?:lat\w*|rok\w*|miesi\w*|semestr\w*|tygodni\w*)?|"
           r"w (?:\d+|dwóch|trzech|czterech|pięciu|kilku) (?:klas|szkoł|gmin|placów|oddział|ośrod|powiat)\w*|"
           r"zgłoszeni\w* patentow\w*|patent\w*")
EVID_1 = P(r"laborator\w*|symulacj\w*|badani\w* (?:wykazał|potwierdził)\w*|zastosowan\w*|wykorzystan\w*")
LAB = P(r"laborator\w*|symulacj\w*|in vitro|w skali laboratoryjnej")
PORT_3 = P(r"licencj\w*|wdrożon\w* (?:w|we) (?:kolejn|inn)\w*|działa już w \d+|stosowan\w* w \d+|"
           r"przejęł\w*|przejął|przejęt\w*|(?:wdrożył|wprowadził)\w* (?:już )?(?:również|także|też)")
PORT_2 = P(r"skalowaln\w*|replik\w*|upowszechni\w*|przenie(?:sie|ść|sion|siona|sione)\w*|"
           r"inn\w+ (?:miast|szkoł|uczelni|jednostk|gmin|szpital|firm|zakład|krajach|region|placówk|powiat|"
           r"ośrod|urzęd|przedszkol)\w*|udostępni\w* (?:inn|wszystk|bezpłatn|nauczyciel|szkoł)\w*")
PORT_1 = P(r"partner\w*|uniwersaln\w*|można (?:go |ją |je )?(?:zastosować|wykorzystać|użyć)")

STAGE_ORDER = [
    ("in_use", P(r"wdrożono|został\w* wdrożon|jest (?:już )?(?:stosowan|używan|wykorzystywan)|użytkowan|"
                 r"funkcjonuje od|działa od|stosowan\w* od|korzyst\w* już|"
                 r"wprowadził\w*|wprowadzon\w*|wprowadzi\w* (?:w|we|od)\b|uruchomił\w*|uruchomion\w*|"
                 r"przejęł\w*|przejął|przejęt\w*|funkcjonuj\w*|realizowan\w* od|prowadzon\w* od")),
    ("pilot", P(r"pilotaż\w*|w warunkach rzeczywist\w*|przetestowan\w*|testowan\w*|faza testów|testy|"
                r"prowadzono przez|próbn\w*|eksperyment\w* pedagogiczn\w*")),
    ("prototype", P(r"prototyp\w*|demonstrator\w*|laborator\w*|model\w* (?:laboratoryjn|testow)\w*")),
    ("idea", P(r"pomysł\w*|koncepcj\w*|planuj\w*|zamierza\w*|opracowuj\w*")),
]
STAGE_SCORE = {"idea": 0, "prototype": 1, "pilot": 2, "in_use": 3}
MARKET = P(r"patent|licencj|komercjaliz|zamawiając|klient|spin-?off|start-?up|inwestor")
# Academic titles match in any case ("Dr inż.", "PROF."), names must still start with a capital letter.
AUTHOR = re.compile(r"(?<!\w)(?i:prof\.|dr|mgr|inż\.)(?:\s+(?i:hab\.|inż\.|dr|n\.\s?med\.|prof\.))*\s+"
                    r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?"
                    r"(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?)?")

# Relevance gate: does the text describe a solution / project / implementation at all?
SOLUTION_CUES = {
    "opracowanie rozwiązania": P(r"opracowa\w*|stworzy\w*|stworzon\w*|skonstruowa\w*|zaprojektowa\w*|zbudowa\w*|"
                                 r"wynalaz\w*|wynalezi\w*|zaprojektowan\w*|udoskonal\w*|"
                                 r"wprowadził\w*|wprowadzon\w*|uruchomił\w*|uruchomion\w*|wdrożył\w*|"
                                 r"zreorganizowa\w*|przygotowa\w* (?:program|procedur|model|metod|scenariusz)\w*|"
                                 r"zmieni\w* (?:sposób|organizac|procedur|zasad)\w*|zorganizowa\w* (?:now|pierwsz)\w*"),
    "opis działania": P(r"(?:pozwala|pozwoli|umożliwia|umożliwi|służy do|dzięki któr\w*|działa na zasadzie|"
                        r"wykrywa|mierzy|monitoruje|analizuje|steruje|usuwa|odzyskuje|polega\w* na|"
                        r"w ramach (?:program|projekt|inicjatyw)\w*|dzięki temu|co pozwala\w*|"
                        r"odwiedzaj\w*|prowadzi sprawę|śledz\w*|uczą się|pracuj\w* w grupach|zgłasza\w*)"),
    "obiekt (techniczny lub organizacyjny)": P(r"\b(?:system\w*|urządzeni\w*|aplikacj\w*|platform\w*|narzędzi\w*|technologi\w*|"
                           r"metod\w*|materiał\w*|czujnik\w*|sensor\w*|robot\w*|algorytm\w*|biopreparat\w*|"
                           r"prototyp\w*|model\w*|oprogramowani\w*|dron\w*|łazik\w*|instalacj\w*|preparat\w*|"
                           r"rozwiązani\w*|innowacj\w*|program\w*|procedur\w*|sposób|sposobu|usług\w*|"
                           r"inicjatyw\w*|scenariusz\w*|model\w* (?:pracy|obsługi|współpracy|organizacji)\w*)"),
    "etap lub wdrożenie": P(r"prototyp\w*|pilotaż\w*|wdroż\w*|przetestowa\w*|testowa\w*|patent\w*|"
                            r"zastosowan\w* w praktyce|komercjaliz\w*|licencj\w*|wprowadzon\w*|wprowadził\w*|"
                            r"uruchomił\w*|uruchomion\w*|przejęł\w*|przejęt\w*|upowszechni\w*|"
                            r"prowadzono przez|funkcjonuj\w*"),
}
NOISE_CUES = {
    "wydarzenie": P(r"konferencj\w*|gal[ia]\b|uroczyst\w*|jubileusz\w*|dzień otwarty|drzwi otwart\w*|"
                    r"inaugurac\w*|immatrykulac\w*|piknik\w*|festiwal\w*|koncert\w*|wystaw[aęy]\b|targ(?:i|ach)\b"),
    "zaproszenie lub zapisy": P(r"zaprasza\w*|zapis\w*|rejestracj\w*|rekrutacj\w*|termin zgłosze\w*|"
                                r"weź udział|wstęp wolny"),
    "sprawy organizacyjne": P(r"wybor\w* (?:rektora|dziekana|władz)|wybran\w* na|kadencj\w*|"
                              r"senat\w*|zarządzeni\w*|komunikat\w*|harmonogram\w*|godzin\w* otwarcia"),
    "nagroda lub ranking": P(r"nagrod\w*|wyróżnieni\w*|laureat\w*|ranking\w*|stypendi\w*|medal\w*|tytuł\w* honorow\w*"),
    "wydarzenie edukacyjne": P(r"wykład\w*|warsztat\w*|webinar\w*|szkoleni\w*|kurs\w*|seminari\w*|spotkani\w*"),
}
SECTORS = {
    "Zdrowie i medycyna": P(r"zdrow|medycz|pacjent|szpital|terapi|klinicz|rehabilit"),
    "Energia i środowisko": P(r"energi|odnawialn|klimat|środowisk|recykl|odpad|emisj|fotowolta|wodór"),
    "Materiały i budownictwo": P(r"beton|materiał|budow|konstrukc|kompozyt"),
    "IT i sztuczna inteligencja": P(r"sztuczn\w+ inteligencj|\bAI\b|algorytm|oprogramowani|aplikacj|cyber"),
    "Edukacja": P(r"uczni|nauczyci|szkoł|dydakty|edukac|studen"),
    "Rolnictwo i żywność": P(r"rolnic|żywno|upraw|zwierz|agro|hodow|weterynar"),
    "Lotnictwo i kosmos": P(r"lotnic|samolot|lotnisk|awiac|aeronaut|kosmiczn|kosmos|satelit|rakiet|dron|bezzałogow"),
    "Motoryzacja": P(r"motoryzac|samochod|pojazd|silnik|automotive|elektromobil"),
    "Transport i mobilność": P(r"transport|kolej|mobilnoś|komunikacj\w* miejsk|logisty"),
    "Administracja i samorząd": P(r"samorząd|gmin|urząd|mieszkańc|usług\w+ publiczn"),
    "Pomoc społeczna i włączenie": P(r"senior|os[oó]b\w* starsz|osob\w* starsz|niepełnospraw|pomoc\w* społeczn|"
                                     r"wykluczen|bezdomn|wolontari|integracj\w* społeczn|opiek\w*|samotn"),
}
# Task text: an innovation may be technological, organisational, educational, social or process-related.
INNOVATION_TYPES = {
    "technologiczna": P(r"prototyp|urządzeni|czujnik|sensor|robot|algorytm|oprogramowani|aplikacj|materiał|"
                        r"technologi|dron|instalacj|patent|preparat|system\w* (?:informatyczn|pomiarow)"),
    "edukacyjna": P(r"uczni|nauczyci|lekcj|zajęci|dydakty|program\w* nauczania|metod\w* nauczania|"
                    r"innowacj\w* pedagogiczn|kształceni|egzamin"),
    "organizacyjna": P(r"urząd|urzędnik|obsług\w* (?:wniosk|mieszkańc|klient|interesant)|procedur|organizac\w* pracy|"
                       r"zarządzani|wniosk|decyzj\w* administracyjn|kolejk"),
    "społeczna": P(r"senior|os[oó]b\w* starsz|niepełnospraw|wolontari|wykluczen|integracj\w* społeczn|"
                   r"pomoc\w* społeczn|mieszkańc\w* (?:zaangaż|współdecyd)|budżet\w* obywatelsk|samotn"),
    "procesowa": P(r"proces\w*|czas (?:obsługi|realizacji|wydania|oczekiwania)|skróci\w* czas|automatyzac|"
                   r"usprawni\w*|przepływ"),

}


def sentences(text):
    out = (re.sub(r"\s+", " ", s).strip() for s in SPLIT.split(text or ""))
    return [s[:300] for s in out if len(s) >= 25]


def _hits(sents, pattern):
    return [s for s in sents if pattern.search(s)]


def _best(candidates):
    """candidates: [(score, sentence)] -> criterion dict with the highest score (first sentence wins ties)."""
    if not candidates:
        return {"score": None, "quote": ""}
    score, quote = max(candidates, key=lambda c: c[0])
    return {"score": score, "quote": quote}


def score_problem(sents):
    out = []
    for s in sents:
        if PROBLEM.search(s):
            out.append((1 + bool(STAKEHOLDER.search(s)) + bool(QUANT.search(s)), s))
    return _best(out)


def score_evidence(sents):
    out = []
    for s in sents:
        if EVID_3.search(s):
            out.append((3, s))
        elif EVID_2.search(s):
            out.append((1 if LAB.search(s) else 2, s))  # laboratory tests are not field evidence
        elif EVID_1.search(s):
            out.append((1, s))
    return _best(out)


def score_results(sents):
    out = []
    for s in sents:
        quant, comp = bool(QUANT.search(s)), bool(COMPARE.search(s))
        if quant and comp:
            out.append((3, s))
        elif quant and RESULT_WORD.search(s) or comp and RESULT_WORD.search(s):
            out.append((2, s))
        elif comp:
            out.append((1, s))
    return _best(out)


def score_portability(sents):
    out = []
    for s in sents:
        tier = 3 if PORT_3.search(s) else 2 if PORT_2.search(s) else 1 if PORT_1.search(s) else 0
        if tier:
            out.append((tier, s))
    return _best(out)


def detect_stage(sents):
    for name, pattern in STAGE_ORDER:
        for s in _hits(sents, pattern):
            if name == "pilot" and LAB.search(s) and not P(r"pilotaż|warunkach rzeczywist").search(s):
                continue  # "przetestowano w laboratorium" is a prototype, not a pilot
            return name, s
    for s in sents:  # laboratory tests skipped above still mean a working prototype
        if LAB.search(s) and EVID_2.search(s):
            return "prototype", s
    return "unknown", ""


def relevance(sents, title=""):
    """Rule gate: is this a description of a solution/project/implementation? Quotes are sentences."""
    hay = [title] + sents if title else sents
    found, evidence = [], []
    for name, pattern in SOLUTION_CUES.items():
        hit = next((s for s in hay if pattern.search(s)), None)
        if hit:
            found.append(name)
            if hit in sents and hit not in evidence:
                evidence.append(hit)
    noise = [name for name, pattern in NOISE_CUES.items() if any(pattern.search(s) for s in hay)]
    if len(found) >= 3 or (len(found) == 2 and len(noise) <= 1):
        is_solution, reason = True, "Tekst opisuje rozwiązanie: " + ", ".join(found) + "."
    elif found and not noise:
        is_solution, reason = None, ("Słaby opis rozwiązania (" + ", ".join(found) +
                                     "); potrzebna weryfikacja przez człowieka.")
    else:
        why = "brak opisu opracowanego rozwiązania, projektu lub wdrożenia" if not found else (
            "opis rozwiązania jest szczątkowy (" + ", ".join(found) + ")")
        is_solution = False
        reason = "Nie wygląda na opis innowacji: " + why + (
            "; charakter tekstu: " + ", ".join(noise) if noise else "") + "."
    return {"is_solution": is_solution, "reason": reason, "evidence": evidence[:3],
            "cues": found, "noise": noise}


def analyze(text, title=""):
    sents = sentences(text)
    stage, stage_quote = detect_stage(sents)
    criteria = {
        "problem": score_problem(sents),
        "dowody": score_evidence(sents),
        "wyniki": score_results(sents),
        "przenosnosc": score_portability(sents),
        "gotowosc": ({"score": STAGE_SCORE[stage], "quote": stage_quote} if stage != "unknown"
                     else {"score": None, "quote": ""}),
    }
    market = _hits(sents, MARKET)
    haystack = f"{title}\n{text}"
    counts = {name: len(p.findall(haystack)) for name, p in SECTORS.items()}
    best = max(counts, key=counts.get)
    types = {name: len(p.findall(haystack)) for name, p in INNOVATION_TYPES.items()}
    ranked = [(name, n) for name, n in sorted(types.items(), key=lambda x: -x[1]) if n]
    kinds = [name for i, (name, n) in enumerate(ranked[:2]) if i == 0 or n >= 2]  # 2nd type only if well supported
    return {
        "innovation_types": kinds or ["nieokreślony"],
        "lead": next((s for s in sents if len(s) >= 40), ""),
        "sector": best if counts[best] else "Inne",
        "stage": stage, "criteria": criteria,
        "authors": [m.group(0) for m in AUTHOR.finditer(text or "")][:8],
        "signal_terms": [m.group(0) for p in SIGNAL if (m := p.search(text or ""))],
        "market": market[0] if market else "",
        "relevance": relevance(sents, title),
        "caveat": CAVEAT,
    }
