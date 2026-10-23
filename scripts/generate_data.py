"""
scripts/generate_data.py -- Synthetic Data Generator

Generates realistic but fake supply chain data and loads it into PostgreSQL.

Usage:
  uv run python scripts/generate_data.py                  # fresh generate
  uv run python scripts/generate_data.py --reset          # wipe + regenerate
  uv run python scripts/generate_data.py --seed 42        # same data every time
  uv run python scripts/generate_data.py --scenario delay_4days  # inject test scenario

How it works:
  1. Creates base data: suppliers, parts, warehouses, inventory, BOM
  2. Creates transactional data: purchase orders, shipments, production orders, customer orders
  3. Optionally injects a known disruption scenario for testing

Why synthetic data?
  We don't have a real company's ERP data.
  Synthetic data lets us control exactly what scenarios exist,
  so we can test our impact engine against known correct answers.
"""

import sys
import os
import random
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.models import (
    Base, Supplier, Part, Warehouse, Inventory, BillOfMaterials,
    PurchaseOrder, Shipment, ProductionOrder, CustomerOrder, DisruptionEvent,
    SupplierStatus, OrderStatus, ProductionStatus,
    DisruptionType, DisruptionSeverity, DisruptionStatus
)


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def random_date(start: datetime, end: datetime) -> datetime:
    """Return a random datetime between start and end."""
    delta = end - start
    random_days = random.randint(0, delta.days)
    return start + timedelta(days=random_days)


def wipe_all_tables(session: Session):
    """
    Delete all rows from all tables in the correct order.
    Order matters because of foreign keys:
    child tables must be cleared before parent tables.
    e.g. you can't delete a supplier if purchase_orders still reference it.
    """
    print("Wiping existing data...")
    # Delete in reverse dependency order
    session.query(DisruptionEvent).delete()
    session.query(CustomerOrder).delete()
    session.query(ProductionOrder).delete()
    session.query(Shipment).delete()
    session.query(PurchaseOrder).delete()
    session.query(BillOfMaterials).delete()
    session.query(Inventory).delete()
    session.query(Part).delete()
    session.query(Warehouse).delete()
    session.query(Supplier).delete()
    session.commit()
    print("[OK] All tables cleared.")


# ---------------------------------------------------------------------------
# SECTION 1: SUPPLIERS
# 5 suppliers from different countries with varying reliability scores.
# Reliability score = historical on-time delivery rate (0.0 to 1.0)
# S-07 is deliberately less reliable -- used in our delay scenario later.
# ---------------------------------------------------------------------------

def create_suppliers(session: Session) -> list[Supplier]:
    print("\nCreating suppliers...")

    suppliers_data = [
        {
            "id": "SUP-001",
            "name": "Bosch Industrial GmbH",
            "country": "Germany",
            "city": "Stuttgart",
            "contact_email": "supply@bosch-ind.de",
            "lead_time_days": 14,
            "reliability_score": 0.96,
            "status": SupplierStatus.ACTIVE,
        },
        {
            "id": "SUP-002",
            "name": "Yamaha Precision Parts",
            "country": "Japan",
            "city": "Osaka",
            "contact_email": "orders@yamaha-parts.jp",
            "lead_time_days": 21,
            "reliability_score": 0.98,
            "status": SupplierStatus.ACTIVE,
        },
        {
            "id": "SUP-003",
            "name": "Delta Components LLC",
            "country": "USA",
            "city": "Detroit",
            "contact_email": "procurement@deltacomp.com",
            "lead_time_days": 7,
            "reliability_score": 0.91,
            "status": SupplierStatus.ACTIVE,
        },
        {
            "id": "SUP-004",
            "name": "Shenzhen FastParts Co.",
            "country": "China",
            "city": "Shenzhen",
            "contact_email": "sales@szfastparts.cn",
            "lead_time_days": 30,
            "reliability_score": 0.83,
            "status": SupplierStatus.ACTIVE,
        },
        # SUP-005 is the "problem supplier" used in disruption scenarios.
        # Low reliability score, longer lead times -- realistic backstory.
        {
            "id": "SUP-005",
            "name": "Apex Hydraulics Ltd",
            "country": "India",
            "city": "Pune",
            "contact_email": "contact@apexhydro.in",
            "lead_time_days": 18,
            "reliability_score": 0.74,   # <-- low reliability, will cause delays
            "status": SupplierStatus.ACTIVE,
        },
    ]

    suppliers = []
    for data in suppliers_data:
        s = Supplier(**data)
        session.add(s)
        suppliers.append(s)

    session.commit()
    print(f"[OK] {len(suppliers)} suppliers created.")
    return suppliers


# ---------------------------------------------------------------------------
# SECTION 2: PARTS
# 20 parts split into:
#   - "component"     : raw materials / sub-assemblies bought from suppliers
#   - "finished_good" : products assembled from components, sold to customers
#
# PRT-104 (Hydraulic Valve) is the critical component used in delay scenario.
# ---------------------------------------------------------------------------

def create_parts(session: Session) -> list[Part]:
    print("Creating parts...")

    parts_data = [
        # --- Components (bought from suppliers) ---
        # PRT-104 is deliberately critical -- used in 2 finished goods
        {"id": "PRT-101", "name": "Steel Bearing Set",       "category": "component", "unit_cost": 12.50, "unit_of_measure": "set"},
        {"id": "PRT-102", "name": "Copper Wiring Harness",   "category": "component", "unit_cost": 28.00, "unit_of_measure": "each"},
        {"id": "PRT-103", "name": "Aluminium Housing",       "category": "component", "unit_cost": 45.00, "unit_of_measure": "each"},
        {"id": "PRT-104", "name": "Hydraulic Valve C-104",   "category": "component", "unit_cost": 67.50, "unit_of_measure": "each"},  # KEY PART
        {"id": "PRT-105", "name": "Rubber Seal Kit",         "category": "component", "unit_cost": 8.75,  "unit_of_measure": "kit"},
        {"id": "PRT-106", "name": "Circuit Board Rev-3",     "category": "component", "unit_cost": 112.00,"unit_of_measure": "each"},
        {"id": "PRT-107", "name": "Drive Shaft Assembly",    "category": "component", "unit_cost": 89.00, "unit_of_measure": "each"},
        {"id": "PRT-108", "name": "Thermal Paste 500g",      "category": "component", "unit_cost": 15.00, "unit_of_measure": "tube"},
        {"id": "PRT-109", "name": "Power Supply Unit 24V",   "category": "component", "unit_cost": 55.00, "unit_of_measure": "each"},
        {"id": "PRT-110", "name": "Stainless Bolt Set M12",  "category": "component", "unit_cost": 4.20,  "unit_of_measure": "set"},
        {"id": "PRT-111", "name": "Pressure Sensor PS-7",    "category": "component", "unit_cost": 38.00, "unit_of_measure": "each"},
        {"id": "PRT-112", "name": "Cooling Fan 120mm",       "category": "component", "unit_cost": 22.00, "unit_of_measure": "each"},
        {"id": "PRT-113", "name": "Gasket Set Industrial",   "category": "component", "unit_cost": 11.00, "unit_of_measure": "set"},
        {"id": "PRT-114", "name": "Motor Controller Board",  "category": "component", "unit_cost": 145.00,"unit_of_measure": "each"},
        {"id": "PRT-115", "name": "Stainless Pipe 2-inch",   "category": "component", "unit_cost": 31.00, "unit_of_measure": "meter"},

        # --- Finished Goods (assembled from components above, sold to customers) ---
        # FGD = Finished Good
        {"id": "FGD-201", "name": "Hydraulic Control Unit Alpha",  "category": "finished_good", "unit_cost": 580.00, "unit_of_measure": "each"},
        {"id": "FGD-202", "name": "Hydraulic Control Unit Beta",   "category": "finished_good", "unit_cost": 620.00, "unit_of_measure": "each"},
        {"id": "FGD-203", "name": "Industrial Pump Assembly P-22", "category": "finished_good", "unit_cost": 890.00, "unit_of_measure": "each"},
        {"id": "FGD-204", "name": "Motor Drive System MDS-5",      "category": "finished_good", "unit_cost": 1250.00,"unit_of_measure": "each"},
        {"id": "FGD-205", "name": "Pneumatic Valve Station",       "category": "finished_good", "unit_cost": 430.00, "unit_of_measure": "each"},
    ]

    parts = []
    for data in parts_data:
        p = Part(**data)
        session.add(p)
        parts.append(p)

    session.commit()
    print(f"[OK] {len(parts)} parts created ({len([p for p in parts_data if p['category']=='component'])} components, {len([p for p in parts_data if p['category']=='finished_good'])} finished goods).")
    return parts


# ---------------------------------------------------------------------------
# SECTION 3: WAREHOUSES
# 3 warehouses in different cities.
# WH-01 is the main production warehouse.
# WH-02 and WH-03 are distribution centers.
# Having multiple warehouses enables the "transfer stock" recovery option later.
# ---------------------------------------------------------------------------

def create_warehouses(session: Session) -> list[Warehouse]:
    print("Creating warehouses...")

    warehouses_data = [
        {"id": "WH-01", "name": "Chicago Main Production",    "location": "Chicago, IL",    "country": "USA", "capacity": 50000},
        {"id": "WH-02", "name": "Dallas Distribution Center", "location": "Dallas, TX",     "country": "USA", "capacity": 30000},
        {"id": "WH-03", "name": "Atlanta Regional Hub",       "location": "Atlanta, GA",    "country": "USA", "capacity": 20000},
    ]

    warehouses = []
    for data in warehouses_data:
        w = Warehouse(**data)
        session.add(w)
        warehouses.append(w)

    session.commit()
    print(f"[OK] {len(warehouses)} warehouses created.")
    return warehouses


# ---------------------------------------------------------------------------
# SECTION 4: INVENTORY
# How much of each component is in each warehouse right now.
#
# PRT-104 (Hydraulic Valve) is set LOW deliberately:
#   WH-01: 45 on hand, 30 reserved  --> only 15 truly available
#   WH-02: 20 on hand, 0 reserved   --> 20 available (for transfer recovery option)
# This sets up our shortage scenario perfectly.
# ---------------------------------------------------------------------------

def create_inventory(session: Session) -> list[Inventory]:
    print("Creating inventory...")

    # Format: (inventory_id, part_id, warehouse_id, on_hand, reserved)
    inventory_data = [
        # WH-01 (Main Production) -- primary stock
        ("INV-001", "PRT-101", "WH-01", 500, 120),
        ("INV-002", "PRT-102", "WH-01", 300, 80),
        ("INV-003", "PRT-103", "WH-01", 200, 60),
        # PRT-104: 45 on hand, 30 reserved = 15 available at primary warehouse
        # This is LOW STOCK -- not enough to cover all production orders alone.
        # Intentional: forces the system to look at transfer, expedite, alt supplier.
        ("INV-004", "PRT-104", "WH-01", 45,  30),
        ("INV-005", "PRT-105", "WH-01", 800, 200),
        ("INV-006", "PRT-106", "WH-01", 150, 40),
        ("INV-007", "PRT-107", "WH-01", 120, 35),
        ("INV-008", "PRT-108", "WH-01", 600, 100),
        ("INV-009", "PRT-109", "WH-01", 180, 50),
        ("INV-010", "PRT-110", "WH-01", 1200, 300),
        ("INV-011", "PRT-111", "WH-01", 90,  25),
        ("INV-012", "PRT-112", "WH-01", 240, 60),
        ("INV-013", "PRT-113", "WH-01", 400, 80),
        ("INV-014", "PRT-114", "WH-01", 70,  20),
        ("INV-015", "PRT-115", "WH-01", 350, 90),

        # WH-02 (Dallas) -- backup stock
        # PRT-104: 80 on hand, 0 reserved = 80 units fully available for transfer.
        # This is enough to cover PRD-301 (50 units) and PRD-302 (15 units) combined.
        # Intentional: makes OPT-B (transfer) FEASIBLE as a recovery option.
        ("INV-016", "PRT-101", "WH-02", 200, 30),
        ("INV-017", "PRT-104", "WH-02", 80,  0),
        ("INV-018", "PRT-106", "WH-02", 60,  10),
        ("INV-019", "PRT-109", "WH-02", 80,  20),
        ("INV-020", "PRT-114", "WH-02", 30,  5),

        # WH-03 (Atlanta) -- minimal stock
        ("INV-021", "PRT-101", "WH-03", 100, 10),
        ("INV-022", "PRT-105", "WH-03", 300, 50),
        ("INV-023", "PRT-110", "WH-03", 500, 100),
    ]

    inventory = []
    for inv_id, part_id, wh_id, on_hand, reserved in inventory_data:
        inv = Inventory(
            id=inv_id,
            part_id=part_id,
            warehouse_id=wh_id,
            quantity_on_hand=on_hand,
            quantity_reserved=reserved
        )
        session.add(inv)
        inventory.append(inv)

    session.commit()
    print(f"[OK] {len(inventory)} inventory records created.")
    return inventory


# ---------------------------------------------------------------------------
# SECTION 5: BILL OF MATERIALS (BOM)
# Defines which components are needed to build each finished good.
# PRT-104 is required by BOTH FGD-201 and FGD-203 -- this is intentional.
# When PRT-104 runs short, BOTH finished goods are affected.
# ---------------------------------------------------------------------------

def create_bom(session: Session) -> list[BillOfMaterials]:
    print("Creating bill of materials...")

    # Format: (bom_id, parent_finished_good, child_component, qty_needed)
    bom_data = [
        # FGD-201: Hydraulic Control Unit Alpha
        ("BOM-001", "FGD-201", "PRT-103", 1.0),   # 1x Aluminium Housing
        ("BOM-002", "FGD-201", "PRT-104", 2.0),   # 2x Hydraulic Valve  <-- KEY
        ("BOM-003", "FGD-201", "PRT-105", 1.0),   # 1x Rubber Seal Kit
        ("BOM-004", "FGD-201", "PRT-110", 1.0),   # 1x Bolt Set

        # FGD-202: Hydraulic Control Unit Beta
        ("BOM-005", "FGD-202", "PRT-103", 1.0),
        ("BOM-006", "FGD-202", "PRT-106", 1.0),   # Circuit Board instead
        ("BOM-007", "FGD-202", "PRT-109", 1.0),
        ("BOM-008", "FGD-202", "PRT-110", 1.0),

        # FGD-203: Industrial Pump Assembly P-22
        ("BOM-009", "FGD-203", "PRT-101", 2.0),
        ("BOM-010", "FGD-203", "PRT-104", 1.0),   # 1x Hydraulic Valve  <-- KEY
        ("BOM-011", "FGD-203", "PRT-107", 1.0),
        ("BOM-012", "FGD-203", "PRT-111", 2.0),
        ("BOM-013", "FGD-203", "PRT-113", 1.0),
        ("BOM-014", "FGD-203", "PRT-115", 3.0),

        # FGD-204: Motor Drive System MDS-5
        ("BOM-015", "FGD-204", "PRT-102", 2.0),
        ("BOM-016", "FGD-204", "PRT-106", 1.0),
        ("BOM-017", "FGD-204", "PRT-107", 1.0),
        ("BOM-018", "FGD-204", "PRT-109", 2.0),
        ("BOM-019", "FGD-204", "PRT-114", 1.0),

        # FGD-205: Pneumatic Valve Station
        ("BOM-020", "FGD-205", "PRT-101", 1.0),
        ("BOM-021", "FGD-205", "PRT-105", 2.0),
        ("BOM-022", "FGD-205", "PRT-111", 1.0),
        ("BOM-023", "FGD-205", "PRT-112", 2.0),
        ("BOM-024", "FGD-205", "PRT-113", 2.0),
    ]

    boms = []
    for bom_id, parent, child, qty in bom_data:
        b = BillOfMaterials(
            id=bom_id,
            parent_part_id=parent,
            child_part_id=child,
            quantity_required=qty
        )
        session.add(b)
        boms.append(b)

    session.commit()
    print(f"[OK] {len(boms)} BOM entries created.")
    return boms


# ---------------------------------------------------------------------------
# SECTION 6: PURCHASE ORDERS + SHIPMENTS
# Orders we placed with suppliers to restock components.
# PO-441 is the DELAYED order -- SUP-005 supplying PRT-104, 4 days late.
# All other POs are normal (on time or already delivered).
# ---------------------------------------------------------------------------

def create_purchase_orders_and_shipments(session: Session) -> tuple:
    print("Creating purchase orders and shipments...")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Format: (po_id, supplier_id, part_id, qty, order_date_offset, lead_days, status)
    # order_date_offset = days before today the PO was placed
    po_data = [
        # Normal orders - various states
        ("PO-101", "SUP-001", "PRT-101", 500, -20, 14, OrderStatus.DELIVERED),
        ("PO-102", "SUP-001", "PRT-103", 200, -15, 14, OrderStatus.DELIVERED),
        ("PO-103", "SUP-002", "PRT-102", 300, -25, 21, OrderStatus.DELIVERED),
        ("PO-104", "SUP-002", "PRT-107", 100, -10, 21, OrderStatus.IN_TRANSIT),
        ("PO-105", "SUP-003", "PRT-105", 800, -8,  7,  OrderStatus.IN_TRANSIT),
        ("PO-106", "SUP-003", "PRT-110", 1000,-5,  7,  OrderStatus.CONFIRMED),
        ("PO-107", "SUP-004", "PRT-108", 400, -30, 30, OrderStatus.DELIVERED),
        ("PO-108", "SUP-004", "PRT-112", 200, -15, 30, OrderStatus.IN_TRANSIT),
        ("PO-109", "SUP-001", "PRT-109", 150, -12, 14, OrderStatus.IN_TRANSIT),
        ("PO-110", "SUP-003", "PRT-111", 100, -6,  7,  OrderStatus.CONFIRMED),

        # THE DELAYED ORDER -- SUP-005 supplying PRT-104 (Hydraulic Valve)
        # Placed 12 days ago, 18-day lead time, so originally due in 6 days
        # But SUP-005 notified us of a 4-day delay
        ("PO-441", "SUP-005", "PRT-104", 200, -12, 18, OrderStatus.DELAYED),

        # ALTERNATE SUPPLIER for PRT-104 -- SUP-003 (Delta Components, 7-day lead time)
        # This is a historical order showing SUP-003 has supplied PRT-104 before.
        # It is already DELIVERED (past), so it doesn't affect current stock.
        # Its purpose: proves SUP-003 is a qualified alternate supplier for PRT-104.
        # This unlocks OPT-D in the recovery planner.
        ("PO-442", "SUP-003", "PRT-104", 100, -30, 7, OrderStatus.DELIVERED),
    ]

    purchase_orders = []
    shipments = []

    for po_id, sup_id, part_id, qty, order_offset, lead_days, status in po_data:
        order_date = today + timedelta(days=order_offset)
        expected_arrival = order_date + timedelta(days=lead_days)

        po = PurchaseOrder(
            id=po_id,
            supplier_id=sup_id,
            part_id=part_id,
            quantity=qty,
            order_date=order_date,
            expected_arrival=expected_arrival,
            status=status
        )
        session.add(po)
        purchase_orders.append(po)

        # Create a shipment record for each PO
        # For PO-441: scheduled_date = original ETA, revised_eta = 4 days later
        is_delayed = (po_id == "PO-441")

        shp = Shipment(
            id=f"SHP-{po_id.split('-')[1]}",   # SHP-441, SHP-101, etc.
            purchase_order_id=po_id,
            scheduled_date=expected_arrival,
            revised_eta=expected_arrival + timedelta(days=4) if is_delayed else None,
            delay_days=4 if is_delayed else 0,
            status=status,
            delay_reason="Production line issue at supplier facility" if is_delayed else None
        )
        session.add(shp)
        shipments.append(shp)

    session.commit()
    print(f"[OK] {len(purchase_orders)} purchase orders + {len(shipments)} shipments created.")
    print(f"     (PO-441 for PRT-104 from SUP-005 is DELAYED by 4 days -- this is our test scenario)")
    return purchase_orders, shipments


# ---------------------------------------------------------------------------
# SECTION 7: PRODUCTION ORDERS
# Manufacturing jobs scheduled for the near future.
# PRD-301 and PRD-302 need PRT-104 (via BOM) and will be impacted by the delay.
# PRD-303 does NOT need PRT-104 so it should NOT be flagged (important test).
# ---------------------------------------------------------------------------

def create_production_orders(session: Session) -> list[ProductionOrder]:
    print("Creating production orders...")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Format: (id, product_id, qty, start_offset_days, duration_days, status, warehouse)
    prod_data = [
        # These two use FGD-201 and FGD-203 which BOTH need PRT-104 via BOM
        # They start soon -- will hit the shortage caused by PO-441 delay
        ("PRD-301", "FGD-201", 25, 3,  5, ProductionStatus.PLANNED,      "WH-01"),
        ("PRD-302", "FGD-203", 15, 5,  7, ProductionStatus.PLANNED,      "WH-01"),

        # This one uses FGD-204 which does NOT need PRT-104 -- should NOT be flagged
        ("PRD-303", "FGD-204", 10, 4,  6, ProductionStatus.PLANNED,      "WH-01"),

        # Already in progress -- uses FGD-202 (no PRT-104 dependency)
        ("PRD-304", "FGD-202", 20, -2, 8, ProductionStatus.IN_PROGRESS,  "WH-01"),

        # Future orders
        ("PRD-305", "FGD-205", 30, 10, 5, ProductionStatus.PLANNED,      "WH-02"),
        ("PRD-306", "FGD-201", 40, 15, 5, ProductionStatus.PLANNED,      "WH-01"),
    ]

    production_orders = []
    for prd_id, prod_id, qty, start_offset, duration, status, wh_id in prod_data:
        planned_start = today + timedelta(days=start_offset)
        planned_end = planned_start + timedelta(days=duration)
        prd = ProductionOrder(
            id=prd_id,
            product_part_id=prod_id,
            quantity=qty,
            planned_start=planned_start,
            planned_end=planned_end,
            status=status,
            warehouse_id=wh_id
        )
        session.add(prd)
        production_orders.append(prd)

    session.commit()
    print(f"[OK] {len(production_orders)} production orders created.")
    print(f"     (PRD-301, PRD-302 are COVERED by 95 units available stock)")
    print(f"     (PRD-306 starts after stock would run out, but shipment SHP-441 lands first -> NOT at risk)")
    print(f"     (PRD-303 uses FGD-204 -- no PRT-104 needed -- should NOT be flagged)")
    return production_orders


# ---------------------------------------------------------------------------
# SECTION 8: CUSTOMER ORDERS
# Orders from customers linked to production orders.
# CO-501 and CO-502 are linked to PRD-301 and PRD-302 -- will be at risk.
# ---------------------------------------------------------------------------

def create_customer_orders(session: Session) -> list[CustomerOrder]:
    print("Creating customer orders...")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Format: (id, customer, part_id, qty, promised_days_from_now, prod_order_id, value)
    co_data = [
        # At-risk orders -- linked to PRD-301 and PRD-302 which need PRT-104
        ("CO-501", "Acme Industrial Corp",     "FGD-201", 20, 12, "PRD-301", 11600.00),
        ("CO-502", "GlobalTech Manufacturing", "FGD-203", 12, 15, "PRD-302", 10680.00),

        # Safe orders -- linked to PRD-303 which does NOT need PRT-104
        ("CO-503", "Precision Works Ltd",      "FGD-204", 8,  14, "PRD-303", 10000.00),

        # Orders linked to in-progress / future production
        ("CO-504", "Summit Engineering",       "FGD-202", 15, 10, "PRD-304", 9300.00),
        ("CO-505", "Vertex Systems Inc",       "FGD-205", 25, 20, "PRD-305", 10750.00),
        ("CO-506", "Acme Industrial Corp",     "FGD-201", 35, 25, "PRD-306", 20300.00),
    ]

    customer_orders = []
    for co_id, customer, part_id, qty, promise_days, prod_id, value in co_data:
        co = CustomerOrder(
            id=co_id,
            customer_name=customer,
            part_id=part_id,
            quantity=qty,
            promised_delivery_date=today + timedelta(days=promise_days),
            production_order_id=prod_id,
            order_value=value,
            status=OrderStatus.CONFIRMED
        )
        session.add(co)
        customer_orders.append(co)

    session.commit()
    print(f"[OK] {len(customer_orders)} customer orders created.")
    print(f"     (CO-506 is linked to PRD-306, which the inbound shipment covers -> NOT at risk)")
    print(f"     (CO-501, CO-502 are SAFE -- their production orders are covered by 95 units)")
    return customer_orders


# ---------------------------------------------------------------------------
# SECTION 9: DISRUPTION EVENT
# The trigger event that starts the whole analysis workflow.
# SUP-005 notified us that PO-441 (PRT-104) will arrive 4 days late.
# ---------------------------------------------------------------------------

def create_disruption_event(session: Session) -> DisruptionEvent:
    print("Creating disruption event...")

    event = DisruptionEvent(
        id="EVT-001",
        event_type=DisruptionType.SUPPLIER_DELAY,
        severity=DisruptionSeverity.HIGH,
        status=DisruptionStatus.OPEN,
        source_entity_type="shipment",
        source_entity_id="SHP-441",
        description=(
            "Supplier SUP-005 (Apex Hydraulics Ltd) has notified a 4-day delay "
            "on shipment SHP-441 for PO-441 (200 units of PRT-104 Hydraulic Valve C-104). "
            "Original ETA was revised due to a production line issue at the supplier facility. "
            "This affects all assemblies requiring PRT-104."
        ),
        detected_at=datetime.utcnow()
    )
    session.add(event)
    session.commit()
    print(f"[OK] Disruption event EVT-001 created (SUP-005 delayed PRT-104 by 4 days).")
    return event


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SupplyChain Orchestrator -- Data Generator")
    parser.add_argument("--reset",    action="store_true", help="Wipe all data before generating")
    parser.add_argument("--seed",     type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--scenario", type=str, default="delay_4days", help="Scenario name to inject")
    args = parser.parse_args()

    # Set random seed if provided -- same seed = same data every time
    # Useful for reproducible tests
    if args.seed is not None:
        random.seed(args.seed)
        print(f"Random seed set to: {args.seed}")

    print("=" * 60)
    print("  SupplyChain Orchestrator -- Synthetic Data Generator")
    print("=" * 60)

    engine = create_engine(DATABASE_URL)

    # Use a Session to interact with the database.
    # Session = a "unit of work" -- all changes are buffered until commit().
    # If anything fails, we can rollback() to undo everything safely.
    with Session(engine) as session:
        try:
            if args.reset:
                wipe_all_tables(session)

            # Create data in dependency order:
            # Parents must exist before children (foreign key constraint)
            suppliers  = create_suppliers(session)
            parts      = create_parts(session)
            warehouses = create_warehouses(session)
            inventory  = create_inventory(session)
            boms       = create_bom(session)
            pos, shps  = create_purchase_orders_and_shipments(session)
            prods      = create_production_orders(session)
            cos        = create_customer_orders(session)
            event      = create_disruption_event(session)

            print("\n" + "=" * 60)
            print("  DATA GENERATION COMPLETE")
            print("=" * 60)
            print(f"  Suppliers        : {len(suppliers)}")
            print(f"  Parts            : {len(parts)} (15 components + 5 finished goods)")
            print(f"  Warehouses       : {len(warehouses)}")
            print(f"  Inventory records: {len(inventory)}")
            print(f"  BOM entries      : {len(boms)}")
            print(f"  Purchase orders  : {len(pos)}")
            print(f"  Shipments        : {len(shps)}")
            print(f"  Production orders: {len(prods)}")
            print(f"  Customer orders  : {len(cos)}")
            print(f"  Disruption events: 1")
            print("=" * 60)
            print("\n  TEST SCENARIO INJECTED:")
            print("  - SUP-005 delayed PO-441 (PRT-104) by 4 days")
            print("  - WH-01: 15 available, WH-02: 80 available = 95 total units")
            print("  - PRD-301 (50 units) and PRD-302 (15 units): COVERED by stock")
            print("  - PRD-306 (80 units, 2 weeks out): SAFE -- SHP-441 (200 units) arrives first")
            print("  - Expected result: late shipment, but NO shortage and no order at risk")
            print("  - SUP-003 (Delta Components) is alternate supplier for PRT-104 (OPT-D)")
            print("  - PRD-303, CO-503 should NOT be flagged (no PRT-104 dependency)")
            print("\n  Run the impact engine next:")
            print("  uv run python -m core.impact_analysis.engine")
            print("=" * 60)

        except Exception as e:
            session.rollback()
            print(f"\n[ERROR] Data generation failed: {e}")
            raise


if __name__ == "__main__":
    main()
