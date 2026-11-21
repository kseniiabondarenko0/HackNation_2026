import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "collection", "analysis", "web"]
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
           "MAX_BYTES": 2_000_000, "DELAY_S": 1.0, "MIN_TEXT_CHARS": 300,
           "USER_AGENT": "RadarInnowacji-hackathon/0.1",
           "MAX_LINKS_PER_RUN": 200, "MAX_ATTEMPTS": 3,
           "RECHECK_HOURS": 24, "MAX_RUN_SECONDS": 180, "LEASE_SECONDS": 600}
# Analysis: backend registry lives in analysis/service.py; "rules" works without any LLM.
ANALYSIS = {"BACKEND": os.environ.get("ANALYSIS_BACKEND", "rules"),
            "WEIGHTS": {"problem": 1, "dowody": 2, "wyniki": 2, "przenosnosc": 1, "gotowosc": 1}}
