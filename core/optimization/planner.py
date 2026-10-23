"""
core/optimization/planner.py -- Recovery Planner (Orchestrator)

Orchestrates the full recovery planning pipeline:
  1. Generate all possible options      (options.py)
  2. Check which ones are feasible      (constraints.py)
  3. Calculate cost for each feasible   (costs.py)
  4. Rank and pick the best option      (this file)

Ranking logic:
  Only FEASIBLE options are ranked.
  Score = weighted combination of:
    - Cost score       (lower cost = higher score, weight 40%)
    - Speed score      (faster resolution = higher score, weight 40%)
    - Reliability score (higher supplier reliability = higher, weight 20%)

  The option with the highest score is recommended.
  But the human always makes the final decision.

How to run:
  uv run python -m core.optimization.planner
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.clock import as_of_for_event
from core.models import (
    DisruptionEvent, Shipment, PurchaseOrder, Inventory
)
from core.impact_analysis.engine import run_impact_analysis
from core.impact_analysis.inventory import calculate_coverage
from core.impact_analysis.order_impact import find_affected_orders
from core.impact_analysis.bom_tracer import trace_component_to_products
from core.optimization.options import generate_all_options, RecoveryOption, OptionType, OptionStatus
from core.optimization.constraints import check_all_constraints
from core.optimization.costs import calculate_all_costs, cost_of_doing_nothing


# ---------------------------------------------------------------------------
# SCORING + RANKING
# ---------------------------------------------------------------------------

def score_options(
    options: list[RecoveryOption],
    max_cost: float,
    max_lead_days: int,
    as_of_date: datetime
) -> list[RecoveryOption]:
    """
    Score and rank all FEASIBLE options.

    Scoring formula (0-100 scale):
      cost_score        = (1 - option_cost / max_cost) * 100
      speed_score       = based on how quickly option resolves shortage
      reliability_score = for alt supplier options, based on track record

    Final score = (cost_score * 0.40) + (speed_score * 0.40) + (reliability_score * 0.20)
    """
    feasible = [o for o in options if o.status == OptionStatus.FEASIBLE]

    if not feasible:
        return options

    for option in feasible:
        # --- Cost score (40%) ---
        if max_cost > 0:
            cost_score = (1 - option.estimated_cost / max_cost) * 100
        else:
            cost_score = 100.0
        cost_score = max(0.0, min(100.0, cost_score))

        # --- Speed score (40%) ---
        # How quickly does this option resolve the shortage?
        if option.option_type == OptionType.USE_STOCK:
            speed_days = 0       # immediate
        elif option.option_type == OptionType.TRANSFER:
            speed_days = option.transfer_days
        elif option.option_type == OptionType.EXPEDITE:
            speed_days = (option.expedited_eta - as_of_date).days if option.expedited_eta else max_lead_days
        elif option.option_type == OptionType.ALT_SUPPLIER:
            speed_days = option.alt_supplier_lead_time
        else:
            speed_days = max_lead_days

        if max_lead_days > 0:
            speed_score = (1 - speed_days / max_lead_days) * 100
        else:
            speed_score = 100.0
        speed_score = max(0.0, min(100.0, speed_score))

        # --- Reliability score (20%) ---
        if option.option_type == OptionType.ALT_SUPPLIER:
            reliability_score = option.alt_supplier_reliability * 100
        else:
            reliability_score = 95.0  # internal options assumed reliable

        # --- Final weighted score ---
        option.score = round(
            (cost_score * 0.40) +
            (speed_score * 0.40) +
            (reliability_score * 0.20),
            2
        )

    # Rank by score descending
    feasible.sort(key=lambda o: o.score, reverse=True)
    for i, option in enumerate(feasible):
        option.rank = i + 1
        if option.rank == 1:
            option.recommendation_reason = (
                f"Highest overall score ({option.score:.1f}/100). "
                f"Best combination of cost (${option.estimated_cost:,.0f}), "
                f"speed, and reliability."
            )

    return options


def print_recovery_report(
    options: list[RecoveryOption],
    doing_nothing_cost: float,
    event_id: str
):
    """Print the full recovery planning report."""
    sep = "=" * 65
    thin = "-" * 65

    print(f"\n{sep}")
    print(f"  RECOVERY PLANNING REPORT  --  Event {event_id}")
    print(f"{sep}")

    print(f"\n  Cost of doing nothing: ${doing_nothing_cost:,.2f}")
    print(f"  (production delay cost: $1,200/day x delay days)")

    feasible   = [o for o in options if o.status == OptionStatus.FEASIBLE]
    infeasible = [o for o in options if o.status == OptionStatus.INFEASIBLE]

    print(f"\n  Options generated  : {len(options)}")
    print(f"  Feasible           : {len(feasible)}")
    print(f"  Infeasible         : {len(infeasible)}")

    # --- Feasible options ranked ---
    print(f"\n  FEASIBLE OPTIONS (ranked best to worst)")
    print(thin)

    if not feasible:
        print("  No feasible options found. Escalate immediately.")
    else:
        ranked = sorted(feasible, key=lambda o: o.rank)
        for opt in ranked:
            tag = "  --> RECOMMENDED" if opt.rank == 1 else ""
            print(f"\n  Rank #{opt.rank}  [{opt.option_id}]  {opt.title}{tag}")
            print(f"  Score: {opt.score:.1f}/100  |  Cost: ${opt.estimated_cost:,.2f}")
            print(f"  {opt.description}")
            print(f"  Constraint: {opt.feasibility_notes[0] if opt.feasibility_notes else 'N/A'}")
            print(f"  Cost note:  {opt.cost_breakdown.get('note','N/A')}")
            if opt.rank == 1:
                print(f"  Why best:   {opt.recommendation_reason}")

    # --- Infeasible options ---
    if infeasible:
        print(f"\n  INFEASIBLE OPTIONS (excluded)")
        print(thin)
        for opt in infeasible:
            print(f"  [{opt.option_id}] {opt.title}")
            print(f"    Reason: {opt.feasibility_notes[0] if opt.feasibility_notes else 'N/A'}")

    print(f"\n{sep}")
    print(f"  END OF RECOVERY REPORT")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# MAIN PLANNER FUNCTION
# ---------------------------------------------------------------------------

def run_recovery_planning(event_id: str = "EVT-001"):
    """
    Run the full recovery planning pipeline for a disruption event.

    Steps:
      1. Re-run impact analysis to get shortage data
      2. Generate all recovery options
      3. Check constraints
      4. Calculate costs
      5. Rank and recommend
      6. Print report
    """
    db_engine = create_engine(DATABASE_URL)

    with Session(db_engine) as session:
        # --- Load event data ---
        event = session.get(DisruptionEvent, event_id)
        if not event:
            print(f"[ERROR] Event {event_id} not found.")
            return
        today = as_of_for_event(event)

        shipment = session.get(Shipment, event.source_entity_id)
        po = session.get(PurchaseOrder, shipment.purchase_order_id)
        part_id = po.part_id
        current_supplier_id = po.supplier_id

        print(f"\nRunning recovery planning for {event_id}...")
        print(f"  Part: {part_id} ({po.part.name})")
        print(f"  Delayed supplier: {current_supplier_id}")

        # --- Get impact analysis data ---
        bom_result = trace_component_to_products(session, part_id)
        affected_product_ids = [p.product_id for p in bom_result.affected_products]

        order_result_first = find_affected_orders(
            session=session,
            component_part_id=part_id,
            component_part_name=po.part.name,
            affected_product_ids=affected_product_ids,
            total_available_stock=0,
            shortage_date=None,
            as_of_date=today,
        )
        daily_consumption = order_result_first.daily_consumption_rate

        coverage = calculate_coverage(
            session=session,
            part_id=part_id,
            daily_consumption=daily_consumption,
            as_of_date=today,
        )

        order_result = find_affected_orders(
            session=session,
            component_part_id=part_id,
            component_part_name=po.part.name,
            affected_product_ids=affected_product_ids,
            total_available_stock=coverage.total_available,
            shortage_date=coverage.shortage_date,
            as_of_date=today,
        )

        # Total units needed by all at-risk production orders
        units_needed = sum(
            p.component_units_needed
            for p in order_result.production_orders
            if p.is_at_risk
        )

        # Days until the first at-risk production order starts
        at_risk_orders = [p for p in order_result.production_orders if p.is_at_risk]
        if at_risk_orders:
            earliest = min(at_risk_orders, key=lambda p: p.planned_start)
            days_until_production = max(0, (earliest.planned_start - today).days)
        else:
            days_until_production = 99

        # Nearest inbound shipment ETA
        nearest_eta = None
        if coverage.inbound_shipments:
            nearest = min(coverage.inbound_shipments, key=lambda s: s.effective_eta)
            nearest_eta = nearest.effective_eta

        print(f"  Available stock  : {coverage.total_available:.0f} units")
        print(f"  Daily consumption: {daily_consumption:.1f} units/day")
        print(f"  Units needed     : {units_needed:.0f} units")
        print(f"  Days to production start: {days_until_production}")
        print(f"  Shortage date    : {coverage.shortage_date.strftime('%Y-%m-%d') if coverage.shortage_date else 'None'}")

        # --- Step 1: Generate options ---
        options = generate_all_options(
            session=session,
            part_id=part_id,
            primary_warehouse_id="WH-01",
            current_supplier_id=current_supplier_id,
            available_units=coverage.total_available,
            daily_consumption=daily_consumption,
            shortage_date=coverage.shortage_date,
            units_needed=units_needed
        )
        print(f"\n  Generated {len(options)} recovery options.")

        # --- Step 2: Check constraints ---
        options = check_all_constraints(
            options=options,
            shortage_date=coverage.shortage_date,
            nearest_shipment_eta=nearest_eta,
            units_needed=units_needed,
            days_until_production_start=days_until_production,
            as_of_date=today
        )
        feasible_count = sum(1 for o in options if o.status == OptionStatus.FEASIBLE)
        print(f"  Feasible options : {feasible_count}")

        # --- Step 3: Calculate costs ---
        options = calculate_all_costs(
            options=options,
            standard_unit_cost=po.part.unit_cost,
            quantity_needed=units_needed
        )

        # --- Step 4: Rank ---
        max_cost = max((o.estimated_cost for o in options if o.status == OptionStatus.FEASIBLE), default=1.0)
        max_lead = max([o.alt_supplier_lead_time for o in options if o.option_type == OptionType.ALT_SUPPLIER] + [shipment.delay_days or 7])
        options = score_options(options, max_cost=max_cost, max_lead_days=max_lead, as_of_date=today)

        # --- Cost of doing nothing ---
        doing_nothing = cost_of_doing_nothing(shipment.delay_days or 4)

        # --- Step 5: Print report ---
        print_recovery_report(options, doing_nothing, event_id)

        return options


if __name__ == "__main__":
    run_recovery_planning("EVT-001")
