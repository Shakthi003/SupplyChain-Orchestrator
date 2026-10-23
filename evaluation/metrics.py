"""
evaluation/metrics.py -- pure scoring functions (no database, no network).

Kept separate from the runner so they can be unit-tested with plain lists.
"""

from datetime import datetime


def precision_recall(predicted, truth) -> dict:
    """Set precision / recall / F1. Empty-vs-empty counts as a perfect match."""
    p, t = set(predicted), set(truth)
    if not p and not t:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "fp": [], "fn": []}
    tp = len(p & t)
    # Convention: predicting nothing makes no false claims (precision 1);
    # having nothing to find means nothing was missed (recall 1).
    prec = tp / len(p) if p else 1.0
    rec = tp / len(t) if t else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": prec, "recall": rec, "f1": f1,
            "fp": sorted(p - t), "fn": sorted(t - p)}


def date_error_days(predicted, truth):
    """Absolute error in days between two 'YYYY-MM-DD' strings. None if either is missing."""
    if not predicted or not truth:
        return None
    a = datetime.fromisoformat(predicted[:10])
    b = datetime.fromisoformat(truth[:10])
    return abs((a - b).days)


def recall_at_k(ranked_doc_ids, expected_docs, k) -> float:
    """Share of expected documents that appear in the first k ranked results."""
    if not expected_docs:
        return 1.0
    top = set(ranked_doc_ids[:k])
    return sum(1 for d in expected_docs if d in top) / len(expected_docs)


def phrase_coverage(text, phrases) -> float:
    """Share of required phrases (the facts the answer needs) present in retrieved text."""
    if not phrases:
        return 1.0
    low = (text or "").lower()
    return sum(1 for p in phrases if p.lower() in low) / len(phrases)


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None
