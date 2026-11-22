# DECISIONS
- **Weryfikacja 22.11.2026:** Gemini sprawdzony trzema rzeczywistymi wywołaniami (dwa rozwiązania + zwykła wiadomość), bez płatnej taryfy. Klucz tylko w lokalnym `.env`. Wyniki i ograniczenia próby w `PROJECT_STATE.md`.
- Błędny kształt JSON jest błędem odpowiedzi modelu, nigdy podstawą do odrzucenia innowacji. Zmiana tekstu wycofuje bieżącą ocenę i dowody; zachowujemy ostatni snapshot w `_previous`. Powrót źródła może odblokować kartę wstrzymaną kontrolą aktualności.
- Analiza AI działa małymi porcjami pomiędzy źródłami, żeby wynik nie czekał na pełny obieg rejestru.
- Django + SQLite (WAL): team stack (Python), zero setup; Postgres after hackathon.
- LLM za adapterem (`analysis/llm.py`): Gemini free → Groq free; pokaz działa bez żywego AI dzięki zestawowi demonstracyjnemu. Backend `ollama` porzucony (zero kosztów, brak GPU na serwerze).
- Similarity via TF-IDF in base (task asks for duplicate-work reduction).
- Manual submission form in base (task: "zgłaszanie lub wykrywanie").

- **Design (2026-11-21):** statyczny `radar.css` zamiast inline `<style>`; blok kompatybilności dla starszych klas (`.notice`, `.metric`, `button` bez klasy), żeby nie przepisywać każdej strony naraz. `/` = Przegląd, katalog pod `/inicjatywy/`. Czcionki z Google Fonts jak w makiecie (offline spada na fonty systemowe).

## AI za 0 PLN: Gemini free → Groq free (2026-11-21)
- Wymóg: projekt działa bez żadnych kosztów. Rezygnacja z Google Search Grounding (płatny/limit 0 w free tier); odkrywanie źródeł tylko `seeds` + `links`.
- Gemini i Groq przez REST (httpx), bez nowych zależności. Kolejność: Gemini, potem Groq; pauza dostawcy po 429 zamiast pętli ponowień.
- Brak cichego powrotu do wzoru/reguł: gdy oba modele niedostępne, artykuł czeka w kolejce.
- Cache niezależny od modelu: zmiana dostawcy nie zużywa tokenów drugi raz.
- Odrzucone przez AI: tylko URL + hash + powód (`Rejected`). Wiek publikacji nie odrzuca (FAQ, nadpisuje wcześniejsze okno 8 mies.; opcja `WINDOW_MONTHS`).
- Dane zweryfikowane (URL, data ze strony, cytaty znalezione w tekście) i interpretacja AI przechowywane osobno.

## Przechowywanie danych i brak ręcznej moderacji (2026-11-21)
- Ocena innowacji tylko automatyczna: usunięty login eksperta i ręczne zatwierdzanie/odrzucanie. Staff został tylko do etapów „Co dalej”, kontaktów RODO i opcjonalnej korekty źródeł.
- Baza trzyma wyłącznie: Interesujące (AI ≥ 50, cytat; bez limitu wieku) oraz krótką kolejkę „Do weryfikacji” (TTL 48 h, limit 300). Reszta jest usuwana; zostaje URL + skrót (`Rejected`, wygasa po 12 mies., limit 20 000).
- „Wszystkie” = materiały, które przeszły kontrolę AI i nie zostały usunięte (bez czekających na pierwszą analizę — te są tylko w „Do weryfikacji”).
- Brak daty ≠ stare: najpierw sprawdzenie daty w stronie źródłowej (maks. 2 próby), potem reguła `ai.decide` na zapisanej odpowiedzi AI, bez nowego wywołania modelu.
- (Okno wyłączone) Archiwum, gdy okno włączone, ma limit 2000 rekordów (wymóg „archiwum przed usunięciem” zachowany, ale ograniczony).
- Kopia SQLite przed pierwszym usunięciem w cyklu (≥ 24 h odstępu; ostatnie 2) i zawsze przy `cleanup_storage --apply`.
- Dawne analizy regułowe nie są masowo przeliczane: wracają do ograniczonej kolejki, a to, czego nie zdąży przeanalizować darmowe AI w 48 h, znika.

## Zestaw demonstracyjny (2026-11-21)
- Pokaz komisji nie może zależeć od czasu zbierania i darmowego limitu AI, więc repozytorium niesie JSON z rzeczywistymi, już potwierdzonymi publikacjami. Żadnych wymyślonych pozycji i ocen.
- `load_demo` tylko wstawia: pomija istniejące URL-e, wpisy z `Rejected` i starsze niż okno; na bazie z własnymi rekordami nic nie robi (`--force` dodaje tylko brakujące pozycje).
- W JSON: fragment tekstu zamiast pełnej treści (prawa autorskie, rozmiar), bez autorów/kontaktów/kluczy; `export_demo` sprawdza linki i odmawia zapisu przy e-mailu, telefonie lub kluczu.
- Analiza AI nigdy nie jest zastępowana wynikiem regułowym (tryb bez klucza): demo zostaje nietknięte.
- Aktualność zamiast wieku: co 14 dni kontrola strony źródłowej potwierdzonych pozycji; 3 błędy z rzędu → „Do weryfikacji”, bez usuwania (`analysis/currency.py`).
- TRL tylko jako szacunek AI z tekstu (null, gdy nie dotyczy); obszar wyliczany z sektora, bez dodatkowego wywołania AI.

## Twardnienie (2026-11-22)
- `DJANGO_DEBUG=0` bez własnego `DJANGO_SECRET_KEY` kończy się błędem startu (wartość `change-me` tylko ostrzega, żeby nie zablokować pokazu). `/robots.txt` blokuje wyłącznie `/admin/`.

## Ochrona danych przy awarii AI (2026-11-22)
- Błąd 404 oraz 400 o kluczu/modelu to błąd dostawcy (`config`, pauza 1 h), nie artykułu: nie zużywa `analysis_attempts` i nie prowadzi do `Rejected`. Zwykłe 400 (np. schemat) nadal liczy się artykułowi.
- `Rejected` z hashem tylko dla pozycji, za której ocenę AI już „zapłaciło”. Pozycja bez analizy (przepełnienie kolejki, TTL) odpada bez śladu, a po wyczerpaniu prób AI zostaje sam URL (hash pusty).
- Pozycja wstrzymana kontrolą aktualności (`currency.failures` ≥ `CURRENCY_FAILS`) nie podlega TTL ani limitowi kolejki: czeka na człowieka.
- Domyślny model Groq: `openai/gpt-oss-120b` z `reasoning_effort=low` (tokeny rozumowania wchodzą w limit wyjścia).

## Pierwszy ekran katalogu (2026-11-22)
- Domyślna kolejność katalogu: priorytet PCI, potem ocena AI, potem data publikacji (wcześniej: kolejność wykrycia, przy zestawie demo przypadkowa, więc na górze lądowały pozycje z oceną 65). Dawny parametr `sort=priorytet` działa jak domyślny; „Najnowsze” to jawne `sort=najnowsze` (data publikacji).
- Na „Przeglądzie” sekcja „Ostatnio dodane” pokazuje najnowsze publikacje (po dacie publikacji), nie kolejność ładowania.
- TRL nie jest uzupełniany ręcznie ani formułą: pochodzi wyłącznie z odpowiedzi modelu AI.

## Porządki przed pokazem (2026-11-22)
- Wyszukiwanie w katalogu ignoruje wielkość liter i polskie znaki (`analysis.search.fold`): SQLite `LIKE` zna tylko ASCII, więc „Łódź”, „łódź” i „lodz” dawały różne wyniki.
- `.env.example` ma `DJANGO_DEBUG=0` (jak obraz Dockera); usunięte pozostałości Ollamy (`OLLAMA_*`, `extra_hosts`).
- Usunięty wewnętrzny plan `docs/PLAN_V2.md` (po rosyjsku i nieaktualny: backendy Ollama, sklearn); zostaje w historii gita.

## Poprawki po przeglądzie (2026-11-22)
- `/skutecznosc/`: blok z precyzją i czułością opisany jako test filtra regułowego (tryb offline), z uwagą, że przykłady napisał zespół, a jakość analizy AI nie została jeszcze zmierzona. Wcześniej wynik 100% mógł być odczytany jako jakość Gemini lub Groq.
- Nazwa formularza w README zgodna z interfejsem: „Wskaż rozwiązanie” (wcześniej „Zgłoś innowację”).
- Usunięty `docs/V0_1_VERIFICATION.md`: raport z pierwszej wersji (Windows, Django 5.1, brak analizy AI) nie opisywał już projektu.
- `/api/innowacje.<format>`: znane są tylko `json` i `csv`, każdy inny format zwraca 404 (wcześniej każdy nieznany zwracał CSV).
- Wersja w `/health/` i `/api/status/` pochodzi z jednego miejsca (`settings.APP_VERSION`).
- Karta „Najnowsze” na Przeglądzie pokazuje datę publikacji; „Wykryto” tylko, gdy publikacja nie ma daty (data wykrycia pozycji demo to dzień załadowania do bazy).
- Porządki w kodzie: nieużywane importy, `raise ... from ...` w obsłudze błędów, `stacklevel` przy ostrzeżeniu o kluczu.
