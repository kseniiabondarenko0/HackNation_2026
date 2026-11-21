# PROJECT_STATE — 2026-11-21

## V0.1: zakres

Automatyczny kolektor publikacji: HTML/RSS/sitemap, zapis SQLite WAL, deduplikacja URL/tekstu, harmonogram, historia przebiegów, błędy, ponowienia i ponowna kontrola starych artykułów. Interfejs PL: lista, filtry, paginacja, pełny tekst, źródła i historia. Zarządzanie źródłami przez Django admin.

Docker automatycznie wykonuje migracje i `seed_sources`, zachowuje ustawienia istniejących źródeł i uruchamia worker po gotowości web. Restart kontenerów ma politykę `unless-stopped`.

## Weryfikacja

- 27 testów offline przeszło podczas prac nad V0.1.
- Z kontenera potwierdzono pobranie list i tekstu prawdziwych artykułów PWr oraz UR z regułami robots.txt.
- Wyniki końcowego uruchomienia zapisane w `docs/V0_1_VERIFICATION.md`.

## Następny etap V0.2

Adapter lokalnego AI, schemat analizy, potwierdzenia cytatów, ocena i ścieżka rozwoju. Następnie podobne rozwiązania, forma zgłoszenia i kandydaci odbiorców według priorytetów planu.

V0.1 nie nazywa zwykłych zebranych wiadomości potwierdzonymi innowacjami. Ollama nie jest wymagana do uruchomienia kolektora; jej działanie/benchmark nie należą do weryfikacji tej wersji.
