# Radar Innowacji — V0.1: automatyczny kolektor

Licencja: EUPL-1.2 (plik `LICENSE`).

Działający etap zbierania publikacji z publicznych stron. Kolektor sam odnajduje adresy na skonfigurowanych stronach, pobiera tekst, zapisuje wyniki i powtarza sprawdzenie według harmonogramu. V0.1 zbiera publikacje; analiza AI i ocena potencjału innowacji są następnym etapem.

## Start w Windows PowerShell

```powershell
Set-Location "C:\Project\HackNation\radar"
# Tylko jeśli .env jeszcze nie istnieje:
Copy-Item .env.example .env
# Ustaw własny DJANGO_SECRET_KEY w .env.
docker compose up -d --build --wait
```

Przy kolejnym uruchomieniu zachowaj istniejący `.env`. Docker automatycznie wykonuje migracje, dodaje dwa początkowe źródła (PWr i UR), a następnie uruchamia web i kolektor. Istniejące ustawienia źródeł nie są nadpisywane.

- Publikacje: http://localhost:8000/
- Harmonogram i błędy źródeł: http://localhost:8000/zrodla/
- Historia rzeczywistych przebiegów: http://localhost:8000/przebiegi/
- Stan JSON: http://localhost:8000/api/status/

Pierwsze pobieranie trwa zwykle kilkadziesiąt sekund, zależnie od stron. Widok źródeł odświeża się co 30 sekund. Domyślny interwał źródła to 60 minut; worker sprawdza harmonogram co 15 sekund.

```powershell
docker compose ps
docker compose logs --tail=50 worker
docker compose exec web python manage.py createsuperuser
```

Zaloguj się w `/admin/`, aby dodawać/wyłączać źródła, zmieniać interwał i prefiks. Zalogowany administrator może też zlecić sprawdzenie na stronie źródeł. Przycisk zmienia harmonogram; pracę wykonuje worker.

## Ręczna kontrola i testy

```powershell
docker compose exec worker python manage.py collect_sources --once --all
docker compose exec web python manage.py test tests --noinput
docker compose exec web python manage.py check
```

`--all` pomija termin następnego sprawdzenia, ale respektuje blokadę trwającego przebiegu. Niedawno pobrane artykuły nie są ponownie ściągane. Znane artykuły trafiają do ponownej kontroli po 24 godzinach.

Aby zatrzymać: `docker compose stop`. Aby wrócić: `docker compose up -d`. Komputer i Docker muszą działać, aby zbieranie odbywało się automatycznie. Dane są w trwałym wolumenie `radar-data`.

## Mechanizmy i ograniczenia

- HTML-lista, RSS/Atom, sitemap i ograniczone indeksy sitemap.
- Reguły robots.txt, publiczne HTTP(S), kontrola adresów/redirectów, limit rozmiaru i czasu odpowiedzi.
- Jednoczesny drugi przebieg tego samego źródła jest blokowany. Po przerwaniu blokada wygasa; niedokończone adresy pozostają w bazie.
- Błąd parsowania jednej publikacji nie przerywa całego worker. Nieudane pobrania mają ograniczenie prób i opóźnienie ponowienia.
- Unikalność URL i identycznego tekstu, osobne daty publikacji/odkrycia/pobrania.
- `lastmod` sitemap nie jest datą publikacji.
- Pobieranie nie używa płatnego API. Nie jest to indeks całego internetu: działa w zakresie skonfigurowanych źródeł.
- PDF, skany, strony wymagające logowania/JS i semantyczne łączenie podobnych projektów pozostają poza V0.1.
- Ochrona URL to podstawowa warstwa dla lokalnego narzędzia; publiczne wdrożenie wymaga dodatkowej kontroli sieci, w tym ochrony przed DNS rebinding.

## Lokalnie bez kontenerów

Python 3.12+ i osobne dwa terminale. Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sources
python manage.py runserver
# Drugi terminal z aktywnym tym samym środowiskiem:
python manage.py collect_sources
```

Przy lokalnym uruchomieniu plik `.env` nie jest automatycznie wczytywany przez Django: zmienne ustaw w środowisku terminala. Baza domyślnie powstaje w katalogu projektu. Docker jest zalecaną, sprawdzaną ścieżką uruchomienia.

## Rejestr i automatyczne wyszukiwanie źródeł

- Rejestr: `collection/data/sources.json` (uczelnie, parki naukowo-technologiczne, centra transferu technologii, instytucje publiczne). `seed_sources` ładuje wpisy z `verified: true` jako monitorowane, pozostałe jako kandydatów (niezbierane).
- Weryfikacja: `python manage.py probe_sources --registry --write` sprawdza robots.txt, dostępność strony, RSS/sitemap i listę publikacji (min. 3 linki), poprawia adres/prefiks i zapisuje wynik w rejestrze. `python manage.py probe_sources` robi to samo dla źródeł w bazie i aktywuje kandydatów z rejestru, którzy przeszli weryfikację.
- Wyszukiwanie: `python manage.py discover_sources [--query "..."] [--provider seeds] [--dry-run]`. Dostawcy: SearXNG (`SEARXNG_URL`) i Brave Search API (`BRAVE_API_KEY`), jeśli skonfigurowane; zawsze: lista domen `collection/data/discovery_seeds.json` i linki ze stron monitorowanych źródeł. Każda znaleziona strona przechodzi przez `safe_get` (SSRF, robots.txt, opóźnienie między żądaniami) i trafia do bazy jako **kandydat**, wyłączony do czasu decyzji eksperta.
- Decyzja eksperta: przyciski „Zatwierdź / Odrzuć” na `/zrodla/` albo akcje w panelu administracyjnym. Odrzucone domeny nie są proponowane ponownie.
- Worker uruchamia wyszukiwanie automatycznie co `DISCOVERY_AUTO_HOURS` godzin (0 = tylko ręcznie). Historia: panel administracyjny → Discovery runs.


## Decyzja eksperta, skuteczność i priorytet PCI

- **Decyzja eksperta** (karta publikacji, tylko zalogowany staff): „Zatwierdź jako innowację”, „Odrzuć” (z powodem), „Cofnij”. Ma pierwszeństwo przed werdyktem filtra i nie jest nadpisywana przy ponownej analizie. Radar ma zakładkę „Zatwierdzone przez eksperta”.
- **`/skutecznosc/`**: lejek na żywo z bazy, zgodność filtra z ekspertem (precyzja w każdej grupie werdyktu), wynik na oznaczonych przykładach (`analysis/examples.py`, to samo co `evaluate_filter`), jakość źródeł.
- **Priorytet PCI**: sektory „Lotnictwo i kosmos”, „Motoryzacja” (nowe), „IT i sztuczna inteligencja”, „Zdrowie i medycyna” +2, związek z Podkarpaciem +1. Wpływa tylko na sortowanie („Priorytet PCI”), nie na potencjał ani werdykt. Lista sektorów: `settings.ANALYSIS["PRIORITY_SECTORS"]` (opcjonalnie).


## Pokrycie wymagań zadania (stan 2026-11-21)

| Wymaganie (treść zadania) | Gdzie w systemie |
|---|---|
| Szkoły, uczelnie, JST, inne instytucje publiczne | Rejestr `collection/data/sources.json` (uczelnie, szkoła, miasto, powiat, gmina, agencje); kandydaci źródeł |
| Innowacje także organizacyjne, edukacyjne, społeczne, procesowe | Reguły w `analysis/rules.py`, pole „Typ innowacji”, przykłady w `analysis/examples.py` |
| Zgłaszanie lub automatyczne wykrywanie | Kolektor + „Zgłoś innowację” |
| Ocena według jasnych kryteriów | Rubryka z cytatami, werdykt z powodem, decyzja eksperta |
| Rekomendowanie ścieżki | Rozwój / transfer / komercjalizacja / wdrożenie + „czego brakuje” |
| Wyszukiwanie podobnych, ograniczanie dublowania | „Podobne rozwiązania” + linki do baz z pkt 7 (Espacenet/EPO, UPRP, PBN, PPM, PAN, Interreg, NCBR) |
| Łączenie z użytkownikami, partnerami, inwestorami | Profile odbiorców + „Szukam rozwiązania” (instytucje zgłaszają potrzeby, radar dopasowuje innowacje) |
| Co dzieje się po identyfikacji (pkt 9) | „Co dalej z tą innowacją”: kontakt → przekazano partnerowi → pilotaż → wdrożono, z historią |
| Mierniki skuteczności (pkt 6e) | `/skutecznosc/`, `manage.py evaluate_filter` |
| Co najmniej dwa przypadki użycia (pkt 6) | `python manage.py demo_cases` — scenariusz a)–e) dla przypadku technologicznego i organizacyjnego |
| Integracja | `/api/innowacje.json`, `/api/innowacje.csv`, `/api/szukaj/`, `/api/status/` |
| Bezpieczeństwo i ochrona danych | „O systemie” → RODO; eksport bez danych osobowych; kontakt tylko za zgodą |
| Licencja EUPL-1.2 | `LICENSE` |


## Województwa i użytkownicy (2026-11-21, uwagi kuratorów)

- **Dowolne województwo.** Filtr „Województwo” w radarze i w eksporcie (`?woj=małopolskie`, `?woj=ogólnopolskie`). Region publikacji: województwo najczęściej wymienione w tekście → siedziba instytucji źródła (`region` w `sources.json`) → wybór w zgłoszeniu. Kod: `analysis/regions.py` (16 województw). Bonus priorytetu za województwo: `PRIORITY_REGION` w `.env` (domyślnie `podkarpackie`, puste = brak). Odbiorca z tego samego województwa dostaje +1 pkt dopasowania.
- **Kto korzysta.** Szkoły, uczelnie, samorządy, inne instytucje, firmy prywatne, organizacje pozarządowe i osoby prywatne: „Zgłoś innowację” ma pole „Kto zgłasza” i województwo (model `collection.Submission`), „Zgłoś potrzebę” ma typ „Osoba prywatna”. Filtr „Od kogo” w radarze (`?kto=company`). Dane osobowe tylko za zgodą, nazwisko publiczne tylko na życzenie, kontakt widoczny dla zespołu. Ukryte pole przeciw automatom. Strona `/dla-kogo/`.
