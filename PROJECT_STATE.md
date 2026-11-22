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
- **Testy:** 239 offline (`python manage.py test tests --noinput`).

## Znane ograniczenia
- Ocena AI to szacunek, nie werdykt; zbieranie obejmuje tylko skonfigurowane źródła, nie cały internet.
- Groq (domyślnie `openai/gpt-oss-120b`, bo `llama-3.3-70b-versatile` wygasa 2026-08-16) sprawdzony tylko na mockach (brak prawdziwego klucza); błędy konfiguracji (zły klucz, nieistniejący model) wstrzymują dostawcę na 1 h i nie zużywają prób artykułów. Limity free tier: Gemini RPD/TPM, Groq ok. 100 tys. tokenów/dzień.
- `/skutecznosc/` liczy dokładność na 29 oznaczonych przykładach przez `analysis.evaluation.evaluate`, domyślnie z backendem `rules`, czyli mierzy filtr regułowy, a nie model AI.
- Hosting z dyskiem tymczasowym gubi bazę przy restarcie (demo wraca przez `load_demo`). Zbieranie wymaga działającego workera.
- PDF-y, skany i strony wymagające JS/logowania nie są obsługiwane. Ochrona przed SSRF to warstwa podstawowa (bez ochrony DNS rebinding).

## Następne kroki
1. Metryki `/skutecznosc/` dla modelu AI: 20–30 oznaczonych tekstów przez Gemini, precyzja i kompletność.
2. Więcej rzeczywistych pozycji z Podkarpacia (samorządy, szkoły) w zestawie demonstracyjnym.
3. Sprawdzenie Groq na prawdziwym kluczu; pokaz z `load_demo`, bez zależności od limitów.
