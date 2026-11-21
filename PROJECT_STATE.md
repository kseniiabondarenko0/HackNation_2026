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

## Następne kroki

1. Backend `ollama` w `analysis/service.py` BACKENDS (finalize() już odrzuca niezweryfikowane cytaty); sprawdzić na Macu.
2. Więcej źródeł (cel 4–6).
3. „Podobne rozwiązania” w karcie (ponowne użycie `analysis/search.py`), profile odbiorców, strona „O systemie”.

Ograniczenia: reguły to słowa kluczowe — sygnały, nie werdykt. Zbieranie obejmuje tylko skonfigurowane źródła, nie cały internet. V0.1 nie nazywa zwykłych wiadomości potwierdzonymi innowacjami.
