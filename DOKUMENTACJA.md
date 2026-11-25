# Radar Innowacji — pełna dokumentacja (PL)

> Krótki opis projektu po angielsku: [README.md](README.md).

**HackNation 2026 · zadanie Podkarpackiego Centrum Innowacji · zespół Zhivchiki · EUPL-1.2 ([LICENSE](LICENSE))**

Dokumentacja sprawdzona z kodem i konfiguracją 22.11.2026. Liczby dotyczące rejestru i zestawu demo opisują pliki repozytorium; stan działającej bazy zmienia się wraz z pracą kolektora.

Radar zbiera publikacje publicznych instytucji, rozpoznaje opisy istniejących rozwiązań i tworzy karty z oceną AI, cytatami, brakującymi informacjami i dalszą ścieżką: rozwój, transfer, komercjalizacja lub wdrożenie. Obsługuje także rozwiązania edukacyjne, organizacyjne, społeczne i procesowe. Wyszukiwanie obejmuje rozszerzany rejestr źródeł, a nie cały internet.

Budżet projektu na nowe usługi i API wynosi **0 PLN**. Używamy kont Gemini/Groq w darmowych planach bez rozliczeń. Limity w aplikacji są naszymi ograniczeniami zużycia; nie określają aktualnej darmowej kwoty dostawcy i nie sprawdzają taryfy konta. Płatne wyszukiwanie ani Google Search Grounding nie są wymagane.

## Uruchomienie w Dockerze — Windows PowerShell

Wymagany działający Docker Desktop z obsługą Docker Compose. Uruchamiaj polecenia w katalogu repozytorium, obok `docker-compose.yml`.

```powershell
Set-Location .\HackNation_2026
# Tylko przy pierwszej konfiguracji; zachowaj istniejący .env:
Copy-Item .env.example .env
```

W `.env` ustaw własny `DJANGO_SECRET_KEY`. Klucze `GEMINI_API_KEY` i `GROQ_API_KEY` są opcjonalne do oglądania zapisanych kart; co najmniej jeden jest potrzebny do nowych analiz i scenariuszy „Sprawdź u nas”. `.env` jest ignorowany przez Git i kontekst obrazu Docker.

```powershell
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail=50 worker
```

Web wykonuje migracje, `seed_sources`, próbę `load_demo` i `collectstatic`, następnie uruchamia gunicorn. Worker uruchamia `collect_sources` po sprawdzeniu zdrowia weba. Błąd ładowania demo nie zatrzymuje weba — jego przyczynę sprawdź w logach.

`seed_sources` wczytuje **137 wpisów**, z których **96** ma w pliku `verified: true`. Zweryfikowane nowe wpisy są aktywne, pozostałe stają się kandydatami. Komenda zachowuje ręczne decyzje i istniejącą konfigurację; może uzupełnić pusty region i aktywować zweryfikowanego kandydata z rejestru bez wcześniejszej ręcznej decyzji. Odkrywanie i demo mogą zmienić liczbę źródeł w bazie.

- [Przegląd](http://localhost:8000/) i [katalog inicjatyw](http://localhost:8000/inicjatywy/).
- [Źródła](http://localhost:8000/zrodla/) i [historia zbierania](http://localhost:8000/przebiegi/).
- [Stan JSON](http://localhost:8000/api/status/) i [kontrola zdrowia](http://localhost:8000/health/).

Pierwsze materiały mogą pojawić się po kilkudziesięciu sekundach; pełny cykl wielu źródeł trwa dłużej. Worker sprawdza harmonogram co 15 sekund. Domyślny interwał źródła wynosi 60 minut, a źródła odkrywane automatycznie dostają 240 minut; rzeczywisty termin zależy od ustawień źródła i długości cyklu. Widok źródeł odświeża się co 30 sekund.

Zatrzymanie: `docker compose stop`. Ponowne uruchomienie: `docker compose up -d`. Po zmianach kodu użyj ponownie `docker compose up -d --build --wait`. Automatyczne zbieranie wymaga działającego komputera, Dockera i workera.

## Uruchomienie bez Dockera

Python **3.12** jest wersją sprawdzaną w obrazie; zależności znajdują się w [requirements.txt](requirements.txt). Django jest ograniczone do gałęzi 5.2, pozostałe pakiety nie mają pełnego pliku blokady wersji.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Opcjonalnie, jeśli .env jeszcze nie istnieje:
Copy-Item .env.example .env
$env:DJANGO_DEBUG = '1'
python manage.py migrate
python manage.py seed_sources
python manage.py load_demo
python manage.py runserver
```

Linux/macOS — odpowiednik w Bash:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Opcjonalnie, jeśli .env jeszcze nie istnieje:
cp .env.example .env
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py seed_sources
python manage.py load_demo
python manage.py runserver
```

W drugim terminalu aktywuj to samo środowisko, również ustaw `DJANGO_DEBUG=1` i wykonaj `python manage.py collect_sources`. Sam `runserver` nie uruchamia kolektora. Przy lokalnym rozwoju można użyć `DJANGO_DEBUG=1`; `.env.example` i obraz Docker domyślnie mają `DJANGO_DEBUG=0`. `WHITENOISE_USE_FINDERS=True` zapewnia style także bez wcześniejszego `collectstatic`; Docker nadal wykonuje tę komendę przy starcie.

`config/settings.py` automatycznie wczytuje `.env`; zmienne ustawione w terminalu mają pierwszeństwo. Domyślna baza lokalna to `db.sqlite3`, archiwum to `archive/`. Przy `DJANGO_DEBUG=0` brak własnego sekretu blokuje start; przykładowe `change-me` tylko ostrzega i należy je zastąpić.

## Funkcje i miejsca w interfejsie

| Miejsce | Co robi |
|---|---|
| `/` | Liczniki i najnowsze publikacje według daty publikacji |
| `/inicjatywy/` | Karty/tabela, wyszukiwanie bez rozróżniania polskich znaków i wielkości liter, filtry źródła, instytucji, regionu, sektora, obszaru, etapu i ścieżki |
| `/a/<id>/` | Zebrany tekst, źródło, oddzielne daty publikacji/wykrycia/pobrania, cytaty, ocena AI, braki, TRL gdy dotyczy, rekomendowana ścieżka |
| `/porownaj/?id=1&id=2` | Porównanie 2–4 wybranych kart; identyfikatory są przykładowe |
| `/zglos/` | „Wskaż rozwiązanie”: URL lub tekst istniejącego rozwiązania, typ zgłaszającego i województwo |
| `/potrzeby/` | „Szukam rozwiązania”: potrzeby i profile odbiorców, dopasowanie według sektora, słów kluczowych, etapu, ścieżki i regionu |
| `/a/<id>/dalej/` | Zmiana etapu „Co dalej” przez zalogowany staff: kontakt, przekazanie partnerowi, pilotaż, wdrożenie lub zamknięcie; historia zmian |
| `/skutecznosc/` | Stan bazy, etapy obsługi, jakość źródeł i test filtra regułowego na przykładach |
| `/dla-kogo/`, `/o-systemie/` | Użytkownicy, zasady działania, ograniczenia i przetwarzanie danych |
| `/admin/` | Zarządzanie danymi zgodnie z uprawnieniami Django |

„Podobne rozwiązania” wykorzystują TF-IDF w bieżącej bazie. Linki do Espacenet/EPO, UPRP, PBN, PPM, PAN, Interreg i NCBR pomagają w dalszym wyszukiwaniu; nie są automatycznym przeszukaniem tych baz ani badaniem zdolności patentowej.

Ocena innowacji jest automatyczna; osobny ekran ręcznego zatwierdzania/odrzucania publikacji nie jest częścią obecnego interfejsu. Staff zarządza m.in. źródłami i etapami obsługi; panel Django pozostaje dostępny zgodnie z nadanymi uprawnieniami.

## Funkcja dodatkowa: „Sprawdź u nas”

Na karcie kliknij **Sprawdź u nas** (`/a/<id>/sprawdz-u-nas/`). Podaj typ organizacji, cel, zasoby i ograniczenia. AI przygotowuje wstępną ocenę warunków transferu, bariery, pytania do autora, propozycję pilotażu i mierniki. Dosłowne cytaty są sprawdzane w zapisanym tekście; niepotwierdzone są pomijane i liczone, a bez co najmniej jednego prawidłowego cytatu wynik nie powstaje. Listy są ograniczone do trzech elementów. Pozostałe treści są oznaczone jako wnioski lub propozycje AI. Obecność cytatu nie potwierdza niezależnie prawdziwości wyników. Scenariusz nie wycenia wdrożenia ani nie gwarantuje wykonalności.

- Wynik jest dostępny najwyżej 7 dni, w sesji przeglądarki, która go utworzyła; sam adres UUID nie wystarcza. Usunięcie ciasteczka sesji oznacza utratę dostępu. Wygasłe rekordy usuwa worker w trybie zbierania lub kolejna próba wygenerowania scenariusza.
- Ten sam tekst i warunki korzystają z cache bez kolejnego wywołania AI. **Zmień warunki i przelicz** przygotowuje nowy scenariusz i zestawia go z poprzednim: zmienione warunki, ocena, nowe i pominięte bariery, pytania oraz kroki. Porównanie tekstów jest obliczane lokalnie, bez kolejnego zapytania AI; odmienne sformułowanie tej samej uwagi może wyglądać jak zmiana. Zmiana źródła wycofuje stare cytaty i rekomendacje z widoku.
- Limit sesji: 8 nowych scenariuszy na godzinę. Nie podawaj danych osobowych ani poufnych: treść formularza trafia do skonfigurowanego dostawcy AI. Scenariuszy nie ma w publicznym eksporcie.
- Przy braku klucza, limitu lub poprawnej odpowiedzi formularz pozostaje wypełniony. Błędna odpowiedź nie jest zapisywana jako gotowy raport. Otworzenie formularza lub zapisanego wyniku nie wywołuje modelu.

**Pomysł na pokaz:** ta sama innowacja, dwa profile organizacji — z dostępnym partnerem i bez wykonawcy lub budżetu. Porównaj uzasadnienia i bariery. To dwa nowe zapytania AI; nie zakładamy z góry odpowiedzi modelu. Zapisane karty demo nie zawierają gotowych scenariuszy dla organizacji.

## Tryb pokazowy dla jury

Ustaw `DEMO_MODE=1` w `.env` i uruchom `docker compose up -d --build --wait`. Worker w tle nie pobiera stron, nie analizuje i nie czyści bazy; zapisane karty i ręczne scenariusze nadal działają. Tryb jest oznaczony w stopce, na `/zrodla/` i w `/api/status/` (`demo_mode`). Nie odnawia już wykorzystanego limitu AI.

Przed pokazem przygotuj dwa scenariusze w tej samej przeglądarce. Każdy nowy scenariusz zwykle wymaga jednego zapytania, ale ponowienia i fallback mogą zwiększyć ich liczbę. Ponowne otwieranie i porównanie zapisanych wyników nie wywołuje modelu. Wyniki pozostają prywatne dla sesji i dostępne przez 7 dni.

Aby wrócić do zbierania, ustaw `DEMO_MODE=0` i wykonaj `docker compose up -d`. Jawne `collect_sources --once` działa także w trybie pokazowym i może pobierać, analizować oraz czyścić dane.

## AI, ocena i limity

Domyślny backend to `ai`: Gemini, następnie Groq, jeśli ma skonfigurowany klucz. Domyślne nazwy modeli w kodzie to `gemini-3.1-flash-lite` i `openai/gpt-oss-120b`; można je zmienić przez `GEMINI_MODEL` / `GROQ_MODEL`. Ich dostępność i darmowe limity zależą od konta dostawcy. Backend Ollama nie jest zaimplementowany w obecnej wersji.

| Wewnętrzne ustawienie | Gemini | Groq |
|---|---:|---:|
| Wywołania na dzień | 250 | 900 |
| Tokeny wejścia + wyjścia na dzień | 1 000 000 | 90 000 |
| Odstęp między wywołaniami w procesie | 6 s | 10 s |
| Maksymalna długość odpowiedzi | 1500 tokenów | 1500 tokenów |

Tabela dotyczy analizy artykułów. Scenariusze „Sprawdź u nas” mają maksymalnie 2500 tokenów odpowiedzi, timeout 25 s i jedną ponowną próbę (`transfer.INTERACTIVE`), przy tym samym budżecie dziennym. To wartości ustawione w kodzie, **nie oficjalne limity darmowych planów**. Wspólny licznik obejmuje analizy artykułów i scenariusze. Automatyczna kolejka wstrzymuje nowe analizy, gdy pozostaje najwyżej 10 dostępnych wywołań (`LLM["SCENARIO_RESERVE"]`), zostawiając rezerwę na pracę ręczną. Rezerwa nie zwiększa budżetu; niedostępny dostawca lub limit tokenów może zablokować AI wcześniej. Dzień licznika określa data procesu serwera, a czas odnowienia kwoty dostawcy może być inny.

Model dostaje do 6000 znaków oczyszczonego tekstu. Worker wykonuje do 2 prób analizy artykułu po każdym źródle i do 60 po cyklu. Każda próba HTTP, także ponowienie po błędzie sieci, rezerwuje miejsce w dziennym liczniku przed wysłaniem. Limity prób artykułów na przebieg nie są osobnym limitem żądań HTTP: ponowienia i fallback nadal zużywają wspólny budżet dzienny. `analyze --max-calls 0` pomija nowe analizy. HTTP 429 wstrzymuje dostawcę; nie jest ponawiany w pętli. Niepoprawny JSON nie jest powodem odrzucenia innowacji. Zmiana tekstu lub metadanych źródła wycofuje starą ocenę do ponownej analizy tylko tej publikacji; ostatni snapshot i etapy obsługi są zachowane.

AI podaje **jedną ocenę 0–100**, uzasadnienie, braki i niepewność. To nie jest średnia pięciu osobnych ocen kryteriów. Rubryka 0–3 dla pięciu kryteriów należy do pomocniczego backendu `rules`, uruchamianego wyłącznie jawnie przez `ANALYSIS_BACKEND=rules`; nie zastępuje automatycznie niedostępnego AI. Liczba zweryfikowanych cytatów nie oznacza procentowej kompletności wiedzy o projekcie.

## Zestaw demonstracyjny i zakres sprawdzenia

Plik `analysis/data/demo_innovations.json` zawiera **21 publikacji z adresami źródłowymi i zapisanymi ocenami AI**. `load_demo` dodaje brakujące rekordy na pustej bazie, bez wywoływania modelu. Na bazie z własnymi artykułami domyślnie nic nie dodaje; `--force` pozwala dołączyć brakujące demo. Istniejące URL-e i wpisy w `Rejected` są pomijane; rekordy nie są nadpisywane.

Pozycje mają znacznik demo i zawierają fragment tekstu oraz cytaty, a pełny tekst jest pod źródłowym linkiem. Ich cache może zostać unieważniony po pobraniu zmienionej treści. **Domyślnie nie ma limitu wieku ani automatycznego wygaśnięcia demo po 8 miesiącach** (`WINDOW_MONTHS=0`). Opcjonalne okno `WINDOW_MONTHS=N` stosuje się również do demo.

Eksport zestawu z działającej bazy: `python manage.py export_demo`. W Dockerze, aby zachować nowy plik poza kontenerem:

```powershell
docker compose exec web python manage.py export_demo --out /data/demo_innovations.json
docker compose cp web:/data/demo_innovations.json ./analysis/data/demo_innovations.json
```

Eksporter sprawdza linki i określone wzorce e-maili, telefonów oraz kluczy. Czyści pola autorów, ale fragmenty publicznego tekstu mogą zawierać nazwiska; to nie jest pełna anonimizacja treści.

`analysis/examples.py` to osobny zbiór **29 syntetycznych przykładów zespołu**. `/skutecznosc/` oraz `python manage.py evaluate_filter` mierzą na nim filtr `rules`, a nie jakość Gemini/Groq na rzeczywistym internecie. `python manage.py demo_cases --backend rules` przetwarza dwa takie przykłady i zapisuje je w bazie — używaj bazy testowej. Bez tej opcji `demo_cases` domyślnie korzysta z AI i zużywa limit.

**Stan weryfikacji 22.11.2026:** cały zestaw **325 testów offline** przeszedł po połączeniu audytu kodu (308 testów) i PR #7 (17 dodatkowych testów). `check`, `makemigrations --check --dry-run` i `pip check` bez problemów. Sprawdzono strukturę 137 wpisów rejestru i zgodność zapisanych cytatów wszystkich 21 pozycji demo z ich fragmentami tekstu; nie jest to ponowna kontrola dostępności wszystkich stron w internecie. W audycie nie wykonywano nowych zapytań AI. Wcześniejsze rzeczywiste próby Gemini obejmowały dwa rozwiązania i wiadomość kontrolną. „Sprawdź u nas” sprawdzono z kontrolowaną odpowiedzią i w przeglądarce; dwa rzeczywiste scenariusze pozostają do weryfikacji po odnowieniu limitu. To nie jest pomiar jakości AI na reprezentatywnym zbiorze.

Audyt objął również polecenia administracyjne, obsługę zgłoszeń, wzorce wykrywania kluczy przy eksporcie i kontekst obrazu Docker. `.tmp_x`, lokalne archiwum i inne pliki robocze są wyłączone z budowania obrazu. Diagnostyka odrzuconego eksportu podaje kategorię problemu, bez drukowania znalezionego klucza lub kontaktu. Minimalna wersja Django podniesiona do zainstalowanej 5.2.19; gałąź 5.2 LTS jest nadal wspierana ([Django: wspierane wersje](https://www.djangoproject.com/download/), [wydanie 5.2.19](https://docs.djangoproject.com/en/5.2/releases/5.2.19/)). Pełnego audytu wszystkich zależności pod kątem CVE nie przeprowadzano.

## Przechowywanie danych

SQLite działa w trybie WAL. Web i worker współdzielą trwały wolumen `radar-data`: baza `/data/db.sqlite3`, archiwum i kopie w `/data/archive`. Hosting z dyskiem tymczasowym traci zebrane dane przy restarcie; samo odtworzenie demo ich nie przywróci. Nie wybrano ani nie sprawdzano darmowego hostingu.

Polityka `analysis/retention.py` działa automatycznie z workerem. `python manage.py cleanup_storage` jest próbą bez zmian; `--apply` wykonuje politykę po wymuszonej kopii SQLite.

- **Interesujące** (`widok=glowna`): potwierdzona przez filtr inicjatywa, ocena AI co najmniej 50, co najmniej jeden zweryfikowany cytat i wiarygodność inna niż niska. Nieustalona data sama nie blokuje publikacji.
- **Do weryfikacji** (`widok=weryfikacja`): artykuły oczekujące na AI i przeanalizowane, ale niepotwierdzone. Zwykła kolejka ma TTL 48 h i limit 300 pobranych rekordów; osobny limit znalezionych URL-i to 300.
- **Wszystkie** (`widok=wszystkie`): zachowane artykuły po analizie, z werdyktem `glowna` lub `weryfikacja`; nie obejmuje jeszcze nieprzeanalizowanych.
- Odrzucone materiały, np. ocena poniżej 50 lub brak innowacji, są usuwane. Zostaje `Rejected`: URL, powód i hash ocenionego tekstu. Dla błędów technicznych hash może być pusty. Nigdy nieoceniona pozycja po TTL/przepełnieniu odpada bez wpisu, aby mogła zostać znaleziona ponownie.
- Wpisy `Rejected` domyślnie wygasają po 12 miesiącach i mają limit 20 000. Kopie SQLite: dwie ostatnie, zwykle co najmniej 24 h między kopiami; ręczne `--apply` wymusza kopię. Przy włączonym oknie wieku archiwum zachowuje maksymalnie 2000 rekordów.
- Dostępność źródła potwierdzonych pozycji jest sprawdzana co 14 dni, do 10 na cykl. Po 3 kolejnych błędach karta wraca do weryfikacji i jest chroniona przed zwykłym TTL/limitem kolejki; kolejne udane sprawdzenie może przywrócić poprzedni werdykt. To kontrola dostępności, nie dowód aktualności wszystkich twierdzeń.
- Zgłoszenia z formularza mają wyjątki od automatycznego usuwania; odrzucone zgłoszenie usuwa się po TTL wraz z danymi kontaktowymi. Scenariusze organizacji mają osobne 7 dni przechowywania.

## Źródła i rozszerzanie zasięgu

Rejestr: `collection/data/sources.json`; startowe domeny odkrywania: `collection/data/discovery_seeds.json`. Obsługiwane są listy HTML, RSS/Atom i sitemap, w tym ograniczone indeksy sitemap. Obowiązują robots.txt, opóźnienia, limit 2 MB odpowiedzi oraz kontrola URL-i i przekierowań.

Domyślne odkrywanie to **`seeds,links`**, co 24 godziny (`DISCOVERY_AUTO_HOURS=0` wyłącza automatyczne odkrywanie). Kandydaci przechodzą kontrolę techniczną i przy `DISCOVERY_AUTO_APPROVE=1` mogą być aktywowani automatycznie. Staff może skorygować listę źródeł. Opcjonalne adaptery SearXNG/Brave wymagają jawnego dodania dostawcy w `DISCOVERY_PROVIDERS` i odpowiednio adresu/klucza; sam klucz nie włącza wyszukiwania. Nie są potrzebne do podstawowej, bezpłatnej konfiguracji.

Polecenia administracyjne (wykonują pobieranie i mogą zmieniać dane):

```text
python manage.py probe_sources --registry --write
python manage.py probe_sources
python manage.py discover_sources --provider seeds --dry-run
python manage.py collect_sources --once --all
```

`probe_sources --registry --write` zapisuje wynik do pliku rejestru; w Dockerze zmieniony plik trzeba skopiować na host, aby zachować go po przebudowie. `collect_sources --once --all` pomija termin źródła, ale respektuje blokadę aktywnego przebiegu i 24-godzinny odstęp ponownego pobierania artykułu; wykonuje też analizę AI, odkrywanie i czyszczenie. Nie jest poleceniem samej kontroli zdrowia.

## API, priorytet i dane użytkowników

Eksport: `/api/innowacje.json` i `/api/innowacje.csv`, do 2000 rekordów, z filtrami `widok`, `woj`, `kto`. Inne rozszerzenia zwracają 404. Eksport nie zawiera pól autorów, kontaktów ani scenariuszy organizacji. Pole `kompletnosc` / `completeness` pozostaje dla zgodności API: w trybie AI oznacza liczbę zweryfikowanych cytatów względem czterech miejsc, a nie kompletność wiedzy o projekcie. `/api/szukaj/?q=...` obsługuje wyszukiwanie, `/api/status/` pokazuje stan zbierania, `/health/` sprawdza bazę. Wersja pochodzi z `settings.APP_VERSION`.

Domyślne sortowanie katalogu: priorytet PCI, ocena AI, data publikacji. Sektory „Lotnictwo i kosmos”, „Motoryzacja”, „IT i sztuczna inteligencja”, „Zdrowie i medycyna” otrzymują +2 priorytetu, wybrane województwo +1 (`PRIORITY_REGION=podkarpackie`, puste wyłącza bonus). Nie zmienia to oceny ani werdyktu. Odbiorca z tego samego województwa otrzymuje +1 pkt dopasowania.

Zgłoszenia są dostępne dla szkół, uczelni, samorządów, innych instytucji, firm, NGO i osób prywatnych. Formularze mają CSRF i ukryte pole przeciw automatom. Kontakt wymaga zgody i jest widoczny dla staffu; nazwisko zgłaszającego jest publiczne na jego życzenie. Publicznie wymienieni autorzy publikacji mogą być pokazani, gdy ich nazwiska znajdują się w tekście źródła. Szczegóły: `/o-systemie/`.

## Kontrola i testy bez zapytań AI

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python -m pip check
docker compose exec -e GEMINI_API_KEY= -e GROQ_API_KEY= web python manage.py test tests --noinput
```

Testy nie wczytują lokalnego `.env`, ale mogą dziedziczyć zmienne procesu, dlatego klucze są jawnie czyszczone w poleceniu Docker. Do pełnego zestawu używaj czystego kodu bez lokalnego `.env`: podprocesy testujące konfigurację startu mogą ten plik wczytać. Obraz Docker wyklucza `.env` i jest sprawdzaną ścieżką testową. Nie nadpisuj `DB_PATH` adresem roboczej bazy na potrzeby testów ręcznych.

Kontrola linków bez wysyłania formularzy, przy działającym serwerze: `python scripts/check_links.py http://127.0.0.1:8000 --no-external --out raport_linkow.txt`. Usuń `--no-external`, aby sprawdzić także adresy zewnętrzne. Skrypt odwiedza strony i zapisuje raport; nie mierzy jakości analizy AI.

Konto administratora: `docker compose exec web python manage.py createsuperuser`.

## Ograniczenia MVP

PDF-y, skany, strony wymagające JS lub logowania nie są obsługiwane. Ochrona przed SSRF jest podstawowa, bez pełnej ochrony przed DNS rebinding. Dopasowanie i TF-IDF nie zastępują analizy eksperta ani pełnego wyszukiwania patentowego. Pomyślne testy programu i zgodność cytatów nie dowodzą trafności oceny AI. Jakość AI na większym oznaczonym zbiorze oraz dwa rzeczywiste scenariusze „Sprawdź u nas” pozostają do sprawdzenia.
