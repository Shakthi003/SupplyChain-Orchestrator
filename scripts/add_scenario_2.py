"""
scripts/add_scenario_2.py -- Adds a SECOND disruption scenario (EVT-002) on top of existing data.

Why a separate script (not generate_data.py --reset)?
  --reset wipes every table and rebuilds EVT-001 with new dates. This script only
  ADDS/UPDATES a few rows, so EVT-001 and the audit log (decision_log) are not
  touched. It is safe to run more than once.

The scenario (a REAL shortage, unlike EVT-001):
  SUP-004 (Shenzhen FastParts) delays PO-108 / SHP-108 -- 200 x PRT-112 (Cooling Fan) -- by 14 days.
  PRT-112 is used by FGD-205 (2x each). Only WH-01 holds it: 240 on hand - 60 reserved = 180 available.
  Two new FGD-205 production orders (130 units) plus the existing PRD-305 (60 units) need ~190 units,
  and the shipment is weeks away.

How to run:
  .\\.venv\\Scripts\\python.exe scripts/add_scenario_2.py
After running, reload the graph if Neo4j is up:
  .\\.venv\\Scripts\\python.exe scripts/load_graph.py
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.models import (
    PurchaseOrder, Shipment, ProductionOrder, CustomerOrder, DisruptionEvent,
    OrderStatus, ProductionStatus,
    DisruptionType, DisruptionSeverity, DisruptionStatus,
)


def main():
    engine = create_engine(DATABASE_URL)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    with Session(engine) as session:
        # --- 1. Make PO-108 / SHP-108 the delayed shipment (14 days late) -------------
        po = session.get(PurchaseOrder, "PO-108")
        shp = session.get(Shipment, "SHP-108")
        if not po or not shp:
            print("[ERROR] PO-108 / SHP-108 not found. Run generate_data.py first.")
            return
        po.status = OrderStatus.DELAYED
        shp.status = OrderStatus.DELAYED
        shp.delay_days = 14
        shp.revised_eta = shp.scheduled_date + timedelta(days=14)
        shp.delay_reason = "Customs hold at port of origin"

        # --- 2. A past order proving SUP-001 can supply PRT-112 (unlocks alt supplier) --
        session.merge(PurchaseOrder(
            id="PO-443", supplier_id="SUP-001", part_id="PRT-112", quantity=100,
            order_date=today - timedelta(days=40),
            expected_arrival=today - timedelta(days=26),
            status=OrderStatus.DELIVERED,
        ))
        session.flush()
        session.merge(Shipment(
            id="SHP-443", purchase_order_id="PO-443",
            scheduled_date=today - timedelta(days=26), revised_eta=None, delay_days=0,
            status=OrderStatus.DELIVERED, delay_reason=None,
        ))

        # --- 3. Extra production demand for FGD-205 (2x PRT-112 each) ------------------
        for prd_id, qty, start, dur in [("PRD-307", 35, 2, 5), ("PRD-308", 30, 6, 5)]:
            session.merge(ProductionOrder(
                id=prd_id, product_part_id="FGD-205", quantity=qty,
                planned_start=today + timedelta(days=start),
                planned_end=today + timedelta(days=start + dur),
                status=ProductionStatus.PLANNED, warehouse_id="WH-01",
            ))
        session.flush()  # production orders must exist before customer orders point at them

        # --- 4. Customer orders waiting on them ---------------------------------------
        for co_id, cust, qty, days, prd, value in [
            ("CO-507", "Vertex Systems Inc",    35, 12, "PRD-307", 15050.00),
            ("CO-508", "Northwind Fluid Power", 30, 16, "PRD-308", 12900.00),
        ]:
            session.merge(CustomerOrder(
                id=co_id, customer_name=cust, part_id="FGD-205", quantity=qty,
                promised_delivery_date=today + timedelta(days=days),
                production_order_id=prd, order_value=value,
                status=OrderStatus.CONFIRMED,
            ))

        # --- 5. The disruption event ---------------------------------------------------
        session.merge(DisruptionEvent(
            id="EVT-002",
            event_type=DisruptionType.LOGISTICS_ISSUE,
            severity=DisruptionSeverity.CRITICAL,
            status=DisruptionStatus.OPEN,
            source_entity_type="shipment",
            source_entity_id="SHP-108",
            description=(
                "Supplier SUP-004 (Shenzhen FastParts Co.) has notified a 14-day delay "
                "on shipment SHP-108 for PO-108 (200 units of PRT-112 Cooling Fan 120mm). "
                "The shipment is held at customs at the port of origin. "
                "This affects all assemblies requiring PRT-112 (FGD-205)."
            ),
            detected_at=datetime.utcnow(),
        ))

        session.commit()
    print("[OK] Scenario 2 added: EVT-002 (SUP-004 / PRT-112 / SHP-108, 14 days late).")
    print("     Reload Neo4j with scripts/load_graph.py if it is running.")


if __name__ == "__main__":
    main()
