"""Demonstration set: REAL publications that the AI already confirmed, exported from a working database (export_demo)
and loaded into a clean installation (load_demo) so the site is not empty before the first collection and AI run.

Nothing is invented: every item is a real publication (title, institution, date, link) with the AI answer that was
stored for it. The stored text is a short excerpt (start of the article + the verified quotes); the full text is under
the source link. Items are marked data["demo"], and the UI says the AI scores are preliminary.
The loader only inserts: it never overwrites or deletes an existing record, and it does nothing on a filled base."""
import copy
import json
import re
from datetime import date, datetime, time as dtime
from pathlib import Path
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone

from collection.extract import content_hash, extract_article
from collection.models import Article, Rejected, Source
from collection.netsafe import safe_get
from collection.window import is_old, to_date
from .core import norm
from .models import Analysis
from .service import _key

DEMO_PATH = Path(__file__).resolve().parent / "data" / "demo_innovations.json"
FORMAT = 1
EXCERPT_CHARS = 700
NOTE = ("Zestaw demonstracyjny: rzeczywiste publikacje instytucji wraz z odpowiedzią AI zapisaną w systemie. "
        "Oceny AI są wstępne (szacunek systemu, nie decyzja człowieka); pełny tekst jest pod linkiem źródłowym.")
SOURCE_FIELDS = ("name", "entry_url", "organization_type", "region", "discovery_type", "allowed_prefix", "feed_url",
                 "sitemap_url", "origin")
REQUIRED_ANALYSIS = ("potential", "completeness", "path", "signal", "sector", "stage", "priority", "region", "data")
PERSONAL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|(?<!\d)(?:\+?48[ -]?)?(?:\d[ -]?){9}(?!\d)")
SECRET = re.compile(r"AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z]{20,}", re.I)


class DemoError(Exception):
    pass


# ------------------------------------------------------------------ file
def read(path=DEMO_PATH):
    """Load and validate the JSON file. Raises DemoError with a readable reason."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DemoError(f"Nie można odczytać zestawu demo ({path}): {exc}") from exc
    if payload.get("format") != FORMAT or not isinstance(payload.get("items"), list) or not payload["items"]:
        raise DemoError("Zestaw demo ma nieznany format albo jest pusty.")
    seen = set()
    for i, item in enumerate(payload["items"], 1):
        where = f"pozycja {i}"
        for key in ("url", "title", "published_at", "excerpt", "source", "analysis"):
            if not item.get(key):
                raise DemoError(f"{where}: brak pola „{key}”.")
        if not item["url"].startswith(("https://", "http://")) or item["url"] in seen:
            raise DemoError(f"{where}: zły albo powtórzony adres URL.")
        seen.add(item["url"])
        try:
            date.fromisoformat(item["published_at"])
        except ValueError:
            raise DemoError(f"{where}: zła data publikacji.") from None
        if any(not item["source"].get(k) for k in ("name", "entry_url")):
            raise DemoError(f"{where}: źródło bez nazwy lub adresu.")
        analysis = item["analysis"]
        if any(k not in analysis for k in REQUIRED_ANALYSIS) or not isinstance(analysis["data"], dict):
            raise DemoError(f"{where}: niepełna analiza.")
        ai_part = analysis["data"].get("ai") or {}
        if not isinstance(ai_part.get("score"), int) or not ai_part.get("explanation"):
            raise DemoError(f"{where}: brak oceny AI lub jej uzasadnienia.")
    return payload


# ------------------------------------------------------------------ export (from a working database)
def _scrub(data):
    """Copy of the stored analysis without personal data (author names) and without the demo marker."""
    d = copy.deepcopy(data)
    d.pop("demo", None)
    d["authors"] = []
    if isinstance(d.get("ai"), dict) and "authors" in d["ai"]:
        d["ai"]["authors"] = []
    return d


def _excerpt(text, quotes):
    """Start of the article plus every verified quote that is not already in it (so each quote stays verifiable)."""
    flat = " ".join(text.split())
    head = flat[:EXCERPT_CHARS]
    if len(flat) > EXCERPT_CHARS:
        head = head.rsplit(" ", 1)[0] + " …"
    parts = [head] + [q for q in quotes if norm(q) not in norm(head)]
    return "\n\n".join(parts)


LISTING = re.compile(r"/(?:page-?\d+|strona-?\d+|aktualnosci|wiadomosci|news|wydarzenia)/?$", re.I)


def _is_listing(url, title):
    """An index page or a page without a real headline is not a publication about one innovation."""
    return bool(LISTING.search(urlparse(url).path)) or len((title or "").strip()) < 20


def _alive(url, getter):
    """The link works and still leads to an article with text."""
    try:
        final_url, html = getter(url)
        page = extract_article(html, final_url)
    except Exception:
        return False
    return bool(page and len(page["text"]) > 200)


def export_items(limit=30, per_source=4, check_links=True, getter=None, min_score=0, report=None):
    """Best AI-confirmed publications of the current database, one dict per item (JSON-ready).

    Only real, current, AI-confirmed items from active sources; dead links are left out."""
    getter = getter or safe_get
    report = report if report is not None else {}
    report.update(candidates=0, dead=0, skipped_demo=0, over_source_cap=0)
    qs = (Article.objects.select_related("source", "analysis")
          .filter(status="fetched", duplicate_of__isnull=True, submission__isnull=True, source__status="active",
                  analysis__backend="ai", analysis__verdict="glowna", published_at__isnull=False)
          .order_by("-analysis__potential", "-published_at", "-pk"))
    items, per = [], {}
    for a in qs:
        report["candidates"] += 1
        data = a.analysis.data or {}
        score = (data.get("ai") or {}).get("score")
        if data.get("demo"):
            report["skipped_demo"] += 1     # a loaded demo item is not a fresh export source
            continue
        if not isinstance(score, int) or score < min_score or is_old(a.published_at) or not data.get("verified", {}).get("quotes"):
            continue
        if _is_listing(a.final_url or a.original_url, a.title):
            report["listing"] = report.get("listing", 0) + 1
            continue
        if per.get(a.source_id, 0) >= per_source:
            report["over_source_cap"] += 1
            continue
        if check_links and not _alive(a.final_url or a.original_url, getter):
            report["dead"] += 1
            continue
        per[a.source_id] = per.get(a.source_id, 0) + 1
        s = a.source
        items.append({
            "url": a.original_url, "final_url": a.final_url or a.original_url, "title": a.title, "published_at": to_date(a.published_at).isoformat(),
            "source": {f: getattr(s, f) for f in SOURCE_FIELDS},
            "excerpt": _excerpt(a.text, data["verified"]["quotes"]),
            "analysis": {"potential": a.analysis.potential, "completeness": a.analysis.completeness,
                         "path": a.analysis.path, "signal": a.analysis.signal, "sector": a.analysis.sector,
                         "stage": a.analysis.stage, "priority": a.analysis.priority, "region": a.analysis.region,
                         "data": _scrub(data)}})
        if len(items) >= limit:
            break
    return items


def build_payload(items):
    return {"format": FORMAT, "generated_at": timezone.now().isoformat(timespec="seconds"), "note": NOTE, "items": items}


def check_clean(payload):
    """Refuse to write a file containing e-mails, phone numbers or API keys. Returns the list of problems."""
    blob = json.dumps(payload, ensure_ascii=False)
    # Diagnostics must not echo the very contact/credential that prevented export.
    return [label for label, rx in (("dane kontaktowe", PERSONAL), ("klucz API", SECRET)) if rx.search(blob)]


# ------------------------------------------------------------------ load
def _aware_day(day):
    return timezone.make_aware(datetime.combine(day, dtime()))


def load(path=DEMO_PATH, force=False, dry=False):
    """Insert the demo items missing from the database. Returns a report dict.

    Never overwrites or deletes anything. A base that already holds records of its own is left alone unless force=True
    (and even then existing URLs are skipped)."""
    payload = read(path)
    items = payload["items"]
    urls = {i["url"] for i in items}
    report = {"items": len(items), "added": 0, "existing": 0, "tombstoned": 0, "too_old": 0, "sources_created": 0,
              "own_records": Article.objects.exclude(original_url__in=urls).count(), "refused": False}
    if report["own_records"] and not force:
        report["refused"] = True
        return report
    now = timezone.now()
    with transaction.atomic():
        for item in items:
            pub = date.fromisoformat(item["published_at"])
            if Article.objects.filter(original_url=item["url"]).exists():
                report["existing"] += 1
            elif Rejected.objects.filter(url=item["url"]).exists():
                report["tombstoned"] += 1       # removed earlier on purpose: never bring it back
            elif is_old(pub):
                report["too_old"] += 1
            else:
                report["added"] += 1
                if not dry:
                    report["sources_created"] += _insert(item, pub, now)
        if dry:
            transaction.set_rollback(True)
    return report


def _insert(item, pub, now):
    s, created = item["source"], 0
    source = Source.objects.filter(entry_url=s["entry_url"]).first()
    if source is None:
        source = Source.objects.create(status="active", enabled=True, **{f: s.get(f, "") for f in SOURCE_FIELDS})
        created = 1
    text = item["excerpt"]
    article = Article.objects.create(
        source=source, original_url=item["url"], final_url=item.get("final_url") or item["url"], title=item["title"], text=text,
        content_hash=content_hash(text), published_at=_aware_day(pub), fetched_at=now, status="fetched")
    a = item["analysis"]
    data = copy.deepcopy(a["data"])
    data["demo"] = {"label": "Zestaw demonstracyjny", "note": NOTE, "loaded_at": now.isoformat(timespec="seconds")}
    Analysis.objects.create(
        article=article, input_key=_key(article, "ai"), backend="ai", data=data, potential=a["potential"],
        completeness=a["completeness"], path=a["path"], signal=a["signal"], sector=a["sector"][:40], stage=a["stage"],
        verdict="glowna", priority=a["priority"], region=a["region"])
    return created


def loaded_count():
    """How many demo items the base holds right now."""
    return Analysis.objects.filter(data__has_key="demo").count()
