"""
tools/planning_tool.py -- Recovery Planning Tool (Wrapper for Stage 5)

Wraps core/optimization/planner.py for use by the AI agent.
Returns ranked recovery options as a clean structured dict.
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
from core.optimization.options import (
    generate_all_options, OptionStatus, OptionType
)
from core.optimization.constraints import check_all_constraints
from core.optimization.costs import calculate_all_costs, cost_of_doing_nothing
from core.optimization.planner import score_options


def run_recovery_planning_tool(event_id: str) -> dict:
    """
    Run the full recovery planning pipeline for a disruption event.
    Returns ranked options as a clean dict the agent can use.

    Returns:
        {
          "event_id": "EVT-001",
          "doing_nothing_cost": 4800.0,
          "options": [
            {
              "option_id": "OPT-A",
              "type": "use_stock",
              "title": "Use Available Stock",
              "rank": 1,
              "score": 99.0,
              "cost": 0.0,
              "status": "feasible",
              "description": "...",
              "feasibility_note": "...",
              "cost_note": "...",
              "recommendation_reason": "..."
            },
            ...
          ],
          "recommended_option_id": "OPT-A",
          "error": None
        }
    """
    try:
        db_engine = create_engine(DATABASE_URL)

        with Session(db_engine) as session:
            today = datetime.now(timezone.utc).replace(tzinfo=None)

            event = session.get(DisruptionEvent, event_id)
            if not event:
                return {"error": f"Event {event_id} not found."}

            shipment = session.get(Shipment, event.source_entity_id)
            po = session.get(PurchaseOrder, shipment.purchase_order_id)
            part_id = po.part_id

            # Get impact data
            bom_result = trace_component_to_products(session, part_id)
            affected_product_ids = [p.product_id for p in bom_result.affected_products]

            order_first = find_affected_orders(
                session=session,
                component_part_id=part_id,
                component_part_name=po.part.name,
                affected_product_ids=affected_product_ids,
                total_available_stock=0,
                shortage_date=None,
            )
            daily_consumption = order_first.daily_consumption_rate

            coverage = calculate_coverage(
                session=session,
                part_id=part_id,
                daily_consumption=daily_consumption
            )

            order_result = find_affected_orders(
                session=session,
                component_part_id=part_id,
                component_part_name=po.part.name,
                affected_product_ids=affected_product_ids,
                total_available_stock=coverage.total_available,
                shortage_date=coverage.shortage_date,
            )

            units_needed = sum(
                p.component_units_needed
                for p in order_result.production_orders
                if p.is_at_risk
            )

            at_risk_orders = [p for p in order_result.production_orders if p.is_at_risk]
            if at_risk_orders:
                earliest = min(at_risk_orders, key=lambda p: p.planned_start)
                days_until_production = max(0, (earliest.planned_start - today).days)
            else:
                days_until_production = 99

            nearest_eta = None
            if coverage.inbound_shipments:
                nearest = min(coverage.inbound_shipments, key=lambda s: s.effective_eta)
                nearest_eta = nearest.effective_eta

            # Generate, check, cost, rank
            options = generate_all_options(
                session=session,
                part_id=part_id,
                primary_warehouse_id="WH-01",
                current_supplier_id=po.supplier_id,
                available_units=coverage.total_available,
                daily_consumption=daily_consumption,
                shortage_date=coverage.shortage_date,
                units_needed=units_needed
            )

            options = check_all_constraints(
                options=options,
                shortage_date=coverage.shortage_date,
                nearest_shipment_eta=nearest_eta,
                units_needed=units_needed,
                days_until_production_start=days_until_production
            )

            options = calculate_all_costs(
                options=options,
                standard_unit_cost=po.part.unit_cost,
                quantity_needed=units_needed
            )

            max_cost = max(
                (o.estimated_cost for o in options if o.status == OptionStatus.FEASIBLE),
                default=1.0
            )
            max_lead = max(
                [o.alt_supplier_lead_time for o in options if o.option_type == OptionType.ALT_SUPPLIER]
                + [shipment.delay_days or 7]
            )
            options = score_options(options, max_cost=max_cost, max_lead_days=max_lead)

            doing_nothing = cost_of_doing_nothing(shipment.delay_days or 4)

            # Build clean output
            options_out = []
            for opt in sorted(options, key=lambda o: (o.rank if o.rank > 0 else 999)):
                options_out.append({
                    "option_id":             opt.option_id,
                    "type":                  opt.option_type.value,
                    "title":                 opt.title,
                    "rank":                  opt.rank,
                    "score":                 opt.score,
                    "cost":                  opt.estimated_cost,
                    "status":                opt.status.value,
                    "description":           opt.description,
                    "feasibility_note":      opt.feasibility_notes[0] if opt.feasibility_notes else "",
                    "cost_note":             opt.cost_breakdown.get("note", ""),
                    "recommendation_reason": opt.recommendation_reason
                })

            recommended = next(
                (o["option_id"] for o in options_out if o["rank"] == 1),
                None
            )

            return {
                "event_id":               event_id,
                "doing_nothing_cost":     doing_nothing,
                "total_options":          len(options),
                "feasible_options":       sum(1 for o in options if o.status == OptionStatus.FEASIBLE),
                "options":                options_out,
                "recommended_option_id":  recommended,
                "error":                  None
            }

    except Exception as e:
        return {"error": str(e), "event_id": event_id}


if __name__ == "__main__":
    import json
    result = run_recovery_planning_tool("EVT-001")
    print(json.dumps(result, indent=2))
