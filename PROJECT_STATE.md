# PROJECT_STATE — 2026-11-21

## FAQ (finalna generacja)
- Obszary Technologiczne/Edukacyjne/Administracyjne (`analysis/core.py: AREAS`, pochodne od sektora), filtr dojrzałości (etap), TRL 1–9 jako szacunek AI (`data["ai"]["trl"]`, bez zmiany `AI_VERSION`: starsze analizy go nie mają), porównanie 2–4 pozycji (`/porownaj/`), formularz przemianowany na „Wskaż istniejące rozwiązanie” (FAQ: to nie platforma pomysłów).

## V0.1: zakres

Automatyczny kolektor publikacji: HTML/RSS/sitemap, zapis SQLite WAL, deduplikacja URL/tekstu, harmonogram, historia przebiegów, błędy, ponowienia i ponowna kontrola starych artykułów. Interfejs PL: lista, filtry, paginacja, pełny tekst, źródła i historia. Zarządzanie źródłami przez Django admin.

Docker automatycznie wykonuje migracje i `seed_sources`, zachowuje ustawienia istniejących źródeł i uruchamia worker po gotowości web. Restart kontenerów ma politykę `unless-stopped`.

## Weryfikacja

- 28 testów offline przeszło podczas prac nad V0.1.
- Worker w tle pobrał 19 publikacji (PWr: 8, UR: 11). Powtórny przebieg nie dodał duplikatów; końcowo brak błędów artykułów.
- Wyniki końcowego uruchomienia zapisane w `docs/V0_1_VERIFICATION.md`.

## V0.2 (w toku) — zrobione

- `analysis/`: analiza regułowa po polsku (bez LLM): sektor, etap, autorzy, sygnały innowacyjności, rubryka 5 kryteriów (0–3 lub „brak danych”) z cytatami weryfikowanymi w tekście, potencjał i kompletność dowodów osobno, ścieżka (rozwój/transfer/komercjalizacja/wdrożenie) z uzasadnieniem i brakami. Wyniki w cache (klucz: wersja + backend + hash tekstu).
- Worker analizuje nowe publikacje po każdym cyklu; ręcznie: `python manage.py analyze [--force]`.
- UI: blok analizy w karcie, filtry (ścieżka, sygnały), sortowanie po potencjale.
- Wyszukiwanie po zapytaniu: `/api/szukaj/?q=...&n=5` (TF-IDF z prefiksami, bez zewnętrznych usług), zwraca artykuły + podsumowanie analizy.
- Formularz „Zgłoś innowację” (`/zglos/`): wklejony opis albo URL (pobierany przez `safe_get`), ten sam potok analizy, deduplikacja.
- 52 testy offline przechodzą (python 3.10, Django 5.2).

## 2026-11-21 (popołudnie) — zrobione

- Naprawiono radar: zakładki werdyktu zniknęły z `web/views.py` przy scalaniu z kodem kandydatów źródeł (szablon ich oczekiwał, test padał). Przywrócone.
- Decyzja eksperta dla publikacji (`Analysis.review_*`, POST `/a/<id>/ocena/`, `_review.html`), zakładka „Zatwierdzone przez eksperta”; decyzja eksperta nadpisuje werdykt w zakładkach.
- `/skutecznosc/`: lejek, zgodność z ekspertem, wynik na przykładach (`analysis.evaluation.evaluate`), jakość źródeł.
- Priorytet PCI (`analysis.core.priority`, pole `Analysis.priority`, sortowanie „Priorytet PCI”); nowe sektory „Lotnictwo i kosmos”, „Motoryzacja”. `VERSION = "3"` → worker przelicza analizy. Metryki `evaluate_filter` bez zmian (100%/100%, ściśle 100%/67%).
- `LICENSE` EUPL-1.2. 98 testów offline.

## 2026-11-21 (wieczór) — wymagania zadania domknięte

- Innowacje nietechnologiczne: reguły etapu/dowodów/przenośności/opisu rozwiązania (wprowadzono, uruchomiono, przejęły, program, procedura…), sektor „Pomoc społeczna i włączenie”, pole „Typ innowacji” (technologiczna/edukacyjna/organizacyjna/społeczna/procesowa). +10 oznaczonych przykładów (szkoła, gmina, MOPS, szpital, przedszkole; dożynki, sesja rady…). `evaluate_filter`: 29 przykładów, 0 błędów.
- Rejestr: +szkoła (Liceum UR), JST (Miasto Rzeszów, Powiat Jasielski, Gmina Jasło), PANS Jarosław/Krosno, PCI, MEN — `verified: false`, potwierdzić `probe_sources --registry --write`.
- „Szukam rozwiązania” (`/potrzeby/`): instytucja zgłasza potrzebę → dopasowane innowacje (`matching.recipients.match_articles`); kontakt tylko za zgodą, widoczny dla staff. Nowe profile: lotnictwo/kosmos, motoryzacja, pomoc społeczna.
- „Co dalej z tą innowacją” (`Analysis.handling*`, POST `/a/<id>/dalej/`): etapy z historią i partnerem; lejek na `/skutecznosc/`.
- Linki do baz z pkt 7 zadania (`analysis/external.py`), eksport `/api/innowacje.json|csv`, sekcja RODO w „O systemie”.
- `manage.py demo_cases`: scenariusz a)–e) dla przypadku A (czujnik sepsy) i B (gmina). 113 testów.

## 2026-11-21 (wieczór, cd.) — województwa i użytkownicy

- `analysis/regions.py`: 16 województw, wykrywanie z tekstu, `Source.region`, `Analysis.region`, filtr `woj` (radar, eksport), `PRIORITY_REGION`, +1 pkt dopasowania za to samo województwo, wybór województwa w formularzach. `VERSION = "5"`; klucz cache zawiera region źródła.
- Użytkownicy: `Source.ORG` + firma prywatna / NGO / osoba prywatna; `collection.Submission` (kto zgłasza, województwo, autor i kontakt za zgodą); filtr `kto`; typ odbiorcy „Osoba prywatna”; honeypot; strona „Dla kogo”. 128 testów.

## 2026-11-21 (noc) — design z makiety

- Interfejs przeniesiony na neo-brutalistyczny system z `radar-innowacji-makiety.html`: `web/static/web/radar.css` (tokeny, jasny/ciemny motyw, przełącznik w sidebarze), `base.html` (sidebar + topbar), ikony `_icons.html`, logo `_logo.html`, partiale `_card.html`, `_score.html`, `_rubric.html`, tagi `web/templatetags/web_extras.py`.
- Nowa strona „Przegląd” pod `/` (`views.overview`); katalog przeniesiony na `/inicjatywy/` (nazwa URL `radar` bez zmian), filtr sektora (`?sektor=`), układ karty/tabela (`?uklad=tabela`).
- Karta inicjatywy: panel „Potwierdzone informacje” (fakty ze źródła) obok „Interpretacja systemu” (przerywana ramka = szacunek), rubryka z cytatami w osobnej sekcji. „Brak danych” ma własny wygląd (nie „niski wynik”).
- Odstępstwa od makiety: brak osobnej strony „Analiza AI” (analiza jest w karcie), brak plakietki „dane przykładowe” (dane są prawdziwe), etykiety „szacunek systemu” zamiast „szacunek AI” (backend `rules` nie jest AI).
- Naprawiono `about.html`: blok RODO trafiał do `<title>` i był zdublikowany.
- Po `git pull` wymagane `python manage.py migrate` (brak kolumny `analysis_analysis.verdict` w starej bazie).

## 2026-11-21 (noc) — przechowywanie danych bez ręcznej moderacji

- Usunięto decyzję eksperta (pola `Analysis.review_*`, URL `/a/<id>/ocena/`, zakładki „Zatwierdzone przez eksperta” i „Odrzucone”, link do logowania). Ocena w pełni automatyczna; staff zostaje tylko do etapów „Co dalej”, kontaktów RODO i (opcjonalnie) listy źródeł.
- Trzy listy: Interesujące / Do weryfikacji / Wszystkie (`analysis/tabs.py`, jedna definicja dla widoków, eksportu i polityki).
- `analysis/retention.py` + `manage.py cleanup_storage`: brak limitu wieku (FAQ; opcjonalnie `WINDOW_MONTHS`), kontrola aktualności źródła (`analysis/currency.py`, 3 błędy → Do weryfikacji), ocena AI < 50 i duplikaty → usunięcie z tombstone w `Rejected` (wygasa), kolejka „Do weryfikacji” z TTL 48 h i limitem, sprawdzanie daty w źródle przed usunięciem, kopia zapasowa SQLite. Hak w pętli `collect_sources`. Migracje: `analysis 0008`, `collection 0007`.
- Testy: 202 offline (`tests/test_retention.py`, `tests/test_review.py::TabsAndPagesTests`).
- Ograniczenia: analizy z dawnego filtra regułowego wracają do kolejki (limit kolejki + dzienne limity free AI), nadmiar po 48 h znika; Groq nie testowany z prawdziwym kluczem; treść oficjalnego zadania niedostępna — zgodność sprawdzona tylko z tabelą w README.

## 2026-11-21 (noc, cd.) — zestaw demonstracyjny

- `analysis/demo.py`, `manage.py export_demo` / `load_demo`, plik `analysis/data/demo_innovations.json`: rzeczywiste publikacje potwierdzone przez AI (tytuł, instytucja, data, link, źródło, ocena AI + uzasadnienie, krótki fragment tekstu i cytaty; bez autorów, kontaktów i kluczy). Ładowanie idempotentne, tylko wstawianie, pomijane na bazie z własnymi rekordami; Docker uruchamia je po `seed_sources`.
- Pozycje demo: `Analysis.data["demo"]`, znacznik „Demo · wstępna ocena AI” (karta, szczegóły, lista, przegląd). `analyze_pending` nie degraduje analizy AI do reguł; pozycje demo nie są analizowane ponownie.
- Ograniczenie: w bazie pozycji demo tekst to fragment (początek + cytaty), pełna treść pod linkiem; po zmianie `AI_VERSION` pozycje zostaną przeliczone jak zwykłe.

## Następne kroki

1. Backend `ollama` w `analysis/service.py` BACKENDS (finalize() już odrzuca niezweryfikowane cytaty); sprawdzić na Macu.
2. Więcej źródeł (cel 4–6).
3. „Podobne rozwiązania” w karcie (ponowne użycie `analysis/search.py`), profile odbiorców, strona „O systemie”.

Ograniczenia: reguły to słowa kluczowe — sygnały, nie werdykt. Zbieranie obejmuje tylko skonfigurowane źródła, nie cały internet. V0.1 nie nazywa zwykłych wiadomości potwierdzonymi innowacjami.

## 2026-11-21 (wieczór) — rozszerzenie rejestru źródeł
- `collection/data/sources.json`: 137 wpisów (było 42), 96 zweryfikowanych przez `probe_sources --registry --write` na prawdziwej sieci (RSS 32, HTML 64); 41 czeka jako kandydaci (robots.txt blokuje / 403–503 / brak listy aktualności / timeout) — powód w polu `note`.
- Naprawa: `probe_site` obsługuje `entry_url` będący kanałem RSS (wcześniej wyjątek lxml przerywał cały przebieg); `probe_sources` nie przerywa przebiegu przy błędzie jednej strony. Test regresji `test_feed_as_entry_url`.
- Cztery adresy z listy kandydatów były błędne (brak DNS) i zostały poprawione po wyszukaniu: WUP Rzeszów, UM Tarnobrzeg, Kuratorium Oświaty w Rzeszowie, IZTECH.
- Weryfikacja = strona odpowiada, robots.txt pozwala, jest RSS lub lista ≥3 artykułów. To nie ocena jakości źródła.

## 2026-11-21 (noc) — analiza AI za 0 PLN
- Zasada: zero kosztów. Bez billingu, bez płatnych API, bez Google Search Grounding. Wyszukiwanie źródeł: tylko `seeds` + `links` (SearXNG/Brave działają tylko, gdy admin je skonfiguruje).
- Analiza (`analysis/llm.py`): Gemini free tier (`gemini-3.1-flash-lite`) → Groq free plan (`llama-3.3-70b-versatile`, tryb JSON). Klucze tylko w env/`.env` (`GEMINI_API_KEY`, `GROQ_API_KEY`); `.env` jest git-ignorowany i nie jest ładowany w testach.
- 429 nie jest powtarzany: dostawca idzie na pauzę (Retry-After, inaczej 2 min → 6 h; zapis w `LLMState`), analiza przechodzi na kolejnego. Gdy żaden nie działa, artykuł zostaje w kolejce do powrotu limitu; nigdy nie jest oceniany wzorem. Ponowienia tylko dla błędów sieci/5xx (max 2). Limity dzienne w `LLMUsage`, odstępy między wywołaniami pod limity RPM/TPM.
- Cache: wynik w `Analysis` (klucz = tekst + wersja promptu, bez modelu), więc zmiana modelu/dostawcy nie zużywa tokenów ponownie.
- `analysis/ai.py`: ocena 0–100, uzasadnienie, braki, niepewność; cytaty weryfikowane w tekście; `data["verified"]` oddzielone od `data["ai"]`. Publikacja (`glowna`): inicjatywa + ocena ≥50 + cytat (brak daty nie blokuje) + wiarygodność ≠ niska.
- Okno wieku (`collection/window.py`) jest WYŁĄCZONE domyślnie (`WINDOW_MONTHS=0`, FAQ); po włączeniu działa na liście linków, przy pobraniu i przed AI. Starsze → najpierw archiwum `archive/old_articles.jsonl.gz` (pełny rekord + analiza), potem wpis w `Rejected`. Odrzucone przez AI (ocena <50) → tylko `Rejected` (URL, hash, powód). Zgłoszenia z formularza i pozycje po ocenie eksperta nigdy nie są usuwane.
- 2026-11-21: `prune_window --apply` wykonane na bazie: 756 zarchiwizowanych (kopia bazy przed zmianą: `archive/db_before_prune_*.sqlite3`; katalog `archive/` jest w `.gitignore`).
- Źródła: kandydaci z `seeds`/`links` po probe (robots, linki do artykułów) włączają się sami (`DISCOVERY_AUTO_APPROVE=0` przywraca zatwierdzanie ręczne); `DISCOVERY_AUTO_HOURS` domyślnie 24.
- Etapy: `Article.pipeline_status` (znaleziono/zweryfikowano/przeanalizowano/opublikowano/błąd; odrzucono = `Rejected`), `service.pipeline_counts()`, wypis w `manage.py analyze`.
- Ograniczenia: Groq nie był sprawdzony na prawdziwym kluczu (brak `GROQ_API_KEY`), tylko na mockach; tokeny free tier Groq 70B ≈ 100 tys./dzień (~50 artykułów); na Render (efemeryczny dysk) archiwum przepada przy redeployu; zgłoszenia bez daty trafiają do „do weryfikacji”.
- 2026-11-21: `probe_sources` odrzuca kandydata będącego duplikatem aktywnego źródła (`last_error: Duplikat źródła #id`); sprawdzono 58 kandydatów: 17 duplikatów odrzucono, 5 nowych włączono, 36 zostało do ręcznej decyzji (robots / 403-503 / brak listy publikacji).
