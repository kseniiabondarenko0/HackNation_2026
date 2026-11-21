"""Voivodeships (województwa): detecting the region of a publication and labels for filters.

The region of a publication = the voivodeship most often named in its text (city or region name);
if the text names none, the region of the institution that published it; for a submission, the region
the submitter chose. Codes are the voivodeship names in lower case, as they are written in Polish.
"""
import re
from collections import Counter

P = lambda p: re.compile(p, re.I)
VOIVODESHIPS = [
    ("dolnośląskie", P(r"dolnośląsk\w*|wrocław\w*|legnic\w*|wałbrzych\w*|jeleni\w* gór\w*")),
    ("kujawsko-pomorskie", P(r"kujawsk\w*|bydgoszcz\w*|toru[nń]\w*|włocław\w*|grudziądz\w*")),
    ("lubelskie", P(r"lubelsk\w*|lublin\w*|zamoś\w*|chełm\w*|biał\w* podlask\w*")),
    ("lubuskie", P(r"lubusk\w*|zielon\w* gór\w*|gorz[oó]w\w* wielk\w*|gorzow\w*")),
    ("łódzkie", P(r"łódzk\w*|łódź|łodzi|piotrk[oó]w\w*|piotrkow\w*|skierniew\w*")),
    ("małopolskie", P(r"małopolsk\w*|krak[oó]w\w*|krakow\w*|tarn[oó]w\w*|tarnow\w*|now\w* sącz\w*|zakopan\w*")),
    ("mazowieckie", P(r"mazowieck\w*|warszaw\w*|radomi\w*|\bradom\b|płock\w*|siedlc\w*|ostrołęk\w*")),
    ("opolskie", P(r"\bopol\w*")),
    ("podkarpackie", P(r"podkarpac\w*|rzesz[oó]w\w*|krośn\w*|\bkrosn\w*|przemyś\w*|mielc\w*|mielec|tarnobrzeg\w*|sanok\w*|"
                       r"jaśle|jasł\w*|dębic\w*|stalow\w* wol\w*|jarosławiu|jarosławsk\w*|łańcut\w*|bieszczad\w*")),
    ("podlaskie", P(r"(?<!biała )(?<!białej )podlask\w*|białyst\w*|białymst\w*|białegost\w*|łomż\w*|suwał\w*")),
    ("pomorskie", P(r"(?<!zachodnio)(?<!kujawsko-)(?<!kujawsko )pomorsk\w*|gdańsk\w*|gdyni\w*|gdynia|sopo\w*|słupsk\w*")),
    ("śląskie", P(r"(?<!dolno)śląsk\w*|katowic\w*|gliwic\w*|sosnow\w*|bielsk\w*-biał\w*|częstoch\w*|zabrz\w*|bytom\w*")),
    ("świętokrzyskie", P(r"świętokrzysk\w*|kielc\w*")),
    ("warmińsko-mazurskie", P(r"warmi[nń]sk\w*|mazursk\w*|olsztyn\w*|elbląg\w*|\bełk\w*")),
    ("wielkopolskie", P(r"wielkopolsk\w*|pozna[nń]\w*|kalisz\w*|konin\w*")),
    ("zachodniopomorskie", P(r"zachodniopomorsk\w*|szczecin\w*|koszalin\w*|świnouj\w*")),
]
CODES = [code for code, _ in VOIVODESHIPS]
CHOICES = [(code, code) for code in CODES]
NATIONAL = "ogólnopolskie"  # filter value for publications with no voivodeship


def detect(text):
    """(code, first matching word) of the voivodeship named most often in the text, or ("", "")."""
    counts, first = Counter(), {}
    for code, pattern in VOIVODESHIPS:
        found = pattern.findall(text or "")
        if found:
            counts[code] = len(found)
            first[code] = found[0]
    if not counts:
        return "", ""
    code = max(counts, key=lambda c: (counts[c], -CODES.index(c)))
    return code, first[code]


def resolve(text, source_region="", chosen=""):
    """Region of a publication with the reason shown to the user."""
    if chosen in CODES:
        return {"code": chosen, "how": "wskazane w zgłoszeniu"}
    code, word = detect(text)
    if code:
        return {"code": code, "how": f"z tekstu: „{word}”"}
    if source_region in CODES:
        return {"code": source_region, "how": "siedziba instytucji źródła"}
    return {"code": "", "how": "brak wskazania regionu (ogólnopolskie)"}
