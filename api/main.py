"""
api/main.py -- FastAPI layer

Thin HTTP wrapper. No business logic lives here: it calls the existing
agent / tool functions and returns their results.

Run:  uv run uvicorn api.main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.schemas import DecisionRequest
from core.config import DATABASE_URL
from core.logging_config import get_logger, request_id_var
from core.models import DisruptionEvent, Inventory, Part, DisruptionStatus
from agents.runner import run_analysis
from agents.decision import submit_decision, DecisionError
from tools.impact_tool import run_impact_analysis_tool
from tools.planning_tool import run_recovery_planning_tool
from tools.audit_tool import get_past_decisions

log = get_logger("api")

# Event / part ids look like EVT-001, PRT-104: letters, digits, dash, underscore only.
RecordId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,20}$", description="Record id, e.g. EVT-001")]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the embedding model once at startup (~30s) so the first user
    # request is not the one that pays for it. Non-fatal if ChromaDB is empty.
    try:
        from retrieval.retriever import _get_collection
        _get_collection()
        log.info("document search warmed up")
    except Exception as e:
        log.warning("could not warm up document search", extra={"error": str(e)})
    yield


app = FastAPI(
    title="SupplyChain Orchestrator API",
    description="Explainable agentic supply-chain risk and recovery (synthetic data).",
    version="0.1.0",
    lifespan=lifespan,
)

_engine = create_engine(DATABASE_URL, pool_pre_ping=True)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Give every request an id (returned in X-Request-ID) and log one line per request."""
    rid = request.headers.get("x-request-id", "")[:32] or uuid.uuid4().hex[:8]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Full detail goes to the log; the client only gets a generic message.
        log.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse({"detail": f"Internal error. Quote request id {rid}."}, status_code=500)
    response.headers["X-Request-ID"] = rid
    log.info("request", extra={
        "method": request.method, "path": request.url.path,
        "status": response.status_code,
        "duration_ms": round((time.perf_counter() - start) * 1000),
    })
    request_id_var.reset(token)
    return response


def _event_dict(e: DisruptionEvent) -> dict:
    return {
        "event_id": e.id,
        "event_type": e.event_type.value,
        "severity": e.severity.value,
        "status": e.status.value,
        "description": e.description,
        "source_entity_type": e.source_entity_type,
        "source_entity_id": e.source_entity_id,
        "detected_at": e.detected_at.isoformat() if e.detected_at else None,
    }


def _get_event_or_404(event_id: str) -> dict:
    with Session(_engine) as session:
        event = session.get(DisruptionEvent, event_id)
        if not event:
            raise HTTPException(404, f"Event {event_id} not found.")
        return _event_dict(event)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/events")
def list_events() -> list[dict]:
    with Session(_engine) as session:
        events = session.query(DisruptionEvent).order_by(DisruptionEvent.detected_at.desc()).all()
        return [_event_dict(e) for e in events]


@app.get("/events/{event_id}")
def get_event(event_id: RecordId) -> dict:
    return _get_event_or_404(event_id)


@app.post("/events/{event_id}/analyze")
def analyze_event(event_id: RecordId) -> dict:
    """
    Run the full pipeline (impact, planning, graph, documents, AI explanation).
    Does NOT record any decision -- a human must call /decision afterwards.
    """
    event = _get_event_or_404(event_id)
    if event["status"] == DisruptionStatus.RESOLVED.value:
        raise HTTPException(409, f"Event {event_id} is already resolved.")

    state = run_analysis(event_id)
    if not state.get("event_valid"):
        log.warning("analysis rejected", extra={"event_id": event_id, "error": state.get("error")})
        raise HTTPException(422, state.get("error") or "Event could not be validated.")
    explanation = state.get("explanation") or ""
    log.info("analysis complete", extra={
        "event_id": event_id,
        "has_shortage": (state.get("impact_result") or {}).get("has_shortage"),
        "recommended": (state.get("planning_result") or {}).get("recommended_option_id"),
        "graph_ok": not (state.get("graph_result") or {}).get("error"),
        "docs_ok": not (state.get("documents_result") or {}).get("error"),
        "llm_fallback": explanation.startswith("[AI explanation unavailable"),
    })
    return {
        "event_id": event_id,
        "event": event,
        "impact": state["impact_result"],
        "planning": state["planning_result"],
        "graph": state["graph_result"],
        "documents": state["documents_result"],
        "explanation": state["explanation"],
        "warnings": [state["error"]] if state.get("error") else [],
    }


@app.post("/events/{event_id}/decision")
def record_decision(event_id: RecordId, body: DecisionRequest) -> dict:
    """
    Record the human approve/reject decision in the audit log.

    The deterministic analysis is recomputed server-side (no LLM call), so the
    client cannot supply fake options or costs -- only its own choice.
    """
    _get_event_or_404(event_id)

    impact = run_impact_analysis_tool(event_id)
    planning = run_recovery_planning_tool(event_id)
    if impact.get("error") or planning.get("error"):
        raise HTTPException(500, impact.get("error") or planning.get("error"))

    analysis = {"event_id": event_id, "impact_result": impact, "planning_result": planning}
    try:
        saved = submit_decision(
            analysis=analysis,
            approved=body.approved,
            reviewer_name=body.reviewer_name,
            rationale=body.rationale,
            chosen_option_id=body.chosen_option_id,
        )
    except DecisionError as e:
        log.warning("decision rejected", extra={"event_id": event_id, "error": str(e)})
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        log.error("decision could not be saved", extra={"event_id": event_id, "error": str(e)})
        raise HTTPException(500, str(e))
    # Audit trail in the log too (ids only: the rationale text lives in the database).
    log.info("decision recorded", extra={
        "event_id": event_id, "decision_id": saved["decision_id"],
        "approved": saved["approved"], "chosen_option_id": saved["chosen_option_id"],
    })
    return saved


@app.get("/decisions")
def list_decisions(
    event_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]{1,20}$"),
    limit: int = 50,
) -> list[dict]:
    """Audit log, newest first."""
    result = get_past_decisions(event_id=event_id, limit=min(max(limit, 1), 200))
    if result and "error" in result[0]:
        raise HTTPException(500, result[0]["error"])
    return result


@app.get("/inventory/{part_id}")
def get_inventory(part_id: RecordId) -> dict:
    with Session(_engine) as session:
        part = session.get(Part, part_id)
        if not part:
            raise HTTPException(404, f"Part {part_id} not found.")
        rows = session.query(Inventory).filter(Inventory.part_id == part_id).all()
        warehouses = [
            {
                "warehouse_id": r.warehouse_id,
                "on_hand": r.quantity_on_hand,
                "reserved": r.quantity_reserved,
                "available": r.quantity_on_hand - r.quantity_reserved,
            }
            for r in rows
        ]
        return {
            "part_id": part.id,
            "part_name": part.name,
            "total_available": sum(w["available"] for w in warehouses),
            "warehouses": warehouses,
        }
