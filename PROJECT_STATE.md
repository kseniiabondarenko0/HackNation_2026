# PROJECT_STATE — 2026-11-22

## Architektura
Django 5.2 + SQLite (WAL), Docker (web na gunicorn + worker `collect_sources`). Aplikacje: `collection` (rejestr źródeł, kolektor HTML/RSS/sitemap, SSRF-safe `safe_get`, deduplikacja, harmonogram, zgłoszenia), `analysis` (analiza AI, werdykt, ścieżki, regiony, retencja, demo), `matching` (profile odbiorców, potrzeby, podobne rozwiązania TF-IDF), `web` (interfejs PL, neo-brutalistyczny system z makiety, API/eksport). Zero kosztów: Gemini free → Groq free (REST przez httpx), bez Google Search Grounding.

## Zaimplementowane
- **Zbieranie:** rejestr `collection/data/sources.json` (137 wpisów, 96 zweryfikowanych `probe_sources`), automatyczne odkrywanie kandydatów (`seeds` + linki ze stron), ponowne próby, kontrola aktualności źródła co 14 dni.
- **Analiza:** `analysis/ai.py` + `llm.py`: ocena 0–100, uzasadnienie, braki, niepewność, sektor, typ innowacji (także edukacyjne, organizacyjne, społeczne), etap, TRL tylko gdy dotyczy, cytaty weryfikowane w tekście (`data["verified"]` oddzielone od `data["ai"]`). Cache niezależny od modelu; 429 → pauza dostawcy, nigdy ciche przejście na reguły. `analysis/rules.py` zostaje jako reguły pomocnicze i zbiór przykładów do testów.
- **Listy:** Interesujące (AI ≥ 50 + cytat) / Do weryfikacji (kolejka z TTL 48 h) / Wszystkie. Polityka przechowywania w `analysis/retention.py` (`cleanup_storage`), tombstone `Rejected`, kopie SQLite.
- **Funkcje z zadania:** ścieżka (rozwój/transfer/komercjalizacja/wdrożenie) z „czego brakuje”, podobne rozwiązania (TF-IDF), linki do baz zewnętrznych (UPRP, EPO, PBN, PPM, PAN, Interreg), „Szukam rozwiązania” (dopasowanie), „Co dalej z tą innowacją”, `/porownaj/`, priorytet PCI i filtr województw, formularze zgłoszeń z RODO, eksport JSON/CSV, `demo_cases` (dwa przypadki a)–e)).
- **Demo:** `analysis/data/demo_innovations.json` (rzeczywiste publikacje z oceną AI), `load_demo`/`export_demo`, znacznik „Demo · wstępna ocena AI”.
- **Twardnienie:** `DJANGO_DEBUG=0` wymaga własnego `DJANGO_SECRET_KEY`; `/robots.txt`, `/favicon.ico`; `/health/`.
- **Testy:** 307 offline (`python manage.py test tests --noinput`); przeszły na czystej kopii bez lokalnego `.env` i prawdziwych kluczy.
- **Funkcja dodatkowa „Sprawdź u nas”:** na karcie publikacji scenariusz transferu dla celu, zasobów i ograniczeń organizacji: bariery, pytania, kroki pilotażu i proponowane mierniki. Weryfikacja cytatów, jawne oddzielenie wniosków AI, cache według tekstu i warunków, wycofanie starego wyniku po zmianie źródła. Scenariusze prywatne dla sesji, TTL 7 dni, limit 8 nowych/godzinę. Kolejka AI pozostawia 10 zapytań w dotychczasowym budżecie dziennym na interakcję.
- **Tryb pokazowy:** `DEMO_MODE=1` w `.env` wstrzymuje pracę kolektora w tle (bez pobierania, czyszczenia i wywołań AI), więc aplikacja startuje od razu na zestawie demonstracyjnym, a limit Gemini zostaje na zapytania z interfejsu. Stopka, `/zrodla/` i `/api/status/` pokazują ten tryb.
- **Wyszukiwanie w katalogu:** nie zależy od wielkości liter ani polskich znaków diakrytycznych (`analysis.search.fold`).

## Znane ograniczenia
- Ocena AI to szacunek, nie werdykt; zbieranie obejmuje tylko skonfigurowane źródła, nie cały internet.
- Groq (domyślnie `openai/gpt-oss-120b`, bo `llama-3.3-70b-versatile` wygasa 2026-08-16) sprawdzony tylko na mockach (brak prawdziwego klucza); błędy konfiguracji (zły klucz, nieistniejący model) wstrzymują dostawcę na 1 h i nie zużywają prób artykułów. Limity free tier: Gemini RPD/TPM, Groq ok. 100 tys. tokenów/dzień.
- `/skutecznosc/` liczy dokładność na 29 oznaczonych przykładach przez `analysis.evaluation.evaluate`, domyślnie z backendem `rules`, czyli mierzy filtr regułowy, a nie model AI. Strona podaje to wprost.
- Hosting z dyskiem tymczasowym gubi bazę przy restarcie (demo wraca przez `load_demo`). Zbieranie wymaga działającego workera.
- PDF-y, skany i strony wymagające JS/logowania nie są obsługiwane. Ochrona przed SSRF to warstwa podstawowa (bez ochrony DNS rebinding).

- Zapytanie „Sprawdź u nas” do prawdziwego Gemini nie zostało jeszcze sprawdzone (limit dzienny był wyczerpany, a środowisko weryfikacji nie miało dostępu do API Google). Przebieg A→B sprawdzono na lokalnej atrapie HTTP w przeglądarce (desktop i telefon); atrapa nie jest modelem i nie dowodzi jakości odpowiedzi. Do zrobienia lokalnie z własnym kluczem: scenariusze A i B z README, po jednym zapytaniu.
- Docker Compose nie był uruchamiany w środowisku weryfikacji (brak demona). Zmiana dotyczy tylko zmiennej `DEMO_MODE` w `.env` i polecenia `collect_sources`.
- Okno wieku (8 mies.) jest domyślnie wyłączone zgodnie z FAQ; włącza je `WINDOW_MONTHS=8`.

## Następne kroki
1. Metryki `/skutecznosc/` dla modelu AI: 20–30 oznaczonych tekstów przez Gemini, precyzja i kompletność.
2. Więcej rzeczywistych pozycji z Podkarpacia (samorządy, szkoły) w zestawie demonstracyjnym.
3. Sprawdzenie Groq na prawdziwym kluczu; pokaz z `load_demo`, bez zależności od limitów.

## Weryfikacja Gemini i poprawki — 22.11.2026

Klucz ustawiony wyłącznie w lokalnym `.env` (ignorowany przez Git i kontekst obrazu). Użytkownik potwierdził Free Tier bez rozliczeń. Metadane modelu `gemini-3.1-flash-lite`: HTTP 200. Przed pierwszą analizą zrobiono kopię SQLite.

Trzy rzeczywiste wywołania Gemini, wszystkie zakończone poprawnie:

| Przypadek | Wynik | Cytaty | Czas całej analizy |
|---|---|---|---|
| Beton z PET, PWr (`/a/5/`) | Interesujące, 85/100 | 4/4 zgodne z zapisanym tekstem | 3,27 s |
| Streetbus / pomoc MOPS, Wrocław (`/a/1211/`) | Interesujące, 85/100; społeczna / organizacyjna | 3/3 zgodne z zapisanym tekstem | 4,87 s |
| Międzynarodowy Dzień Studenta, UR | Odrzucone, 5/100; kontrola negatywna | — | 3,78 s |

Powtórny odczyt analizy PWr użył cache, bez kolejnego wywołania API. Kontrola negatywna nie usuwała rekordu źródłowego. To test działania na trzech przypadkach, nie pomiar precyzji AI na reprezentatywnym zbiorze.

Poprawki pokryte regresjami w `tests/test_pipeline_recovery.py`:
- Walidacja typów, wymaganych pól i wartości enum odpowiedzi przed analizą; błędny kształt odpowiedzi trafia do ograniczonych prób artykułu, a dalsze artykuły są przetwarzane. Możliwy fallback na kolejnego dostawcę.
- Zmiana tekstu atomowo wycofuje stare cytaty i ocenę z bieżącej karty. Ostatni tekst i analiza zostają w prywatnym `_previous`, bez zagnieżdżania historii; etapy obsługi pozostają. Nowy tekst dostaje nowe próby analizy i czas na przetworzenie.
- Po awarii źródła wstrzymane karty ponownie trafiają do kontroli aktualności i mogą odzyskać poprzedni werdykt, gdy źródło wróci.
- Worker przetwarza niewielką porcję AI po każdym źródle (2 próby) oraz resztę po cyklu, w ramach dziennych limitów.
- Interfejs pokazuje liczbę zweryfikowanych cytatów zamiast sugerować „100% kompletności”; opis oceny odróżnia AI od rubryki trybu rules.

Po aktualizacji Docker: web zdrowy, worker uruchomiony, klucz dostępny w obu procesach. Sprawdzono 17 stron/API przez HTTP (200), w tym obie karty i porównanie. `check`, `makemigrations --check --dry-run` i `pip check` bez problemów. W przeglądarce potwierdzono prawdziwą kartę Gemini i katalog bez znaczników demo przy tych dwóch pozycjach.

O 04:46 Europe/Warsaw potwierdzono samodzielny worker: licznik Gemini wzrósł z 3 do 11 wywołań (0 błędów), powstała kolejna analiza i 7 wpisów w rejestrze odrzuconych. W tym przedziale nie uruchamiano ręcznie analizy. Nie jest to końcowy stan bazy: zbieranie i analiza nadal pracują. Sprawdzono też brak wartości klucza w plikach repozytorium i brak pliku `.env` wewnątrz obrazu.

## „Sprawdź u nas” — implementacja i sprawdzenie

Model `TransferScenario`, migracja `0009`, serwis `analysis/transfer.py`, formularz oraz widoki `/a/<id>/sprawdz-u-nas/` i `/scenariusz/<uuid>/`. Ten sam adapter Gemini → Groq i dotychczasowe limity; żadnej nowej usługi ani zależności. Dostęp do UUID wymaga tej samej sesji; wejścia nie są publikowane ani eksportowane. Odpowiedź zachowuje się tylko po walidacji struktury i cytatów. Blokada równoległych prób i krótka pauza po błędzie ograniczają ponowne zużycie limitu.

19 nowych regresji w `tests/test_transfer.py`: poprawna odpowiedź przez prawdziwy adapter z mockiem HTTP, fallback, błędne cytaty i typy, cache mimo wyczerpanego limitu, zmienione warunki/tekst, zmiana lub wycofanie publikacji podczas analizy, prywatność sesji, CSRF/honeypot, ponowne próby, TTL i rezerwa dla interakcji. Cały zestaw 290 testów przeszedł; `check`, `makemigrations --check --dry-run`, `pip check` poprawne. Przed migracją wykonano kopię bazy; Docker przebudowany, web zdrowy i worker działa.

**Ograniczenie weryfikacji na żywo:** przed rozpoczęciem tej funkcji kolektor wykorzystał 250/250 zapytań Gemini (0 błędów). Nie zwiększano limitu i nie omijano budżetu. W roboczym interfejsie przetestowano komunikat limitu i zachowanie wpisanych odpowiedzi. Pełny przebieg formularz → wynik → edycja → cache sprawdzono w przeglądarce na osobnym kontenerze i tymczasowej bazie z jednoznacznie oznaczoną odpowiedzią testową. Nie jest to dowód jakości nowych scenariuszy wygenerowanych przez Gemini. Dwa rzeczywiste scenariusze dla różnych organizacji pozostają do sprawdzenia po odnowieniu limitu; wcześniejsze rzeczywiste testy Gemini powyżej dotyczą analizy artykułów.

## Szlif końcowy przed pokazem — 22.11.2026

Zakres: niezawodność „Sprawdź u nas”, odporność na błędy AI, pokaz bez czekania na zbieranie w tle. Szczegóły decyzji w `DECISIONS.md`.

- **„Sprawdź u nas”:** limity zapytań interaktywnych, tolerancyjna, ale uczciwa walidacja (cytaty niepotwierdzone odrzucane i liczone, brak wyniku bez potwierdzonego cytatu), panel „Co się zmieniło po zmianie warunków” (zmienione warunki, nowe i zniknięte bariery, kroki i pytania), komunikaty błędów po polsku z zachowaniem formularza (limit, sieć, klucz/model, odmowa, budżet, brak klucza, niepoprawna odpowiedź, wstrzymanie dostawcy), reset formularza po powrocie w przeglądarce, ostrzeżenie przy długim oczekiwaniu.
- **Układ na telefonie:** usunięto poziome przewijanie na kartach, w tabelach i przy długich adresach (18 stron sprawdzonych przy szerokości 390 px).
- **Tryb pokazowy:** `DEMO_MODE` (patrz wyżej).
- **Szybki start bez Dockera:** po `cp .env.example .env` (`DJANGO_DEBUG=0`) strony wyświetlały się bez stylów, bo `collectstatic` nie był uruchamiany (`/static/web/radar.css` zwracał 404). `WHITENOISE_USE_FINDERS=True` serwuje pliki statyczne wprost z katalogów aplikacji; test regresji w `tests/test_demo_mode.py`. W Dockerze nic się nie zmienia (obraz nadal wykonuje `collectstatic`).
- **Dokumentacja:** README opisuje pokaz dla jury i nie twierdzi już, że zestaw demo wygasa po 8 miesiącach.

Sprawdzono (22.11.2026, środowisko bez dostępu do API Google i bez demona Dockera):
- 307 testów offline przeszło (także na czystym klonie z naniesioną poprawką, bez lokalnego `.env`); `check` i `makemigrations --check --dry-run` bez uwag.
- Przeglądarka (Chrome, desktop 1440 px i telefon 390 px): ścieżka karta → „Sprawdź u nas” → scenariusz A → „Zmień warunki i przelicz” → scenariusz B z panelem zmian; brak błędów konsoli i sieci, brak poziomego przewijania. Odpowiedzi pochodziły z lokalnej atrapy, więc to test działania interfejsu i walidacji, nie jakości modelu.
- Tryby błędów w przeglądarce (limit 429, błąd 500, niepoprawny JSON, pusta odpowiedź, wymyślony cytat): każdy pokazuje właściwy komunikat po polsku, zachowuje formularz i nie zapisuje fałszywego wyniku.
- Szybki start z README (bez Dockera) na czystym klonie: migracje, `seed_sources`, `load_demo`, `runserver`; strony i arkusz stylów zwracają 200 (przed poprawką styl dawał 404).
- Dane demo (21 pozycji): każda w katalogu głównym ma ocenę AI ≥ 50 (65–90), co najmniej jeden zweryfikowany cytat i link https; brak duplikatów adresów i treści.
- Skan wzorców kluczy API (Gemini, Groq) w plikach repozytorium, historii Gita (24 commity) i logach: bez trafień.

Nie sprawdzono: prawdziwe wywołanie Gemini dla scenariuszy, uruchomienie Docker Compose, publiczny hosting.
