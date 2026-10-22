"""
tests/integration/test_api.py

Runs against the real PostgreSQL / ChromaDB data (EVT-001 scenario).
Gemini is replaced by a fake (fast, deterministic, no quota) and the audit-log
write is replaced by a recorder so the real decision_log is never polluted.
Neo4j is NOT mocked: if it is offline the pipeline degrades gracefully.
"""

import pytest
from fastapi.testclient import TestClient

import agents.decision as decision_module
import agents.nodes as nodes_module
from api.main import app


class _FakeResponse:
    text = "FAKE EXPLANATION"


class _FakeModels:
    def generate_content(self, **kwargs):
        return _FakeResponse()


class _FakeGenaiClient:
    def __init__(self, *a, **k):
        self.models = _FakeModels()


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(nodes_module.genai, "Client", _FakeGenaiClient)


@pytest.fixture
def saved(monkeypatch):
    """Capture save_decision() calls instead of writing to the real audit log."""
    calls = []

    def fake_save(**kwargs):
        calls.append(kwargs)
        return {"decision_id": 999, "saved": True, "error": None}

    monkeypatch.setattr(decision_module, "save_decision", fake_save)
    return calls


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_and_get_event(client):
    events = client.get("/events").json()
    assert any(e["event_id"] == "EVT-001" for e in events)
    assert client.get("/events/EVT-001").json()["event_id"] == "EVT-001"


def test_unknown_event_404(client):
    assert client.get("/events/EVT-NOPE").status_code == 404
    assert client.post("/events/EVT-NOPE/analyze").status_code == 404


def test_inventory_matches_known_stock(client):
    body = client.get("/inventory/PRT-104").json()
    assert body["total_available"] == 95
    assert client.get("/inventory/NOPE").status_code == 404


def test_analyze_known_scenario(client):
    r = client.post("/events/EVT-001/analyze")
    assert r.status_code == 200
    body = r.json()

    assert body["explanation"] == "FAKE EXPLANATION"
    assert body["impact"]["part_id"] == "PRT-104"
    assert body["impact"]["total_available"] == 95
    # Late shipment is NOT automatically a shortage (stock covers the delay)
    assert body["impact"]["has_shortage"] is False

    planning = body["planning"]
    assert planning["recommended_option_id"] == "OPT-A"
    assert len(planning["options"]) >= 3
    assert all(o["status"] == "feasible" for o in planning["options"])


def test_analyze_does_not_record_a_decision(client, saved):
    client.post("/events/EVT-001/analyze")
    assert saved == []


def test_decision_approve_default_option(client, saved):
    r = client.post("/events/EVT-001/decision", json={
        "approved": True, "reviewer_name": "Tester", "rationale": "Stock covers it",
    })
    assert r.status_code == 200
    assert r.json()["chosen_option_id"] == "OPT-A"
    assert len(saved) == 1 and saved[0]["approved"] is True
    assert saved[0]["reviewer_name"] == "Tester"


def test_rejection_is_also_logged(client, saved):
    r = client.post("/events/EVT-001/decision", json={
        "approved": False, "reviewer_name": "Tester", "rationale": "Too risky",
        "chosen_option_id": "OPT-B1",
    })
    assert r.status_code == 200
    assert saved[0]["approved"] is False
    assert saved[0]["chosen_option_id"] == "OPT-B1"


@pytest.mark.parametrize("body", [
    {"reviewer_name": "T", "rationale": "r"},                                  # approved missing
    {"approved": True, "reviewer_name": "", "rationale": "r"},                 # empty name
    {"approved": True, "reviewer_name": "T", "rationale": ""},                 # empty rationale
    {"approved": "maybe", "reviewer_name": "T", "rationale": "r"},             # not a bool
])
def test_invalid_decision_bodies_rejected(client, saved, body):
    r = client.post("/events/EVT-001/decision", json=body)
    assert r.status_code == 422
    assert saved == []


def test_whitespace_only_name_rejected(client, saved):
    r = client.post("/events/EVT-001/decision", json={
        "approved": True, "reviewer_name": "   ", "rationale": "r"})
    assert r.status_code == 422
    assert saved == []


def test_unknown_option_rejected(client, saved):
    r = client.post("/events/EVT-001/decision", json={
        "approved": True, "reviewer_name": "T", "rationale": "r",
        "chosen_option_id": "OPT-ZZZ"})
    assert r.status_code == 422
    assert saved == []


def test_decisions_endpoint(client):
    r = client.get("/decisions", params={"event_id": "EVT-001"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)
