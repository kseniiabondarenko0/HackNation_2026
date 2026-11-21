"""Rank recipient profiles for one analysed article by tag/sector/path/stage overlap, with reasons.

The result is a list of candidates matching a profile. It does not say the recipient is
interested, has agreed to anything, or knows about the innovation.
"""
import re
from analysis.core import PATHS, STAGES
from .models import Recipient

WORD = re.compile(r"\w+")
W_SECTOR, W_PATH, W_STAGE, W_TAG, W_REGION = 3, 2, 1, 1, 1
MAX_TAGS_SCORED = 5


def _words(text):
    return [w for w in WORD.findall((text or "").lower()) if len(w) > 2]


def _tag_hits(tags, words):
    """tag -> first word in the text that starts with it (tags are stems: 'recykl' ~ 'recyklingu')."""
    hits = {}
    for tag in tags:
        stem = tag.replace(" ", "")
        found = next((w for w in words if w.startswith(stem)), None)
        if found:
            hits[tag] = found
    return hits


def match_recipients(article, data, limit=3, recipients=None):
    """Return [{'recipient', 'score', 'reasons', 'tags'}] best-first. data = Analysis.data (may be None)."""
    data = data or {}
    sector = (data.get("sector") or "").lower()
    path_id = (data.get("path") or {}).get("id", "")
    stage = data.get("stage") or ""
    words = _words(f"{article.title}\n{article.text}")
    pool = recipients if recipients is not None else Recipient.objects.filter(active=True)
    results = []
    for r in pool:
        hits = _tag_hits(r.tag_list(), words)
        sector_ok = bool(sector) and sector in r.sector_list()
        if not hits and not sector_ok:
            continue  # path/stage alone is too weak to call someone a candidate
        score, reasons = 0, []
        if sector_ok:
            score += W_SECTOR
            reasons.append(f"Sektor innowacji „{data['sector']}” jest w profilu odbiorcy")
        if hits:
            score += W_TAG * min(len(hits), MAX_TAGS_SCORED)
            reasons.append("Wspólne słowa kluczowe: " + ", ".join(f"{t} (w tekście: „{w}”)" for t, w in hits.items()))
        if path_id and path_id in r.path_list():
            score += W_PATH
            reasons.append(f"Odbiorca szuka rozwiązań na ścieżce „{PATHS[path_id]}”")
        region = (data.get("region") or {}).get("code", "")
        if region and r.region == region:
            score += W_REGION
            reasons.append(f"To samo województwo: {region}")
        if stage in STAGES and stage != "unknown" and stage in r.stage_list():
            score += W_STAGE
            reasons.append(f"Etap „{STAGES[stage]}” odpowiada profilowi odbiorcy")
        results.append({"recipient": r, "score": score, "reasons": reasons, "tags": list(hits)})
    results.sort(key=lambda x: (-x["score"], x["recipient"].name))
    return results[:limit]


def match_articles(recipient, limit=10, articles=None):
    """Reverse direction: innovations for one recipient / submitted need, best-first, with reasons.

    Only publications the filter did not reject (or an expert approved) are considered."""
    from django.db.models import Q
    from collection.models import Article
    if articles is None:
        articles = (Article.objects.select_related("source", "analysis")
                    .filter(status="fetched", duplicate_of__isnull=True, analysis__isnull=False)
                    .filter(Q(analysis__verdict__in=("glowna", "weryfikacja")) | Q(analysis__review_status="zatwierdzony"))
                    .exclude(analysis__review_status="odrzucony")
                    .order_by("-first_seen_at")[:500])
    out = []
    for a in articles:
        found = match_recipients(a, a.analysis.data, limit=1, recipients=[recipient])
        if found:
            out.append({"article": a, "score": found[0]["score"], "reasons": found[0]["reasons"]})
    out.sort(key=lambda x: (-x["score"], -x["article"].pk))
    return out[:limit]
