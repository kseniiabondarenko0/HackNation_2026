"""Sprawdza linki: obchodzi działającą stronę i testuje każdy adres (wewnętrzny i zewnętrzny).

Użycie (serwer musi działać, np. `python manage.py runserver 8001`):
    python scripts/check_links.py http://127.0.0.1:8001 [--no-external] [--out raport.txt]

Wynik: OK / BLOKADA (strona odrzuca skrypty: 403, 429, 999 — otwórz ręcznie) / BŁĄD (404, 410, 5xx, DNS, timeout).
Tylko GET/HEAD, bez logowania, bez wysyłania formularzy; wyjątek: ścieżki /admin/ są pomijane.
"""
import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urldefrag, urljoin

import httpx

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HREF = re.compile(r'<a\b[^>]*?href="([^"]+)"', re.I)
SKIP_PATH = re.compile(r"^/(admin/|static/|a/\d+/(dalej|ocena)/)")
BOT_CODES = {401, 403, 429, 999}


def crawl(base):
    c = httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": UA})
    seen, queue, internal_bad, external = set(), ["/"], [], {}
    while queue and len(seen) < 600:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        try:
            r = c.get(base + path)
        except httpx.HTTPError as e:
            internal_bad.append((path, "-", f"{type(e).__name__}"))
            continue
        if r.status_code >= 400:
            internal_bad.append((path, "-", str(r.status_code)))
            continue
        if "text/html" not in r.headers.get("content-type", ""):
            continue
        for h in HREF.findall(r.text):
            h = h.replace("&amp;", "&")
            if h.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            url, _ = urldefrag(urljoin(base + path, h))
            if url.startswith(base):
                p = url[len(base):] or "/"
                if not SKIP_PATH.match(p):
                    queue.append(p)
            else:
                external.setdefault(url, path)
    return len(seen), internal_bad, external


def check_one(url):
    c = httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": UA, "Accept": "text/html,*/*"}, verify=True)
    last = None
    for method in ("HEAD", "GET"):
        try:
            r = c.request(method, url)
            if r.status_code < 400:
                return url, "OK", str(r.status_code)
            last = r.status_code
            if method == "GET" or r.status_code in (404, 410):
                break
        except httpx.HTTPError as e:
            last = type(e).__name__
    if isinstance(last, int):
        return url, ("BLOKADA" if last in BOT_CODES else "BŁĄD"), str(last)
    return url, "BŁĄD", str(last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--no-external", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    pages, bad, external = crawl(base)
    lines = [f"Strony wewnętrzne odwiedzone: {pages}, błędne: {len(bad)}"]
    lines += [f"  BŁĄD WEWN. {p} -> {code}" for p, _, code in bad]
    lines.append(f"Linki zewnętrzne do sprawdzenia: {0 if a.no_external else len(external)}")
    if not a.no_external:
        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(check_one, external))
        counts = {"OK": 0, "BLOKADA": 0, "BŁĄD": 0}
        for url, status, detail in results:
            counts[status] += 1
        lines.append(f"  OK: {counts['OK']}  BLOKADA (sprawdź ręcznie): {counts['BLOKADA']}  BŁĄD: {counts['BŁĄD']}")
        for url, status, detail in sorted(results, key=lambda r: r[1]):
            if status != "OK":
                lines.append(f"  {status} {detail}  {url}   (znaleziono na: {external[url]})")
    text = "\n".join(lines)
    print(text)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
