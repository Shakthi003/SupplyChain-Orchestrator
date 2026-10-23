"""Unit tests for the pure scoring functions in evaluation/metrics.py."""

from evaluation.metrics import (date_error_days, mean, phrase_coverage,
                                precision_recall, recall_at_k)


def test_precision_recall_perfect_and_empty():
    assert precision_recall(["A"], ["A"])["f1"] == 1.0
    assert precision_recall([], [])["f1"] == 1.0


def test_precision_recall_false_positive_and_miss():
    fp = precision_recall(["A", "B"], ["A"])
    assert fp["precision"] == 0.5 and fp["recall"] == 1.0 and fp["fp"] == ["B"]
    miss = precision_recall(["A"], ["A", "B"])
    assert miss["precision"] == 1.0 and miss["recall"] == 0.5 and miss["fn"] == ["B"]


def test_predicting_nothing_when_something_expected_is_zero_recall():
    r = precision_recall([], ["A"])
    assert r["recall"] == 0.0 and r["f1"] == 0.0


def test_date_error_days():
    assert date_error_days("2026-11-03", "2026-11-04") == 1
    assert date_error_days(None, "2026-11-04") is None


def test_recall_at_k_and_phrase_coverage():
    assert recall_at_k(["X", "CONTRACT-1"], ["CONTRACT-1"], 1) == 0.0
    assert recall_at_k(["X", "CONTRACT-1"], ["CONTRACT-1"], 2) == 1.0
    assert phrase_coverage("Delay 4-7 days: 5% of PO", ["delay 4-7 days: 5%", "air freight"]) == 0.5


def test_mean_skips_none():
    assert mean([1, None, 3]) == 2
    assert mean([None]) is None
