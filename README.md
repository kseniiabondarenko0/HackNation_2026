# Radar Innowacji — V0.1: automatyczny kolektor

Licencja: EUPL-1.2 (plik `LICENSE`).

Działający etap zbierania publikacji z publicznych stron. Kolektor sam odnajduje adresy na skonfigurowanych stronach, pobiera tekst, zapisuje wyniki i powtarza sprawdzenie według harmonogramu. V0.1 zbiera publikacje; analiza AI i ocena potencjału innowacji są następnym etapem.

## Co potrafi (zgodnie z oficjalnym FAQ)

Radar **odkrywa i analizuje istniejące innowacje** (nie jest platformą do zgłaszania pomysłów): automatycznie zbiera publikacje szkół, uczelni, samorządów i instytucji publicznych, ocenia je modelem AI (0–100, próg publikacji 50, wynik wstępny), rozdziela dane zweryfikowane (adres, data, cytaty z tekstu) od szacunków AI (ocena, etap, TRL 1–9 tylko gdy dotyczy, uzasadnienie, braki, niepewność). Obszary: Technologiczne / Edukacyjne / Administracyjne; filtry: obszar, instytucja, województwo, sektor, dojrzałość (etap wdrożenia); `/porownaj/` zestawia 2–4 wybrane pozycje. Wiek publikacji nie odrzuca pozycji; aktualność sprawdza okresowa kontrola strony źródłowej.

## Szybki start z czystego klonu (bez Dockera)

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env          # opcjonalnie wpisz GEMINI_API_KEY (darmowy limit) i DJANGO_SECRET_KEY
python manage.py migrate && python manage.py seed_sources && python manage.py load_demo
python manage.py runserver    # http://127.0.0.1:8000/ — od razu widać zestaw demonstracyjny
python manage.py collect_sources   # w drugim terminalu: automatyczne zbieranie i analiza AI (opcjonalnie)
```

## Hosting (bezpłatnie) i trwałość danych

Baza to plik SQLite, więc hosting musi mieć **trwały dysk** (w Dockerze: wolumen `radar-data`, także kopie zapasowe i archiwum w `/data`). Na darmowych instancjach z dyskiem tymczasowym dane znikają przy restarcie: wtedy `load_demo` (uruchamiany automatycznie przez Dockerfile) odtworzy zestaw demonstracyjny, ale zebrane dane trzeba zbierać od nowa. Najprościej pokazywać komisji aplikację uruchomioną lokalnie lub na własnym serwerze z Dockerem; aktualne warunki darmowych planów hostingowych należy sprawdzić u dostawcy (nie weryfikowano).

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

## Zestaw demonstracyjny (czysta instalacja)

Na świeżej bazie strona jest pusta, dopóki kolektor nie pobierze publikacji, a Gemini (darmowy limit) ich nie oceni. Żeby pokaz nie zależał od tego czasu, repozytorium zawiera `analysis/data/demo_innovations.json`: 20–30 **rzeczywistych** publikacji, które system już uznał za interesujące (tytuł, instytucja, data, link, źródło, ocena AI i jej uzasadnienie, krótki fragment tekstu i zweryfikowane cytaty). Nic nie jest wymyślone; plik nie zawiera kluczy API, nazwisk autorów ani danych kontaktowych.

- `python manage.py load_demo` (Docker uruchamia je automatycznie po `seed_sources`): wstawia brakujące pozycje; powtórne uruchomienie nie tworzy duplikatów. Nigdy nie nadpisuje ani nie usuwa istniejących rekordów; jeśli baza ma już własne dane, nic nie robi (`--force` dodaje tylko brakujące pozycje demo). Nie przywraca publikacji usuniętych wcześniej ani starszych niż 8 mies. `--dry-run` pokazuje, co by dodał.
- Pozycje mają znacznik „Demo · wstępna ocena AI”; w karcie i na liście jest informacja, że oceny AI są **wstępne** (szacunek systemu, nie decyzja człowieka), a pełny tekst jest pod linkiem źródłowym.
- Zbieranie i analiza AI działają niezależnie: pozycje demo to zwykłe rekordy z gotową analizą AI (nie są analizowane ponownie, tryb bez AI ich nie degraduje), nowe materiały pojawiają się obok, a po 8 miesiącach demo wygasa jak każda publikacja.
- Odświeżenie zestawu na działającej bazie: `python manage.py export_demo` (bierze najlepsze potwierdzone publikacje, sprawdza, czy linki działają, odmawia zapisu, gdy w danych jest e-mail, telefon lub klucz API).

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
python manage.py load_demo   # zestaw demonstracyjny: strona od razu pokazuje prawdziwe publikacje
python manage.py runserver
# Drugi terminal z aktywnym tym samym środowiskiem:
python manage.py collect_sources
```

Przy lokalnym uruchomieniu plik `.env` nie jest automatycznie wczytywany przez Django: zmienne ustaw w środowisku terminala. Baza domyślnie powstaje w katalogu projektu. Docker jest zalecaną, sprawdzaną ścieżką uruchomienia.

## Rejestr i automatyczne wyszukiwanie źródeł

- Rejestr: `collection/data/sources.json` (uczelnie, parki naukowo-technologiczne, centra transferu technologii, instytucje publiczne). `seed_sources` ładuje wpisy z `verified: true` jako monitorowane, pozostałe jako kandydatów (niezbierane).
- Weryfikacja: `python manage.py probe_sources --registry --write` sprawdza robots.txt, dostępność strony, RSS/sitemap i listę publikacji (min. 3 linki), poprawia adres/prefiks i zapisuje wynik w rejestrze. `python manage.py probe_sources` robi to samo dla źródeł w bazie i aktywuje kandydatów z rejestru, którzy przeszli weryfikację.
- Wyszukiwanie: `python manage.py discover_sources [--query "..."] [--provider seeds] [--dry-run]`. Dostawcy: SearXNG (`SEARXNG_URL`) i Brave Search API (`BRAVE_API_KEY`), jeśli skonfigurowane; zawsze: lista domen `collection/data/discovery_seeds.json` i linki ze stron monitorowanych źródeł. Każda znaleziona strona przechodzi przez `safe_get` (SSRF, robots.txt, opóźnienie między żądaniami) i trafia do bazy jako **kandydat**; kandydaci są aktywowani automatycznie po weryfikacji technicznej (robots.txt, linki do artykułów), bez udziału człowieka.
- Kandydaci źródeł, którzy nie przeszli weryfikacji, są odrzucani automatycznie i nie są proponowani ponownie. Przyciski „Zatwierdź / Odrzuć” na `/zrodla/` (tylko dla zalogowanego staffu) to opcjonalna korekta listy źródeł, nie etap oceny innowacji.
- Worker uruchamia wyszukiwanie automatycznie co `DISCOVERY_AUTO_HOURS` godzin (0 = tylko ręcznie). Historia: panel administracyjny → Discovery runs.


## Ocena automatyczna, przechowywanie danych, skuteczność i priorytet PCI

- **Ocena innowacji jest w pełni automatyczna** (Gemini free → Groq free, 0 PLN). Nie ma logowania eksperta, ręcznego zatwierdzania ani odrzucania publikacji. Zalogowany staff (panel Django) może tylko: ustawiać etap „Co dalej z tą innowacją” i widzieć kontakty z formularza (za zgodą).
- **Trzy listy** (`/inicjatywy/?widok=...`, jedna definicja w `analysis/tabs.py`; liczniki zawsze równe listom, także z filtrami): **Interesujące** (`glowna`: ocena AI ≥ 50, zweryfikowany cytat; bez limitu wieku publikacji), **Do weryfikacji** (`weryfikacja`: tymczasowa kolejka — czeka na AI albo jest przeanalizowana, lecz niepotwierdzona), **Wszystkie** (`wszystkie`: wszystko, co przeszło kontrolę AI i nie zostało usunięte).
- **Polityka przechowywania** (`analysis/retention.py`, uruchamiana w każdym cyklu workera oraz ręcznie `python manage.py cleanup_storage [--apply]`; bez `--apply` to próba bez zmian):
  - wiek publikacji nie jest powodem odrzucenia (wymóg oficjalnego FAQ). Aktualność potwierdzonych pozycji sprawdza kontrola strony źródłowej co `CURRENCY_DAYS` (14) dni, kilka na cykl; po 3 kolejnych błędach pozycja wraca do „Do weryfikacji” (nic nie jest usuwane). Opcjonalne okno wieku: `WINDOW_MONTHS=N` (domyślnie 0 = wyłączone; starsze trafiają wtedy najpierw do archiwum `archive/old_articles.jsonl.gz`);
  - ocena AI < 50 lub „to nie innowacja” → usunięcie; zostaje tylko URL + skrót treści + powód (`Rejected`), żeby nie pobierać i nie analizować tego ponownie; wpisy wygasają po 12 miesiącach (lub oknie + 1 miesiąc) i mają limit `TOMBSTONE_MAX`;
  - duplikaty, strony bez treści, wyczerpane błędy pobierania → usunięcie;
  - kolejka „Do weryfikacji”: TTL `QUEUE_TTL_HOURS` (48 h), limit `QUEUE_MAX`; gdy AI jest niedostępne, artykuły czekają tylko w tej ograniczonej kolejce;
  - brak daty: przed usunięciem system sprawdza datę w stronie źródłowej (`DATE_CHECKS`); znaleziona data uruchamia tylko regułę werdyktu na zapisanej odpowiedzi AI (bez nowego wywołania);
  - kopia zapasowa SQLite (`archive/backups/`, ostatnie `BACKUP_KEEP`) powstaje przed pierwszym usunięciem; `cleanup_storage --apply` robi ją zawsze i przerywa, jeśli się nie uda;
  - zgłoszenia z formularza nie są usuwane przez okno ani werdykt (po TTL znika odrzucone zgłoszenie razem z danymi kontaktowymi).
- **`/skutecznosc/`**: stan bazy na żywo (ile przechowujemy, ile czeka, ile usunięto), wynik na oznaczonych przykładach (`analysis/examples.py`, to samo co `evaluate_filter`), jakość źródeł.
- **Priorytet PCI**: sektory „Lotnictwo i kosmos”, „Motoryzacja” (nowe), „IT i sztuczna inteligencja”, „Zdrowie i medycyna” +2, związek z Podkarpaciem +1. Wpływa tylko na sortowanie („Priorytet PCI”), nie na potencjał ani werdykt. Lista sektorów: `settings.ANALYSIS["PRIORITY_SECTORS"]` (opcjonalnie).


## Pokrycie wymagań zadania (stan 2026-11-21)

| Wymaganie (treść zadania) | Gdzie w systemie |
|---|---|
| Szkoły, uczelnie, JST, inne instytucje publiczne | Rejestr `collection/data/sources.json` (uczelnie, szkoła, miasto, powiat, gmina, agencje); kandydaci źródeł |
| Innowacje także organizacyjne, edukacyjne, społeczne, procesowe | Reguły w `analysis/rules.py`, pole „Typ innowacji”, przykłady w `analysis/examples.py` |
| Zgłaszanie lub automatyczne wykrywanie | Kolektor + „Zgłoś innowację” |
| Ocena według jasnych kryteriów | Rubryka z cytatami, automatyczny werdykt z powodem i oceną AI |
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
