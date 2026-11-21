# DECISIONS
- Django + SQLite (WAL): team stack (Python), zero setup; Postgres after hackathon.
- LLM behind adapter (ollama / openai_compat / rules); demo must run without LLM.
- Similarity via TF-IDF in base (task asks for duplicate-work reduction).
- Manual submission form in base (task: "zgłaszanie lub wykrywanie").

- **Design (2026-11-21):** statyczny `radar.css` zamiast inline `<style>`; blok kompatybilności dla starszych klas (`.notice`, `.metric`, `button` bez klasy), żeby nie przepisywać każdej strony naraz. `/` = Przegląd, katalog pod `/inicjatywy/`. Czcionki z Google Fonts jak w makiecie (offline spada na fonty systemowe).
