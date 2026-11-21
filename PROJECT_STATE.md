# PROJECT_STATE — 2026-11-21

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
