"""'Podobne rozwiązania': TF-IDF cosine over the local corpus, with the shared terms that explain it.

Reuses the tokenizer of analysis.search (5-char prefixes as crude Polish stemming). No external services.
"""
import math
import re
from collections import Counter, defaultdict
from analysis.search import tokens
from collection.models import Article

WORD = re.compile(r"\w+")
# Frequent Polish function words (as 5-char prefixes) that say nothing about the topic.
STOP = {w[:5] for w in (
    "się jest oraz które który która którym których został została zostały przez dla nie jak tak też jego jej "
    "ich tym tego tej być będzie będą może można także również tylko już ale aby lub jako kiedy gdzie bardzo "
    "wiele wszystkich swoje swoich między były było był mają roku lat czy pod nad przy przed po bez więcej "
    "jednak ponieważ dzięki który tych tego temu sobie nas nasz naszej wraz około według pierwszy nowe nowych "
    "the and for with").split()}
TITLE_WEIGHT = 2
MIN_SCORE = 0.08
HIGH_SCORE = 0.45


def _terms(article):
    return [t for t in tokens(article.title) * TITLE_WEIGHT + tokens(article.text) if t not in STOP and not t.isdigit()]


def _surface_forms(text):
    """prefix -> most frequent full word in the text (to show 'betonu', not 'beton')."""
    forms = defaultdict(Counter)
    for w in WORD.findall((text or "").lower()):
        if len(w) > 2:
            forms[w[:5]][w] += 1
    return {p: c.most_common(1)[0][0] for p, c in forms.items()}


def _corpus():
    return list(Article.objects.select_related("source", "analysis").filter(
        status="fetched", duplicate_of__isnull=True).exclude(text=""))


def similar(article, limit=5, corpus=None):
    """Return [{'article', 'score', 'percent', 'shared', 'high'}] best-first for one article."""
    docs = corpus if corpus is not None else _corpus()
    if not any(d.pk == article.pk for d in docs):
        docs = docs + [article]
    tfs = {d.pk: Counter(_terms(d)) for d in docs}
    n = len(docs)
    df = Counter(t for tf in tfs.values() for t in tf)
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}

    def vec(tf):
        v = {t: (1 + math.log(c)) * idf[t] for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        return {t: x / norm for t, x in v.items()}

    base = vec(tfs[article.pk])
    if not base:
        return []
    forms = _surface_forms(f"{article.title}\n{article.text}")
    results = []
    for d in docs:
        if d.pk == article.pk or d.pk == article.duplicate_of_id:
            continue
        other = vec(tfs[d.pk])
        parts = {t: base[t] * other[t] for t in base.keys() & other.keys()}
        score = sum(parts.values())
        if score < MIN_SCORE:
            continue
        shared = [forms.get(t, t) for t, _ in sorted(parts.items(), key=lambda x: -x[1])[:6]]
        results.append({"article": d, "score": round(score, 3), "percent": round(100 * score),
                        "shared": shared, "high": score >= HIGH_SCORE})
    results.sort(key=lambda r: -r["score"])
    return results[:limit]
