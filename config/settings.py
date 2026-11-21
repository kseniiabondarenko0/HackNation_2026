import os
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = "test" in sys.argv


def _load_env(path):
    """Tiny .env loader (no dependency). Real environment variables win; values are never logged."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if not TESTING:  # tests must never pick up a real key
    _load_env(BASE_DIR / ".env")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "collection", "analysis", "matching", "web"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DB_PATH", BASE_DIR / "db.sqlite3"),
    "OPTIONS": {"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;"}}}
LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Collector limits (our own settings, tunable after first measurements)
COLLECT = {"MAX_DISCOVERY_PAGES": 10, "MAX_NEW_PER_RUN": 20, "CONNECT_TIMEOUT": 5, "READ_TIMEOUT": 10,
           "MAX_BYTES": 2_000_000, "DELAY_S": float(os.environ.get("COLLECT_DELAY_S", "1.0")), "MIN_TEXT_CHARS": 300,
           "USER_AGENT": "RadarInnowacji-hackathon/0.1",
           "MAX_LINKS_PER_RUN": 200, "MAX_ATTEMPTS": 3,
           "RECHECK_HOURS": 24, "MAX_RUN_SECONDS": 180, "LEASE_SECONDS": 600}
# AI analysis runs only on FREE tiers: Gemini Developer API first, Groq (free plan, no card) as the fallback.
# Keys exist only on the server (env / .env), never in code, templates or the frontend. Billing is never needed:
# on a 429 the provider is paused (cooldown kept in the database, no retry loop) and the next one is tried;
# when none is available the article simply stays in the queue until a quota is restored.
GEMINI = {
    "API_KEY": os.environ.get("GEMINI_API_KEY", ""),
    "MODEL": os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    "BASE_URL": "https://generativelanguage.googleapis.com/v1beta",
    "TIMEOUT_S": 45, "RETRIES": 2, "RETRY_BASE_S": 2.0,        # retries only for network errors / HTTP 5xx
    "MIN_INTERVAL_S": float(os.environ.get("GEMINI_MIN_INTERVAL_S", "6")),   # stays under the free RPM
    "MAX_OUTPUT_TOKENS": 1500,
    "MAX_CALLS_PER_DAY": int(os.environ.get("GEMINI_MAX_CALLS_PER_DAY", "250")),
    "MAX_TOKENS_PER_DAY": int(os.environ.get("GEMINI_MAX_TOKENS_PER_DAY", "1000000")),
}
GROQ = {
    "API_KEY": os.environ.get("GROQ_API_KEY", ""),
    "MODEL": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
    "BASE_URL": "https://api.groq.com/openai/v1",
    "TIMEOUT_S": 45, "RETRIES": 2, "RETRY_BASE_S": 2.0,
    "MIN_INTERVAL_S": float(os.environ.get("GROQ_MIN_INTERVAL_S", "10")),    # free plan: ~12k tokens per minute
    "MAX_OUTPUT_TOKENS": 1000,
    "MAX_CALLS_PER_DAY": int(os.environ.get("GROQ_MAX_CALLS_PER_DAY", "900")),
    "MAX_TOKENS_PER_DAY": int(os.environ.get("GROQ_MAX_TOKENS_PER_DAY", "90000")),  # free plan: 100k tokens/day
}
LLM = {
    "PROVIDERS": [p for p in os.environ.get("LLM_PROVIDERS", "gemini,groq").split(",") if p],   # fallback order
    "MAX_TEXT_CHARS": int(os.environ.get("LLM_MAX_TEXT_CHARS", "6000")),   # cleaned text sent to the model
    "MAX_CALLS_PER_RUN": int(os.environ.get("LLM_MAX_CALLS_PER_RUN", "60")),
}
# Articles older than the window leave the current base; their full record is first appended to this archive.
ARCHIVE_DIR = Path(os.environ.get("ARCHIVE_DIR", BASE_DIR / "archive"))
# Analysis: backend registry lives in analysis/service.py. "ai" is the default when any AI key is configured.
# "rules" (keyword signals, no LLM) is only the offline development mode; it is never a runtime fallback.
ANALYSIS = {"BACKEND": os.environ.get("ANALYSIS_BACKEND") or ("ai" if GEMINI["API_KEY"] or GROQ["API_KEY"] else "rules"),
            "WINDOW_MONTHS": int(os.environ.get("WINDOW_MONTHS", "0")),  # 0 = no age limit (FAQ); N > 0 = only the last N months
            "WEIGHTS": {"problem": 1, "dowody": 2, "wyniki": 2, "przenosnosc": 1, "gotowosc": 1},
            # Voivodeship that gets the +1 priority bonus (ordering only); "" = none. Any of analysis.regions.CODES.
            "PRIORITY_REGION": os.environ.get("PRIORITY_REGION", "podkarpackie")}
# Storage policy (analysis/retention.py, run on every collection cycle): the base keeps only current, AI-confirmed
# innovations plus a short, bounded queue of unconfirmed items. Everything else is deleted; only URL + hash remain
# (Rejected) so the same text is never fetched or paid for again, and those entries expire too.
RETENTION = {
    "QUEUE_TTL_HOURS": int(os.environ.get("QUEUE_TTL_HOURS", "48")),   # unconfirmed items live this long
    "QUEUE_MAX": int(os.environ.get("QUEUE_MAX", "300")),              # fetched items waiting for the AI
    "FOUND_MAX": int(os.environ.get("FOUND_MAX", "300")),              # discovered links not fetched yet
    "DATE_CHECKS": 2, "DATE_CHECKS_PER_CYCLE": 15,                      # primary-source date checks before dropping undated items
    "TOMBSTONE_MAX": int(os.environ.get("TOMBSTONE_MAX", "20000")),    # Rejected rows; older than window+1 month are dropped
    "ARCHIVE_MAX_RECORDS": int(os.environ.get("ARCHIVE_MAX_RECORDS", "2000")),
    "BACKUP_KEEP": 2, "BACKUP_EVERY_HOURS": 24,
    "CURRENCY_DAYS": 14, "CURRENCY_PER_CYCLE": 10, "CURRENCY_FAILS": 3,   # re-check of the source of confirmed items
}
# Automatic source discovery (collection/sourcefinder.py). Search APIs are optional; without them
# the curated seed list and the link graph of monitored sources are used. Candidates are probed and activated automatically.
DISCOVERY = {
    "QUERIES": [q for q in os.environ.get("DISCOVERY_QUERIES", "").split(";") if q.strip()] or [
        "wdrożono innowację uczelnia", "centrum transferu technologii aktualności",
        "projekt pilotażowy wdrożenie", "park naukowo-technologiczny aktualności",
        "komercjalizacja wyników badań spółka spin-off", "instytut badawczy wdrożenie przemysł"],
    "PROVIDERS": [p for p in os.environ.get("DISCOVERY_PROVIDERS", "seeds,links").split(",") if p],
    # Free mechanisms only (curated seeds + links of monitored pages). SearXNG/Brave work only if an admin configures them.
    # Candidates that pass the probe (robots.txt, article links) start monitoring on their own (no mandatory admin step).
    "AUTO_APPROVE": os.environ.get("DISCOVERY_AUTO_APPROVE", "1") == "1",
    "SEARXNG_URL": os.environ.get("SEARXNG_URL", ""),          # e.g. http://localhost:8888 (admin-configured)
    "BRAVE_API_KEY": os.environ.get("BRAVE_API_KEY", ""),
    "ALLOWED_TLDS": (".pl",),
    "MAX_PER_QUERY": 10, "MAX_PROBES": 40, "MAX_CANDIDATES": 15, "MAX_LINK_SOURCES": 10,
    "MIN_SCORE": 2, "SEARCH_DELAY_S": 1.5, "CANDIDATE_INTERVAL_MIN": 240,
    "AUTO_HOURS": int(os.environ.get("DISCOVERY_AUTO_HOURS") or 24),
}
