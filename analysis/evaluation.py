"""Precision/recall of the innovation filter on labeled examples (no database needed)."""
from .core import finalize
from .examples import EXAMPLES
from . import rules


def predict(text, title="", backend=rules.analyze):
    return finalize(backend(text, title), text)


def _metrics(pairs):
    tp = sum(1 for want, got in pairs if want and got)
    fp = sum(1 for want, got in pairs if not want and got)
    fn = sum(1 for want, got in pairs if want and not got)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall}


def evaluate(examples=EXAMPLES, backend=rules.analyze):
    """Positive = interesting. 'lenient': not rejected (main list or review). 'strict': main list only."""
    rows = []
    for ex in examples:
        d = predict(ex["text"], ex.get("title", ""), backend)
        v = d["verdict"]
        rows.append({"id": ex["id"], "title": ex.get("title", ""), "label": ex["label"], "verdict": v["id"],
                     "verdict_label": v["label"], "reason": v["reason"], "potential": d["potential"],
                     "completeness": d["completeness"]})
    lenient = _metrics([(r["label"], r["verdict"] != "odrzucone") for r in rows])
    strict = _metrics([(r["label"], r["verdict"] == "glowna") for r in rows])
    errors = [r for r in rows if r["label"] != (r["verdict"] != "odrzucone")]
    return {"rows": rows, "lenient": lenient, "strict": strict, "errors": errors}
