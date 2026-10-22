"""
core/impact_analysis/engine.py -- Impact Analysis Orchestrator

This is the main entry point for Stage 3.
It reads a disruption event from the database and runs the full analysis:

  Step 1: Load the disruption event (e.g. EVT-001)
  Step 2: Find the delayed shipment and affected part (PRT-104)
  Step 3: Trace BOM -- which products use PRT-104?
  Step 4: Find affected production + customer orders
  Step 5: Calculate inventory coverage -- is there actually a shortage?
  Step 6: Print a full human-readable impact report

This engine is DETERMINISTIC -- pure math and DB queries.
No AI, no LLM, no guessing. Same input always gives same output.
The AI agent (Stage 6) will CALL this engine as a tool
and use its output to generate explanations.

How to run:
  uv run python -m core.impact_analysis.engine
  uv run python -m core.impact_analysis.engine --event EVT-001
"""

import sys
import os
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.models import DisruptionEvent, Shipment, PurchaseOrder, DisruptionStatus
from core.impact_analysis.bom_tracer import trace_component_to_products
from core.impact_analysis.order_impact import find_affected_orders
from core.impact_analysis.inventory import calculate_coverage


# ---------------------------------------------------------------------------
# REPORT PRINTER
# Plain text report -- no emojis for Windows compatibility
# ---------------------------------------------------------------------------

def print_report(
    event,
    shipment,
    po,
    bom_result,
    order_result,
    coverage_result
):
    """Print a full human-readable impact analysis report."""

    sep = "=" * 65
    thin = "-" * 65

    print(f"\n{sep}")
    print(f"  DISRUPTION IMPACT ANALYSIS REPORT")
    print(f"{sep}")

    # ---- Event Summary ----
    print(f"\n  EVENT SUMMARY")
    print(thin)
    print(f"  Event ID   : {event.id}")
    print(f"  Type       : {event.event_type.value.replace('_', ' ').upper()}")
    print(f"  Severity   : {event.severity.value.upper()}")
    print(f"  Detected   : {event.detected_at.strftime('%Y-%m-%d %H:%M') if event.detected_at else 'N/A'}")
    print(f"  Description: {event.description[:100]}...")

    # ---- Shipment Details ----
    print(f"\n  DELAYED SHIPMENT")
    print(thin)
    print(f"  Shipment ID      : {shipment.id}")
    print(f"  Purchase Order   : {po.id}")
    print(f"  Supplier         : {po.supplier_id} ({po.supplier.name})")
    print(f"  Part             : {po.part_id} ({po.part.name})")
    print(f"  Quantity Ordered : {po.quantity:.0f} units")
    print(f"  Original ETA     : {shipment.scheduled_date.strftime('%Y-%m-%d')}")
    if shipment.revised_eta:
        print(f"  Revised ETA      : {shipment.revised_eta.strftime('%Y-%m-%d')}  <-- DELAYED")
        print(f"  Delay            : {shipment.delay_days} days")
    print(f"  Reason           : {shipment.delay_reason or 'Not specified'}")

    # ---- Inventory Coverage ----
    print(f"\n  INVENTORY COVERAGE -- {coverage_result.part_name}")
    print(thin)
    for ws in coverage_result.warehouse_stocks:
        avail = ws.on_hand - ws.reserved
        marker = " <-- spare stock available" if ws.warehouse_id != "WH-01" and avail > 0 else ""
        print(f"  {ws.warehouse_id} ({ws.warehouse_name[:25]:<25}): "
              f"{ws.on_hand:.0f} on hand - {ws.reserved:.0f} reserved = {avail:.0f} available{marker}")

    print(f"  {'':->40}")
    print(f"  Total available  : {coverage_result.total_available:.0f} units")
    print(f"  Daily consumption: {coverage_result.daily_consumption:.1f} units/day")
    if coverage_result.coverage_days < 9999:
        print(f"  Coverage         : {coverage_result.coverage_days:.1f} days")
    if coverage_result.shortage_date:
        print(f"  Shortage date    : {coverage_result.shortage_date.strftime('%Y-%m-%d')}")
    print(f"\n  VERDICT: {coverage_result.verdict}")

    # ---- BOM Trace ----
    print(f"\n  AFFECTED PRODUCTS (via Bill of Materials)")
    print(thin)
    if bom_result.affected_products:
        for prod in bom_result.affected_products:
            print(f"  {prod.product_id} | {prod.product_name[:40]:<40} | needs {prod.quantity_per_unit:.0f}x {coverage_result.part_name}")
    else:
        print(f"  No products in BOM use {coverage_result.part_name}")

    # ---- Production Orders ----
    print(f"\n  PRODUCTION ORDER IMPACT")
    print(thin)
    at_risk_count = 0
    safe_count = 0
    for po_risk in order_result.production_orders:
        status_tag = "[AT RISK]" if po_risk.is_at_risk else "[  SAFE ]"
        start_str = po_risk.planned_start.strftime('%Y-%m-%d')
        print(f"  {status_tag} {po_risk.order_id} | {po_risk.product_name[:30]:<30} | "
              f"qty:{po_risk.quantity_to_produce:.0f} | starts:{start_str} | "
              f"needs:{po_risk.component_units_needed:.0f} units")
        if po_risk.is_at_risk:
            print(f"           Reason: {po_risk.risk_reason}")
            at_risk_count += 1
        else:
            safe_count += 1

    print(f"\n  At risk: {at_risk_count}  |  Safe: {safe_count}")

    # ---- Customer Orders ----
    print(f"\n  CUSTOMER ORDER IMPACT")
    print(thin)
    if order_result.customer_orders:
        for co in order_result.customer_orders:
            promise_str = co.promised_delivery_date.strftime('%Y-%m-%d')
            print(f"  [AT RISK] {co.order_id} | {co.customer_name[:30]:<30} | "
                  f"qty:{co.quantity:.0f} | promised:{promise_str} | value:${co.order_value:,.0f}")
    else:
        print("  No customer orders at risk.")

    # ---- Financial Summary ----
    print(f"\n  FINANCIAL EXPOSURE SUMMARY")
    print(thin)
    print(f"  Production orders at risk  : {order_result.total_production_at_risk}")
    print(f"  Customer orders at risk    : {order_result.total_customers_at_risk}")
    print(f"  Total financial exposure   : ${order_result.total_financial_exposure:,.2f}")

    print(f"\n{sep}")
    print(f"  END OF REPORT")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# VALIDATION: check our results match the known correct answers
# ---------------------------------------------------------------------------

def validate_results(order_result, coverage_result):
    """
    Compare engine output against the known correct answers from our test scenario.
    This is how we verify the engine is working correctly.

    Scenario (v2 -- 95 units available, SHP-441 delayed 4 days):
      - Total available: 95 units (WH-01: 15 + WH-02: 80)
      - Daily consumption: ~7.6 units/day across the full production window
      - Coverage: ~12.5 days -- stock lasts until ~Nov 2
      - SHP-441 revised ETA: ~Oct 30 (9-10 days away)
      - has_shortage = False: shipment arrives BEFORE stock runs out (Oct 30 < Nov 2)

      CONSERVATIVE RISK FLAG for PRD-306:
        order_impact.py flags PRD-306 as AT RISK because its planned start (Nov 4)
        is after the shortage date (Nov 2).
        This is correct conservative behavior: the engine does NOT assume the
        inbound shipment will actually arrive on time (it's already delayed once).
        A human reviewer must confirm whether SHP-441 will arrive before Nov 4.
        This is the "human-in-the-loop" principle: the system warns, humans decide.

      KEY LEARNING:
        inventory.py says "no shortage" (stock bridge exists)
        order_impact.py says "PRD-306 AT RISK" (conservative, ignores replenishment)
        Both are correct! They answer DIFFERENT questions:
          inventory.py: "Do we run out of stock before replenishment?" (NO)
          order_impact.py: "Is any production order scheduled after the theoretical shortage date?" (YES)
        The recovery planner reconciles both views and recommends OPT-A (monitor) as top choice.
    """
    print("\n  VALIDATION AGAINST KNOWN SCENARIO")
    print("-" * 65)

    all_passed = True

    def check(label, condition, expected, got):
        nonlocal all_passed
        status = "[PASS]" if condition else "[FAIL]"
        if not condition:
            all_passed = False
        print(f"  {status} {label}")
        if not condition:
            print(f"         Expected: {expected}")
            print(f"         Got     : {got}")

    # Check 1: Inventory coverage >= 12 days (95 units / 7.6 per day)
    check(
        "Coverage >= 12 days (95 units at ~7.6/day)",
        coverage_result.coverage_days >= 12.0,
        ">= 12 days",
        f"{coverage_result.coverage_days:.1f} days"
    )

    # Check 2: Total available stock correctly summed from all warehouses
    check(
        "Total available = 95 units (WH-01:15 + WH-02:80)",
        coverage_result.total_available == 95.0,
        "95.0 units",
        f"{coverage_result.total_available:.0f} units"
    )

    # Check 3: PRD-301 is SAFE (starts 3 days out, stock covers it)
    prod_ids_at_risk = [p.order_id for p in order_result.production_orders if p.is_at_risk]
    check("PRD-301 is SAFE (near-term, stock covers it)", "PRD-301" not in prod_ids_at_risk, "PRD-301 NOT in at-risk list", prod_ids_at_risk)

    # Check 4: PRD-303 is SAFE (does not use PRT-104)
    # PRD-303 builds FGD-204 which has no PRT-104 in its BOM.
    # Correct behaviour: it should NOT appear in order_result at all.
    all_flagged_prod_ids = [p.order_id for p in order_result.production_orders]
    check("PRD-303 not flagged (no PRT-104 dependency)", "PRD-303" not in all_flagged_prod_ids, "PRD-303 absent from results", all_flagged_prod_ids)

    # Check 5: Shortage date is set (theoretical -- stock would run out Nov 2 if no replenishment)
    check(
        "Shortage date calculated (theoretical Nov 2 without replenishment)",
        coverage_result.shortage_date is not None,
        "shortage_date is not None",
        str(coverage_result.shortage_date)
    )

    # Check 6: Two affected products via BOM trace (FGD-201 and FGD-203)
    bom_related_prod_ids = set(p.product_id for p in order_result.production_orders)
    check(
        "BOM trace found products using PRT-104 (FGD-201, FGD-203)",
        "FGD-201" in bom_related_prod_ids and "FGD-203" in bom_related_prod_ids,
        "FGD-201 and FGD-203",
        list(bom_related_prod_ids)
    )

    # Check 7: PRD-306 conservative AT RISK flag
    # order_impact.py conservatively flags PRD-306 because it starts (Nov 4) after
    # the theoretical shortage date (Nov 2). This is intentional -- the system
    # warns about orders that depend on the delayed shipment arriving on time.
    check(
        "PRD-306 conservatively flagged (starts after theoretical shortage date)",
        "PRD-306" in prod_ids_at_risk,
        "PRD-306 in at-risk list (conservative warning)",
        prod_ids_at_risk
    )

    print(f"\n  {'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
    print("-" * 65)
    return all_passed


# ---------------------------------------------------------------------------
# MAIN ENGINE FUNCTION
# ---------------------------------------------------------------------------

def run_impact_analysis(event_id: str = "EVT-001"):
    """
    Run the full impact analysis for a given disruption event.

    This is the function the AI agent will call in Stage 6.
    For now we run it standalone to verify it works.
    """
    db_engine = create_engine(DATABASE_URL)

    with Session(db_engine) as session:

        # ------------------------------------------------------------------
        # STEP 1: Load the disruption event
        # ------------------------------------------------------------------
        event = session.get(DisruptionEvent, event_id)
        if not event:
            print(f"[ERROR] Event {event_id} not found in database.")
            print("  Make sure you ran: uv run python scripts/generate_data.py")
            return

        # ------------------------------------------------------------------
        # STEP 2: Find the delayed shipment and its purchase order
        # The event points to a shipment (source_entity_type = "shipment")
        # ------------------------------------------------------------------
        if event.source_entity_type != "shipment":
            print(f"[ERROR] This engine currently handles 'shipment' events only.")
            print(f"  Event source type: {event.source_entity_type}")
            return

        shipment = session.get(Shipment, event.source_entity_id)
        if not shipment:
            print(f"[ERROR] Shipment {event.source_entity_id} not found.")
            return

        po = session.get(PurchaseOrder, shipment.purchase_order_id)
        if not po:
            print(f"[ERROR] Purchase order {shipment.purchase_order_id} not found.")
            return

        component_part_id = po.part_id

        print(f"\nAnalyzing event {event_id}...")
        print(f"  Delayed part: {component_part_id} ({po.part.name})")
        print(f"  Delay: {shipment.delay_days} days")

        # ------------------------------------------------------------------
        # STEP 3: BOM trace -- which products use this component?
        # ------------------------------------------------------------------
        bom_result = trace_component_to_products(session, component_part_id)
        affected_product_ids = [p.product_id for p in bom_result.affected_products]

        print(f"  Products affected via BOM: {affected_product_ids}")

        # ------------------------------------------------------------------
        # STEP 4: Find affected orders and get daily consumption rate
        # We need to run order_impact FIRST to get daily_consumption,
        # then pass that back to calculate_coverage.
        # ------------------------------------------------------------------
        # First pass: get consumption rate (coverage not calculated yet)
        order_result_first = find_affected_orders(
            session=session,
            component_part_id=component_part_id,
            component_part_name=po.part.name,
            affected_product_ids=affected_product_ids,
            total_available_stock=0,    # placeholder, recalculated below
            shortage_date=None,         # placeholder
        )

        daily_consumption = order_result_first.daily_consumption_rate
        print(f"  Daily consumption rate: {daily_consumption:.1f} units/day")

        # ------------------------------------------------------------------
        # STEP 5: Calculate inventory coverage with real consumption rate
        # ------------------------------------------------------------------
        coverage_result = calculate_coverage(
            session=session,
            part_id=component_part_id,
            daily_consumption=daily_consumption
        )

        # ------------------------------------------------------------------
        # STEP 6: Re-run order impact with real coverage data
        # ------------------------------------------------------------------
        order_result = find_affected_orders(
            session=session,
            component_part_id=component_part_id,
            component_part_name=po.part.name,
            affected_product_ids=affected_product_ids,
            total_available_stock=coverage_result.total_available,
            shortage_date=coverage_result.shortage_date,
        )

        # ------------------------------------------------------------------
        # STEP 7: Print the full report
        # ------------------------------------------------------------------
        print_report(event, shipment, po, bom_result, order_result, coverage_result)

        # ------------------------------------------------------------------
        # STEP 8: Validate against known correct answers
        # ------------------------------------------------------------------
        validate_results(order_result, coverage_result)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SupplyChain Impact Analysis Engine")
    parser.add_argument("--event", type=str, default="EVT-001", help="Event ID to analyze")
    args = parser.parse_args()
    run_impact_analysis(args.event)
