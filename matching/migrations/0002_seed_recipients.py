from django.db import migrations

# Illustrative profiles by institution type (not specific institutions). Editable in /admin/.
PROFILES = [
    ("CTT uczelni technicznej (profil przykładowy)", "ctt", "podkarpackie",
     "Szuka wyników badań gotowych do licencjonowania lub spin-offu; potrzebuje opisu wyników i stanu ochrony.",
     "patent, licencj, prototyp, technologi, materiał, spin",
     "Materiały i budownictwo, IT i sztuczna inteligencja, Energia i środowisko",
     "komercjalizacja, transfer", "prototype, pilot"),
    ("Gmina średniej wielkości: wydział inwestycji (profil przykładowy)", "samorzad", "podkarpackie",
     "Szuka sprawdzonych rozwiązań dla usług komunalnych, energii i transportu, które da się wdrożyć w budżecie gminy.",
     "gmin, mieszkańc, odpad, energi, oświetl, transport, wod, ciepł",
     "Administracja i samorząd, Energia i środowisko, Transport i mobilność",
     "wdrozenie, transfer", "pilot, in_use"),
    ("Szkoła ponadpodstawowa: dyrekcja (profil przykładowy)", "szkola", "",
     "Szuka metod dydaktycznych i narzędzi przetestowanych w innych szkołach, możliwych do przeniesienia bez dużych kosztów.",
     "uczni, nauczyci, lekcj, dydakty, edukac, szkoł",
     "Edukacja", "transfer, wdrozenie", "pilot, in_use"),
    ("Szpital wojewódzki: dział innowacji (profil przykładowy)", "szpital", "podkarpackie",
     "Szuka rozwiązań poprawiających diagnostykę, rehabilitację lub organizację opieki, z wynikami badań klinicznych lub pilotażu.",
     "pacjent, diagnost, rehabilit, terapi, medycz, szpital, leczeni",
     "Zdrowie i medycyna", "wdrozenie, transfer, komercjalizacja", "pilot, in_use"),
    ("Firma budowlana (MŚP) (profil przykładowy)", "firma", "",
     "Szuka nowych materiałów i technologii obniżających koszt lub emisje, z wynikami testów wytrzymałości.",
     "beton, materiał, budow, konstrukc, kompozyt, izolac",
     "Materiały i budownictwo", "komercjalizacja, wdrozenie", "prototype, pilot"),
    ("Fundusz venture capital na wczesnym etapie (profil przykładowy)", "inwestor", "",
     "Szuka zespołów z prototypem, sygnałem rynkowym (klient, patent) i skalowalnym modelem.",
     "start, spin, skalowal, klient, rynek, patent, aplikacj, algorytm",
     "IT i sztuczna inteligencja, Zdrowie i medycyna", "komercjalizacja", "prototype, pilot"),
    ("Park naukowo-technologiczny / inkubator (profil przykładowy)", "ibo", "podkarpackie",
     "Szuka pomysłów i prototypów do inkubacji, mentoringu i dalszego rozwoju; pomaga znaleźć partnerów.",
     "prototyp, pomysł, start, innowac, inkubac, akcelerac",
     "IT i sztuczna inteligencja, Materiały i budownictwo, Energia i środowisko, Transport i mobilność",
     "rozwoj, komercjalizacja", "idea, prototype"),
    ("Agencja rozwoju regionalnego (profil przykładowy)", "agencja", "podkarpackie",
     "Szuka rozwiązań do upowszechnienia w regionie i projektów, które mogą skorzystać z programów wsparcia.",
     "upowszechn, region, partner, wdroż, samorząd, przedsiębior",
     "Administracja i samorząd, Energia i środowisko, Edukacja",
     "transfer, wdrozenie, rozwoj", "pilot, in_use"),
    ("Spółdzielnia / grupa producentów rolnych (profil przykładowy)", "firma", "",
     "Szuka rozwiązań dla upraw, hodowli i przetwórstwa, przetestowanych w warunkach polowych.",
     "upraw, rolnic, hodow, żywno, zwierz, gleb, nawoz",
     "Rolnictwo i żywność", "wdrozenie, transfer", "pilot, in_use"),
    ("Organizacja pozarządowa działająca na rzecz klimatu (profil przykładowy)", "ngo", "",
     "Szuka rozwiązań ograniczających emisje i odpady, które można pokazać mieszkańcom i upowszechnić.",
     "klimat, emisj, odpad, recykl, środowisk, ekolog",
     "Energia i środowisko", "transfer, rozwoj", "idea, prototype, pilot"),
]


def seed(apps, schema_editor):
    Recipient = apps.get_model("matching", "Recipient")
    for name, kind, region, needs, tags, sectors, paths, stages in PROFILES:
        Recipient.objects.get_or_create(name=name, defaults=dict(
            institution_type=kind, region=region, needs=needs, tags=tags, sectors=sectors,
            paths=paths, stages=stages, is_example=True, active=True))


def unseed(apps, schema_editor):
    apps.get_model("matching", "Recipient").objects.filter(name__in=[p[0] for p in PROFILES]).delete()


class Migration(migrations.Migration):
    dependencies = [("matching", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
