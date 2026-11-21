"""Local relevance search over stored articles (TF-IDF-like, no external services)."""
import math
import re
from collections import Counter
from collection.models import Article

TOKEN = re.compile(r"\w+")


def tokens(text):
    # 5-char prefixes: crude but effective Polish stemming ("betonu" ~ "beton")
    return [w[:5] for w in TOKEN.findall((text or "").lower()) if len(w) > 2]


def search(query, limit=5):
    """Return [(score, Article)] best-first; title matches count triple."""
    wanted = set(tokens(query))
    if not wanted:
        return []
    qs = Article.objects.select_related("source", "analysis").filter(
        status="fetched", duplicate_of__isnull=True).exclude(text="")
    docs = []
    for a in qs:
        tf = Counter(tokens(a.title) * 3 + tokens(a.text))
        docs.append((a, tf, sum(tf.values()) or 1))
    n = len(docs)
    idf = {t: math.log((n + 1) / (sum(1 for _, tf, _ in docs if t in tf) + 1)) + 1 for t in wanted}
    scored = [(sum(tf[t] / size * idf[t] for t in wanted if t in tf), a) for a, tf, size in docs]
    return sorted(((s, a) for s, a in scored if s > 0), key=lambda x: -x[0])[:limit]
