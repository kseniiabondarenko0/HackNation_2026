# PROJECT_STATE (2026-11-21)
**Done (V0.1, offline-tested):** Source/Article, discovery (RSS/sitemap/HTML), SSRF-safe fetch, trafilatura extraction, dedupe (URL + content hash), per-source error isolation, interval scheduling (next_run_at), list/detail/sources pages (PL).
**Not verified:** real sites (cloud sandbox has no direct DNS) — run `collect_sources --once --all` on the Mac and fix selectors/prefixes; Ollama/Qwen3:4b benchmark on Polish text.
**Next 3:** (1) Mac smoke run + 2 real sources; (2) analysis adapter (ollama/rules) + Pydantic schema + quote verification; (3) rubric, paths, TF-IDF similar, submission form (see docs/PLAN_V2.md).
