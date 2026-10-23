"""
Regression gate: the engine must keep agreeing with the hand-derived labels
in evaluation/cases.json. Reads the real DB and ChromaDB; writes nothing.
The LLM is NOT involved (run `python -m evaluation.run_eval --with-llm` for that).
"""

import json
from pathlib import Path

import pytest

from evaluation.run_eval import evaluate_case

SPEC = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "cases.json").read_text(encoding="utf-8"))
TOL = SPEC["stockout_tolerance_days"]


@pytest.fixture(scope="module")
def rows():
    return {c["event_id"]: evaluate_case(c, TOL, with_llm=False) for c in SPEC["cases"]}


@pytest.mark.parametrize("event_id", [c["event_id"] for c in SPEC["cases"]])
def test_core_checks_match_labels(rows, event_id):
    r = rows[event_id]
    assert r["tool_errors"] == 0
    assert r["shortage_correct"]
    assert r["production_orders"]["recall"] == 1.0      # never miss an at-risk order
    assert r["recommended_correct"]
    assert r["infeasible_correct"]
    assert r["retrieval"]["recall_at_3"] == 1.0
    assert r["retrieval"]["evidence_coverage"] == 1.0
    assert r["stockout_date_within_tolerance"] in (True, None)


def test_evt002_is_exact(rows):
    r = rows["EVT-002"]
    assert r["production_orders"]["precision"] == 1.0
    assert r["exposure_correct"]


def test_evt001_has_no_false_positives(rows):
    r = rows["EVT-001"]
    assert r["production_orders"]["precision"] == 1.0
    assert r["exposure_correct"]
