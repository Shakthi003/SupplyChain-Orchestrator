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

from fastapi import FastAPI, File, Form, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.schemas import DecisionRequest, CreateEventRequest
from core.config import DATABASE_URL
from core.logging_config import get_logger, request_id_var
from core.models import (
    DisruptionEvent, DisruptionStatus, DisruptionType, DisruptionSeverity,
    Inventory, Part, Supplier, Shipment, PurchaseOrder, OrderStatus,
)
from agents.runner import run_analysis
from agents.decision import submit_decision, DecisionError
from tools.impact_tool import run_impact_analysis_tool
from tools.planning_tool import run_recovery_planning_tool
from tools.audit_tool import get_past_decisions
from retrieval.parser import extract_text
from retrieval.validator import validate_document
from retrieval.embedder import embed_and_store, delete_document, list_indexed_documents

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


# ---------------------------------------------------------------------------
# Supplier + Shipment lookup endpoints (used by the New Disruption form)
# ---------------------------------------------------------------------------

@app.get("/suppliers")
def list_suppliers() -> list[dict]:
    """Return all active suppliers with their open shipments."""
    with Session(_engine) as session:
        suppliers = session.query(Supplier).order_by(Supplier.name).all()
        return [
            {
                "id":               s.id,
                "name":             s.name,
                "country":          s.country,
                "reliability_score": s.reliability_score,
                "status":           s.status.value,
            }
            for s in suppliers
        ]


@app.get("/shipments")
def list_shipments(supplier_id: str | None = Query(None)) -> list[dict]:
    """
    Return in-transit shipments, optionally filtered by supplier.
    Only shipments without an existing OPEN event are returned
    (no point creating a duplicate event for the same shipment).
    """
    with Session(_engine) as session:
        q = (
            session.query(Shipment)
            .join(PurchaseOrder, Shipment.purchase_order_id == PurchaseOrder.id)
            .filter(Shipment.status == OrderStatus.IN_TRANSIT)
        )
        if supplier_id:
            q = q.filter(PurchaseOrder.supplier_id == supplier_id)

        shipments = q.order_by(Shipment.scheduled_date).all()

        # Collect shipment IDs that already have an open event
        open_event_ids = {
            e.source_entity_id
            for e in session.query(DisruptionEvent)
            .filter(DisruptionEvent.status == DisruptionStatus.OPEN)
            .filter(DisruptionEvent.source_entity_type == "shipment")
            .all()
        }

        result = []
        for s in shipments:
            po = session.get(PurchaseOrder, s.purchase_order_id)
            result.append({
                "id":              s.id,
                "purchase_order_id": s.purchase_order_id,
                "supplier_id":     po.supplier_id,
                "supplier_name":   po.supplier.name,
                "part_id":         po.part_id,
                "part_name":       po.part.name,
                "quantity":        po.quantity,
                "scheduled_date":  s.scheduled_date.date().isoformat(),
                "delay_days":      s.delay_days or 0,
                "has_open_event":  s.id in open_event_ids,
            })
        return result


@app.post("/events")
def create_event(body: CreateEventRequest) -> dict:
    """
    Create a new disruption event for a delayed shipment.

    - Validates the shipment exists and is IN_TRANSIT
    - Updates Shipment.delay_days and Shipment.revised_eta
    - Creates a DisruptionEvent row and returns it
    - Auto-generates the next EVT-NNN id
    """
    valid_severities = {"low", "medium", "high", "critical"}
    severity_str = (body.severity or "high").lower()
    if severity_str not in valid_severities:
        raise HTTPException(422, f"Invalid severity '{severity_str}'. Must be one of: {', '.join(sorted(valid_severities))}")

    with Session(_engine) as session:
        shipment = session.get(Shipment, body.shipment_id)
        if not shipment:
            raise HTTPException(404, f"Shipment '{body.shipment_id}' not found.")
        if shipment.status != OrderStatus.IN_TRANSIT:
            raise HTTPException(422, f"Shipment '{body.shipment_id}' is not IN_TRANSIT (status: {shipment.status.value}).")

        po = session.get(PurchaseOrder, shipment.purchase_order_id)

        # Check for an existing open event on this shipment
        existing = (
            session.query(DisruptionEvent)
            .filter(DisruptionEvent.source_entity_id == body.shipment_id)
            .filter(DisruptionEvent.status == DisruptionStatus.OPEN)
            .first()
        )
        if existing:
            raise HTTPException(409, f"An open event ({existing.id}) already exists for shipment '{body.shipment_id}'. Resolve it first.")

        # Auto-generate next EVT-NNN id
        from sqlalchemy import func
        count = session.query(func.count(DisruptionEvent.id)).scalar() or 0
        event_id = f"EVT-{count + 1:03d}"
        # Ensure uniqueness in case of gaps
        while session.get(DisruptionEvent, event_id):
            count += 1
            event_id = f"EVT-{count + 1:03d}"

        # Update shipment
        from datetime import timedelta
        shipment.delay_days = body.delay_days
        shipment.revised_eta = shipment.scheduled_date + timedelta(days=body.delay_days)
        shipment.delay_reason = body.delay_reason

        # Map severity string to enum
        severity_map = {
            "low":      DisruptionSeverity.LOW,
            "medium":   DisruptionSeverity.MEDIUM,
            "high":     DisruptionSeverity.HIGH,
            "critical": DisruptionSeverity.CRITICAL,
        }

        description = (
            f"Supplier {po.supplier.name} ({po.supplier_id}) has notified a "
            f"{body.delay_days}-day delay on shipment {body.shipment_id} for "
            f"{po.part.name} ({po.part_id}). Reason: {body.delay_reason}"
        )

        event = DisruptionEvent(
            id=event_id,
            event_type=DisruptionType.SUPPLIER_DELAY,
            severity=severity_map[severity_str],
            status=DisruptionStatus.OPEN,
            source_entity_type="shipment",
            source_entity_id=body.shipment_id,
            description=description,
        )
        session.add(event)
        session.commit()

        log.info("event created", extra={
            "event_id": event_id,
            "shipment_id": body.shipment_id,
            "delay_days": body.delay_days,
            "supplier_id": po.supplier_id,
        })

        return _event_dict(session.get(DisruptionEvent, event_id))


# ---------------------------------------------------------------------------
# Document library endpoints
# ---------------------------------------------------------------------------

@app.get("/documents")
def list_documents() -> list[dict]:
    """List all documents currently indexed in ChromaDB."""
    try:
        return list_indexed_documents()
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    supplier_id: str = Form("none"),
) -> dict:
    """
    Upload a document (PDF, DOCX, or TXT), validate it, and index it in ChromaDB.

    Form fields:
      file:        The file to upload
      title:       Human-readable title (e.g. "Apex Hydraulics Contract 2024")
      category:    contract | policy | past_decision | runbook | other
      supplier_id: Optional supplier ID to associate (e.g. "SUP-006"), or "none"

    Returns:
      { doc_id, title, category, supplier_id, chunks_stored, warnings }
    """
    valid_categories = {"contract", "policy", "past_decision", "runbook", "other"}
    if category not in valid_categories:
        raise HTTPException(422, f"Invalid category '{category}'. Must be one of: {', '.join(sorted(valid_categories))}")

    # Read file bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(422, "Uploaded file is empty.")

    # Layer 1 — extract text
    filename = file.filename or "upload"
    text, parse_error = extract_text(filename, file_bytes)
    if parse_error:
        raise HTTPException(422, parse_error)

    # Layer 2 + 3 — validate content
    validation = validate_document(text=text, category=category, run_gemini=True)
    if not validation.passed:
        raise HTTPException(422, " | ".join(validation.errors))

    # Build a stable doc_id from title (slug-style)
    import re, uuid
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").upper()[:40]
    doc_id = f"USER-{slug}-{uuid.uuid4().hex[:6].upper()}"

    # Embed and store in ChromaDB
    try:
        chunks_stored = embed_and_store(
            doc_id=doc_id,
            title=title,
            category=category,
            content=text,
            supplier_id=supplier_id,
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    log.info("document uploaded", extra={
        "doc_id": doc_id, "category": category,
        "supplier_id": supplier_id, "chunks": chunks_stored,
        "warnings": len(validation.warnings),
    })

    return {
        "doc_id":         doc_id,
        "title":          title,
        "category":       category,
        "supplier_id":    supplier_id,
        "chunks_stored":  chunks_stored,
        "warnings":       validation.warnings,
        "gemini_verdict": validation.gemini_verdict,
    }


@app.delete("/documents/{doc_id}")
def remove_document(doc_id: str) -> dict:
    """Remove a document and all its chunks from ChromaDB."""
    try:
        deleted = delete_document(doc_id)
    except Exception as e:
        raise HTTPException(500, str(e))
    if deleted == 0:
        raise HTTPException(404, f"Document '{doc_id}' not found in the index.")
    log.info("document deleted", extra={"doc_id": doc_id, "chunks_removed": deleted})
    return {"doc_id": doc_id, "chunks_removed": deleted}


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
