"""Links to the databases listed in the task (section 7), with keywords taken from the publication.

Only some of these services accept a query in the URL; for the others the keywords are shown to copy.
Nothing is fetched automatically — the expert opens the database and checks novelty / duplicate work.
"""
import re
from urllib.parse import quote_plus

WORD = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{4,}")
STOP = set("""
oraz przez które który która które został została zostały jest będzie może można także również tylko
nowy nowa nowe nowej nowego dla jako przy jego ich tego swoje bardzo więcej naukowcy studenci uczelni
politechniki uniwersytetu wydziału aktualności informacja projekt projektu
""".split())

DATABASES = [
    # (label, what it checks, url template or None, base url)
    ("Espacenet (EPO) — patenty", "czy istnieje podobny patent", "https://worldwide.espacenet.com/patent/search?q={q}",
     "https://worldwide.espacenet.com/"),
    ("Rejestr EPO", "status europejskich zgłoszeń patentowych", None, "https://register.epo.org/regviewer"),
    ("Urząd Patentowy RP — e-wyszukiwarka", "polskie patenty i wzory użytkowe", None,
     "https://ewyszukiwarka.pue.uprp.gov.pl/search/simple-search"),
    ("PBN — Polska Bibliografia Naukowa", "publikacje naukowe autorów", None, "https://pbn.nauka.gov.pl/core/#/home"),
    ("PPM — Polskie Platformy Medyczne", "publikacje z uczelni medycznych", None, "https://ppm.edu.pl/index.seam"),
    ("Biblioteka cyfrowa PAN", "czasopisma naukowe", None, "https://www.czasopisma.pan.pl/dlibra"),
    ("Interreg — lista projektów", "projekty międzynarodowe z funduszy UE", None, "https://interreg.gov.pl/lista-projektow/"),
    ("NCBR — wyszukiwarka sukcesów beneficjentów", "projekty finansowane przez NCBR",
     None, "https://www.gov.pl/web/ncbr/wyszukiwarka-sukcesow-beneficjentow"),
]


def keywords(title, sector="", limit=5):
    words = [w for w in WORD.findall(title or "") if w.lower() not in STOP]
    out = list(dict.fromkeys(words))[:limit]
    return " ".join(out)


def external_search(title, sector=""):
    q = keywords(title, sector)
    links = []
    for label, why, template, base in DATABASES:
        url = template.format(q=quote_plus(q)) if template and q else base
        links.append({"label": label, "why": why, "url": url, "prefilled": bool(template and q)})
    return {"query": q, "links": links}
