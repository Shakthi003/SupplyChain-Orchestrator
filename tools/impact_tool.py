"""
tools/impact_tool.py -- Impact Analysis Tool (Wrapper for Stage 3)

Wraps core/impact_analysis/engine.py for use by the AI agent.

Why a wrapper?
  The agent only knows about tools -- simple functions with clean inputs/outputs.
  engine.py has print statements, argparse, validation logic etc.
  This wrapper extracts just the data the agent needs as a clean Python dict.

The agent calls:  run_impact_analysis_tool("EVT-001")
It gets back:     { "part_id": ..., "at_risk_orders": [...], "exposure": ... }
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.models import DisruptionEvent, Shipment, PurchaseOrder
from core.impact_analysis.bom_tracer import trace_component_to_products
from core.impact_analysis.order_impact import find_affected_orders
from core.impact_analysis.inventory import calculate_coverage


def run_impact_analysis_tool(event_id: str) -> dict:
    """
    Run the full impact analysis for a disruption event.
    Returns a structured dict the agent can use directly.

    Args:
        event_id: The disruption event ID (e.g. "EVT-001")

    Returns:
        {
          "event_id":           "EVT-001",
          "part_id":            "PRT-104",
          "part_name":          "Hydraulic Valve C-104",
          "supplier_id":        "SUP-005",
          "supplier_name":      "Apex Hydraulics Ltd",
          "delay_days":         4,
          "original_eta":       "2026-10-26",
          "revised_eta":        "2026-10-30",
          "total_available":    95.0,
          "daily_consumption":  7.6,
          "coverage_days":      12.5,
          "shortage_date":      "2026-11-02",
          "has_shortage":       False,
          "affected_products":  ["FGD-201", "FGD-203"],
          "at_risk_prod_orders": [ { "order_id": "PRD-306", ... } ],
          "at_risk_cust_orders": [ { "order_id": "CO-506", ... } ],
          "total_exposure":     20300.0,
          "error":              None
        }
    """
    try:
        db_engine = create_engine(DATABASE_URL)

        with Session(db_engine) as session:
            today = datetime.now(timezone.utc).replace(tzinfo=None)

            # Load event
            event = session.get(DisruptionEvent, event_id)
            if not event:
                return {"error": f"Event {event_id} not found.", "event_id": event_id}

            # Load shipment and PO
            shipment = session.get(Shipment, event.source_entity_id)
            po = session.get(PurchaseOrder, shipment.purchase_order_id)
            part_id = po.part_id

            # BOM trace
            bom_result = trace_component_to_products(session, part_id)
            affected_product_ids = [p.product_id for p in bom_result.affected_products]

            # First pass: get daily consumption rate
            order_first = find_affected_orders(
                session=session,
                component_part_id=part_id,
                component_part_name=po.part.name,
                affected_product_ids=affected_product_ids,
                total_available_stock=0,
                shortage_date=None,
            )
            daily_consumption = order_first.daily_consumption_rate

            # Coverage calculation
            coverage = calculate_coverage(
                session=session,
                part_id=part_id,
                daily_consumption=daily_consumption
            )

            # Second pass: real risk assessment
            order_result = find_affected_orders(
                session=session,
                component_part_id=part_id,
                component_part_name=po.part.name,
                affected_product_ids=affected_product_ids,
                total_available_stock=coverage.total_available,
                shortage_date=coverage.shortage_date,
            )

            # Build clean output dict
            at_risk_prod = [
                {
                    "order_id": p.order_id,
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "quantity": p.quantity_to_produce,
                    "planned_start": p.planned_start.strftime("%Y-%m-%d"),
                    "units_needed": p.component_units_needed,
                    "risk_reason": p.risk_reason
                }
                for p in order_result.production_orders if p.is_at_risk
            ]

            at_risk_cust = [
                {
                    "order_id": c.order_id,
                    "customer": c.customer_name,
                    "value": c.order_value,
                    "delivery_date": c.promised_delivery_date.strftime("%Y-%m-%d"),
                    "linked_prod_order": c.linked_production_order_id
                }
                for c in order_result.customer_orders if c.is_at_risk
            ]

            return {
                "event_id":            event_id,
                "part_id":             part_id,
                "part_name":           po.part.name,
                "supplier_id":         po.supplier_id,
                "supplier_name":       po.supplier.name,
                "delay_days":          shipment.delay_days or 0,
                "original_eta":        shipment.scheduled_date.strftime("%Y-%m-%d"),
                "revised_eta":         shipment.revised_eta.strftime("%Y-%m-%d") if shipment.revised_eta else None,
                "total_available":     coverage.total_available,
                "daily_consumption":   coverage.daily_consumption,
                "coverage_days":       round(coverage.coverage_days, 1),
                "shortage_date":       coverage.shortage_date.strftime("%Y-%m-%d") if coverage.shortage_date else None,
                "has_shortage":        coverage.has_shortage,
                "verdict":             coverage.verdict,
                "affected_products":   affected_product_ids,
                "at_risk_prod_orders": at_risk_prod,
                "at_risk_cust_orders": at_risk_cust,
                "total_exposure":      order_result.total_financial_exposure,
                "error":               None
            }

    except Exception as e:
        return {"error": str(e), "event_id": event_id}


if __name__ == "__main__":
    import json
    result = run_impact_analysis_tool("EVT-001")
    print(json.dumps(result, indent=2))
