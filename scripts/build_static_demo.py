"""Build a static, read-only snapshot of Radar Innowacji (for GitHub Pages / portfolio).

Creates a throw-away SQLite database, loads the source registry and the 21-item demo
set (no AI calls, no network), renders every reachable page with Django's test client
and writes plain HTML with relative links, so the result opens from GitHub Pages
or straight from disk (file://).

Usage (from the repository root, with requirements installed):
    python scripts/build_static_demo.py            # writes ./docs
    python scripts/build_static_demo.py --out site

Interactive features (free-text search, filters, forms, the AI "Sprawdź u nas"
scenario, admin) need the running app; in the snapshot they point to a short
explanation page instead of failing silently.
"""
import argparse
import html
import os
import posixpath
import re
import shutil
import sys
import tempfile
from collections import deque
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Query parameters that produce distinct, finite pages worth snapshotting.
ALLOWED_QUERY = {"/inicjatywy/": {"widok", "uklad", "sektor"}, "/porownaj/": {"id"}}
EXTRA_PAGES = ["/porownaj/?id=1&id=2&id=3"]
SKIP = re.compile(r"^/(admin/|api/|health/|scenariusz/|zglos/|potrzeby/zglos/|zrodla/\d+/|a/\d+/(dalej|sprawdz-u-nas)/)")
LIVE_ONLY = "tylko-w-aplikacji/index.html"
MAX_PAGES = 400

BANNER = (
    '<div class="notice" role="note" style="margin-bottom:24px">'
    "<strong>Static preview · Podgląd statyczny.</strong> "
    "This is a read-only snapshot of the app with its demo data. Browsing works; search, filters, "
    "forms and the AI features need the running app "
    '(<a href="https://github.com/kseniiabondarenko0/HackNation_2026#run-it-locally">run it locally</a>). '
    "<span lang=\"pl\">Wyszukiwanie, formularze i funkcje AI działają w uruchomionej aplikacji.</span></div>"
)

LIVE_ONLY_BODY = """
<div class="card"><h2>Ta funkcja działa w uruchomionej aplikacji</h2>
<p><strong>This feature needs the live app.</strong> You are looking at a static snapshot of Radar Innowacji,
so free-text search, filters, the submission forms and the AI scenario generator (&bdquo;Sprawdź u nas&rdquo;)
are disabled here &mdash; they need the Django server, a database and (for AI) a Gemini or Groq API key.</p>
<p>To try them, run the project locally with Docker or Python &mdash; it takes about two minutes:
<a href="https://github.com/kseniiabondarenko0/HackNation_2026#run-it-locally">instructions in the README</a>.</p>
<p><a class="btn" href="{home}">&larr; Back to the overview</a> <a class="btn" href="{catalog}">Browse all initiatives</a></p></div>
"""


def setup_django(db_path, archive_dir):
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_DEBUG": "1",
        "DEMO_MODE": "1",
        "DB_PATH": str(db_path),
        "ARCHIVE_DIR": str(archive_dir),
        "ALLOWED_HOSTS": "testserver,localhost",
        "GEMINI_API_KEY": "",
        "GROQ_API_KEY": "",
    })
    import django
    django.setup()
    from django.core.management import call_command
    call_command("migrate", verbosity=0, interactive=False)
    call_command("seed_sources", verbosity=0)
    call_command("load_demo", verbosity=0)


def canonical(url):
    """Normalise an internal URL to (path, query) or None if it should not be snapshotted."""
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return None
    path = parts.path or "/"
    if path.startswith("/static/"):
        return path, ""
    if SKIP.match(path):
        return None
    allowed = ALLOWED_QUERY.get(path, set())
    pairs = [(k, v) for k, v in parse_qsl(parts.query) if v]
    if any(k not in allowed for k, _ in pairs):
        return None
    return path, urlencode(sorted(pairs))


def out_file(path, query):
    if path.startswith("/static/"):
        return path.lstrip("/")
    base = path.strip("/")
    if query:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", html.unescape(query).replace("%", "")).strip("-").lower()
        return posixpath.join(base, "v", slug or "x", "index.html")
    return posixpath.join(base, "index.html") if base else "index.html"


def rel(from_file, to_file):
    return posixpath.relpath(to_file, posixpath.dirname(from_file) or ".")


def build(out):
    from django.test import Client

    client = Client()
    pages, queue, seen = {}, deque([("/", "")]), set()
    for extra in EXTRA_PAGES:
        queue.append(canonical(extra))
    attr = re.compile(r'\b(href|src|action)="([^"]*)"')

    while queue and len(pages) < MAX_PAGES:
        key = queue.popleft()
        if key in seen:
            continue
        seen.add(key)
        path, query = key
        if path.startswith("/static/"):
            continue
        resp = client.get(path + ("?" + query if query else ""))
        if resp.status_code != 200 or "text/html" not in resp.get("Content-Type", ""):
            print(f"skip {path}?{query} -> {resp.status_code}")
            continue
        body = resp.content.decode()
        page_url = path + ("?" + query if query else "")
        for _, value in attr.findall(body):
            target = canonical(urljoin(page_url, html.unescape(value)).split("#")[0]) if not value.startswith("#") else None
            if target and target not in seen:
                queue.append(target)
        pages[key] = body

    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rendered = {k: out_file(*k) for k in pages}

    def rewrite(page_file, page_url, body):
        def sub(m):
            name, value = m.group(1), m.group(2)
            raw = html.unescape(value)
            if raw.startswith(("#", "mailto:", "tel:", "data:", "javascript:")) or urlsplit(raw).scheme:
                return m.group(0)
            absolute = urljoin(page_url, raw)
            target, frag = (absolute.split("#", 1) + [""])[:2]
            key = canonical(target)
            if key and key[0].startswith("/static/"):
                dest = out_file(*key)
            elif key in rendered:
                dest = rendered[key]
            else:
                dest = LIVE_ONLY
            new = rel(page_file, dest) + ("#" + frag if frag else "")
            return f'{name}="{html.escape(new, quote=True)}"'

        body = attr.sub(sub, body)
        body = re.sub(r'<form\b([^>]*?)method="post"', r'<form\1method="get"', body)
        body = body.replace("{% csrf_token %}", "")
        body = re.sub(r'<input type="hidden" name="csrfmiddlewaretoken"[^>]*>', "", body)
        body = re.sub(r"<script>setTimeout\(function\(\)\{if\(!document\.hidden\)location\.reload\(\)\},\d+\)</script>", "", body)
        # GET forms without an explicit action would reload the static page: send them to the explanation page.
        body = re.sub(r"<form\b(?![^>]*\baction=)", f'<form action="{rel(page_file, LIVE_ONLY)}"', body)
        return body.replace('<main id="main" tabindex="-1">', '<main id="main" tabindex="-1">' + BANNER, 1)

    for key, body in pages.items():
        f = rendered[key]
        page_url = key[0] + ("?" + key[1] if key[1] else "")
        dest = out / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rewrite(f, page_url, body), encoding="utf-8")

    # Explanation page reuses the real layout (rendered from the "about" page shell).
    shell = pages[("/o-systemie/", "")]
    start = shell.index('<main id="main" tabindex="-1">') + len('<main id="main" tabindex="-1">')
    end = shell.index('<footer class="site">')
    live = shell[:start] + LIVE_ONLY_BODY.format(home="{HOME}", catalog="{CATALOG}") + shell[end:]
    live = re.sub(r"<title>.*?</title>", "<title>Tylko w aplikacji — Radar Innowacji</title>", live, flags=re.S)
    live = re.sub(r'(<h1>).*?(</h1>)', r"\1Funkcja aplikacji\2", live, count=1, flags=re.S)
    live = rewrite(LIVE_ONLY, "/tylko-w-aplikacji/", live)
    live = live.replace("{HOME}", rel(LIVE_ONLY, "index.html")).replace("{CATALOG}", rel(LIVE_ONLY, "inicjatywy/index.html"))
    (out / LIVE_ONLY).parent.mkdir(parents=True, exist_ok=True)
    (out / LIVE_ONLY).write_text(live, encoding="utf-8")

    static_out = out / "static" / "web"
    shutil.copytree(ROOT / "web" / "static" / "web", static_out)
    (out / ".nojekyll").write_text("")
    print(f"wrote {len(pages) + 1} pages to {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs"), help="output directory (default: ./docs)")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        setup_django(Path(tmp) / "demo.sqlite3", Path(tmp) / "archive")
        build(Path(args.out).resolve())


if __name__ == "__main__":
    main()
