"""
tests/unit/test_ui_rendering.py

Regression test: dollar amounts in AI text must reach the page intact.
Streamlit markdown treats a pair of unescaped '$' as LaTeX math, which silently
drops the '$' signs and restyles the text between them.
"""

from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[2] / "app" / "main.py")

EXPLANATION = "Exposure is $20,300.00 in total. The cost of doing nothing is $4,800.00."

EVENT = {
    "event_id": "EVT-T", "event_type": "supplier_delay", "severity": "high",
    "status": "open", "description": "Fee $100 and penalty $200.",
    "source_entity_type": "shipment", "source_entity_id": "S", "detected_at": "2026-01-01T00:00:00",
}
ANALYSIS = {
    "event_id": "EVT-T", "event": EVENT,
    "impact": {
        "part_id": "P", "part_name": "Part", "supplier_id": "S", "supplier_name": "Sup",
        "delay_days": 4, "original_eta": "a", "revised_eta": "b", "total_available": 95.0,
        "daily_consumption": 5.0, "coverage_days": 10.0, "shortage_date": None,
        "has_shortage": False, "verdict": "OK", "affected_products": ["X"],
        "at_risk_prod_orders": [], "at_risk_cust_orders": [], "total_exposure": 20300.0,
    },
    "planning": {
        "doing_nothing_cost": 4800.0, "recommended_option_id": "OPT-A",
        "options": [{
            "option_id": "OPT-A", "title": "Use stock", "rank": 1, "score": 99.0, "cost": 0.0,
            "status": "feasible", "description": "Costs $0 and saves $4,800.",
            "feasibility_note": "ok", "cost_note": "Saves $4,800 vs $1,250", "recommendation_reason": "cheap",
        }],
    },
    "graph": {"error": "offline"}, "documents": {"sources_used": [], "combined_context": ""},
    "explanation": EXPLANATION, "warnings": [],
}


def _fake_request(method, url, **kwargs):
    if url.endswith("/events"):
        body = [EVENT]
    elif url.endswith("/analyze"):
        body = ANALYSIS
    else:
        body = []
    return httpx.Response(200, json=body, request=httpx.Request(method, url))


def test_dollar_amounts_survive_markdown(monkeypatch):
    monkeypatch.setattr(httpx, "request", _fake_request)
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    at.button[0].click().run()

    assert not at.exception
    # Everything rendered through markdown (explanation, options, descriptions)
    page_text = " ".join(m.value for m in at.markdown)
    assert "\\$20,300.00 in total" in page_text      # explanation: escaped
    assert "\\$4,800.00" in page_text
    # No bare '$' may remain: a bare pair is what turns text into LaTeX
    assert "$" not in page_text.replace("\\$", "")
