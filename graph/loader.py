"""
graph/loader.py -- PostgreSQL to Neo4j Data Loader

Reads all data from PostgreSQL and creates the equivalent
nodes and relationships in Neo4j.

What it does:
  For every supplier row in PostgreSQL  → creates a Supplier node in Neo4j
  For every BOM row in PostgreSQL       → creates a REQUIRED_BY relationship
  For every purchase_order row          → creates a SUPPLIES relationship
  ...and so on for all entities

Why copy instead of reading PostgreSQL directly?
  Neo4j is optimized for traversal queries (follow the arrows).
  PostgreSQL is optimized for row lookups and calculations.
  We copy the RELATIONSHIPS (not all data) into Neo4j
  so we can use each tool for what it does best.

How to run:
  uv run python scripts/load_graph.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from neo4j import GraphDatabase

from core.config import DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from core.models import (
    Supplier, Part, Warehouse, Inventory,
    BillOfMaterials, PurchaseOrder, Shipment,
    ProductionOrder, CustomerOrder, DisruptionEvent
)
from graph.schema import NodeLabel, RelType, create_indexes


def clear_graph(neo4j_session):
    """
    Delete ALL nodes and relationships in Neo4j.
    Safe to run before reloading -- gives a clean slate.

    DETACH DELETE means:
      Delete the node AND all its relationships.
      Without DETACH, Neo4j refuses to delete nodes
      that still have relationships attached.
    """
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    print("[OK] Neo4j graph cleared.")


# ---------------------------------------------------------------------------
# NODE CREATORS
# Each function creates one type of node.
# We use MERGE instead of CREATE to avoid duplicates.
# MERGE = "create if not exists, update if exists"
# ---------------------------------------------------------------------------

def load_suppliers(pg_session, neo4j_session):
    """Create one Supplier node per supplier row in PostgreSQL."""
    suppliers = pg_session.query(Supplier).all()

    for s in suppliers:
        neo4j_session.run(f"""
            MERGE (n:{NodeLabel.SUPPLIER} {{id: $id}})
            SET n.name             = $name,
                n.country          = $country,
                n.city             = $city,
                n.lead_time_days   = $lead_time_days,
                n.reliability_score = $reliability_score,
                n.status           = $status
        """, {
            "id": s.id,
            "name": s.name,
            "country": s.country,
            "city": s.city or "",
            "lead_time_days": s.lead_time_days,
            "reliability_score": s.reliability_score,
            "status": s.status.value
        })

    print(f"[OK] {len(suppliers)} Supplier nodes created.")


def load_parts(pg_session, neo4j_session):
    """Create one Part node per part row in PostgreSQL."""
    parts = pg_session.query(Part).all()

    for p in parts:
        neo4j_session.run(f"""
            MERGE (n:{NodeLabel.PART} {{id: $id}})
            SET n.name             = $name,
                n.category         = $category,
                n.unit_cost        = $unit_cost,
                n.unit_of_measure  = $unit_of_measure
        """, {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "unit_cost": p.unit_cost,
            "unit_of_measure": p.unit_of_measure
        })

    print(f"[OK] {len(parts)} Part nodes created.")


def load_warehouses(pg_session, neo4j_session):
    """Create one Warehouse node per warehouse row."""
    warehouses = pg_session.query(Warehouse).all()

    for w in warehouses:
        neo4j_session.run(f"""
            MERGE (n:{NodeLabel.WAREHOUSE} {{id: $id}})
            SET n.name     = $name,
                n.location = $location,
                n.country  = $country
        """, {
            "id": w.id,
            "name": w.name,
            "location": w.location or "",
            "country": w.country
        })

    print(f"[OK] {len(warehouses)} Warehouse nodes created.")


def load_production_orders(pg_session, neo4j_session):
    """Create one ProductionOrder node per production order row."""
    orders = pg_session.query(ProductionOrder).all()

    for o in orders:
        neo4j_session.run(f"""
            MERGE (n:{NodeLabel.PRODUCTION_ORDER} {{id: $id}})
            SET n.quantity      = $quantity,
                n.planned_start = $planned_start,
                n.planned_end   = $planned_end,
                n.status        = $status,
                n.product_id    = $product_id
        """, {
            "id": o.id,
            "quantity": o.quantity,
            "planned_start": o.planned_start.isoformat(),
            "planned_end": o.planned_end.isoformat(),
            "status": o.status.value,
            "product_id": o.product_part_id
        })

    print(f"[OK] {len(orders)} ProductionOrder nodes created.")


def load_customer_orders(pg_session, neo4j_session):
    """Create one CustomerOrder node per customer order row."""
    orders = pg_session.query(CustomerOrder).all()

    for o in orders:
        neo4j_session.run(f"""
            MERGE (n:{NodeLabel.CUSTOMER_ORDER} {{id: $id}})
            SET n.customer_name           = $customer_name,
                n.quantity                = $quantity,
                n.promised_delivery_date  = $promised_date,
                n.order_value             = $order_value,
                n.status                  = $status
        """, {
            "id": o.id,
            "customer_name": o.customer_name,
            "quantity": o.quantity,
            "promised_date": o.promised_delivery_date.isoformat(),
            "order_value": o.order_value or 0.0,
            "status": o.status.value
        })

    print(f"[OK] {len(orders)} CustomerOrder nodes created.")


def load_disruption_events(pg_session, neo4j_session):
    """Create one DisruptionEvent node per event row."""
    events = pg_session.query(DisruptionEvent).all()

    for e in events:
        neo4j_session.run(f"""
            MERGE (n:{NodeLabel.DISRUPTION_EVENT} {{id: $id}})
            SET n.event_type  = $event_type,
                n.severity    = $severity,
                n.status      = $status,
                n.description = $description
        """, {
            "id": e.id,
            "event_type": e.event_type.value,
            "severity": e.severity.value,
            "status": e.status.value,
            "description": e.description[:200]
        })

    print(f"[OK] {len(events)} DisruptionEvent nodes created.")


# ---------------------------------------------------------------------------
# RELATIONSHIP CREATORS
# Each function creates one type of arrow between nodes.
# This is the CORE of the graph -- the connections are what make Neo4j useful.
# ---------------------------------------------------------------------------

def load_supplies_relationships(pg_session, neo4j_session):
    """
    (Supplier) -[SUPPLIES]-> (Part)

    Source: purchase_orders table
    Logic: if a supplier has a purchase order for a part,
           that supplier SUPPLIES that part.

    We also store the lead_time and reliability on the relationship
    so queries can filter by these values.
    """
    pos = pg_session.query(PurchaseOrder).all()
    created = 0

    for po in pos:
        neo4j_session.run(f"""
            MATCH (s:{NodeLabel.SUPPLIER} {{id: $supplier_id}})
            MATCH (p:{NodeLabel.PART}     {{id: $part_id}})
            MERGE (s)-[r:{RelType.SUPPLIES}]->(p)
            SET r.lead_time_days    = $lead_time_days,
                r.reliability_score = $reliability_score,
                r.po_id             = $po_id
        """, {
            "supplier_id": po.supplier_id,
            "part_id": po.part_id,
            "lead_time_days": po.supplier.lead_time_days,
            "reliability_score": po.supplier.reliability_score,
            "po_id": po.id
        })
        created += 1

    print(f"[OK] {created} SUPPLIES relationships created.")


def load_required_by_relationships(pg_session, neo4j_session):
    """
    (Component Part) -[REQUIRED_BY]-> (Finished Good Part)

    Source: bill_of_materials table
    Logic: if BOM says FGD-201 needs PRT-104,
           then PRT-104 -[REQUIRED_BY]-> FGD-201

    This is the KEY relationship for impact tracing.
    When PRT-104 is delayed, we follow REQUIRED_BY to find FGD-201, FGD-203.

    Note the direction: component points TO the finished good.
    Reading it: "PRT-104 is REQUIRED BY FGD-201"
    """
    boms = pg_session.query(BillOfMaterials).all()

    for bom in boms:
        neo4j_session.run(f"""
            MATCH (child:{NodeLabel.PART}  {{id: $child_id}})
            MATCH (parent:{NodeLabel.PART} {{id: $parent_id}})
            MERGE (child)-[r:{RelType.REQUIRED_BY}]->(parent)
            SET r.quantity_required = $qty,
                r.bom_id            = $bom_id
        """, {
            "child_id": bom.child_part_id,
            "parent_id": bom.parent_part_id,
            "qty": bom.quantity_required,
            "bom_id": bom.id
        })

    print(f"[OK] {len(boms)} REQUIRED_BY relationships created.")


def load_builds_relationships(pg_session, neo4j_session):
    """
    (ProductionOrder) -[BUILDS]-> (Part/FinishedGood)

    Source: production_orders table
    Logic: PRD-301 builds FGD-201
    """
    orders = pg_session.query(ProductionOrder).all()

    for o in orders:
        neo4j_session.run(f"""
            MATCH (prd:{NodeLabel.PRODUCTION_ORDER} {{id: $prd_id}})
            MATCH (p:{NodeLabel.PART}               {{id: $part_id}})
            MERGE (prd)-[r:{RelType.BUILDS}]->(p)
            SET r.quantity = $quantity
        """, {
            "prd_id": o.id,
            "part_id": o.product_part_id,
            "quantity": o.quantity
        })

    print(f"[OK] {len(orders)} BUILDS relationships created.")


def load_waiting_on_relationships(pg_session, neo4j_session):
    """
    (CustomerOrder) -[WAITING_ON]-> (ProductionOrder)

    Source: customer_orders table
    Logic: CO-501 is waiting on PRD-301 to finish
           so Acme gets their FGD-201 units
    """
    orders = pg_session.query(CustomerOrder).filter(
        CustomerOrder.production_order_id.isnot(None)
    ).all()

    for o in orders:
        neo4j_session.run(f"""
            MATCH (co:{NodeLabel.CUSTOMER_ORDER}    {{id: $co_id}})
            MATCH (prd:{NodeLabel.PRODUCTION_ORDER} {{id: $prd_id}})
            MERGE (co)-[r:{RelType.WAITING_ON}]->(prd)
            SET r.order_value = $order_value
        """, {
            "co_id": o.id,
            "prd_id": o.production_order_id,
            "order_value": o.order_value or 0.0
        })

    print(f"[OK] {len(orders)} WAITING_ON relationships created.")


def load_stocked_in_relationships(pg_session, neo4j_session):
    """
    (Part) -[STOCKED_IN]-> (Warehouse)

    Source: inventory table
    Logic: PRT-104 is stocked in WH-01 (45 units) and WH-02 (20 units)

    Storing stock levels on the relationship lets us answer:
    "Is there spare stock in another warehouse for transfer?"
    """
    inventory_records = pg_session.query(Inventory).all()

    for inv in inventory_records:
        available = max(0.0, inv.quantity_on_hand - inv.quantity_reserved)
        neo4j_session.run(f"""
            MATCH (p:{NodeLabel.PART}      {{id: $part_id}})
            MATCH (w:{NodeLabel.WAREHOUSE} {{id: $wh_id}})
            MERGE (p)-[r:{RelType.STOCKED_IN}]->(w)
            SET r.on_hand    = $on_hand,
                r.reserved   = $reserved,
                r.available  = $available
        """, {
            "part_id": inv.part_id,
            "wh_id": inv.warehouse_id,
            "on_hand": inv.quantity_on_hand,
            "reserved": inv.quantity_reserved,
            "available": available
        })

    print(f"[OK] {len(inventory_records)} STOCKED_IN relationships created.")


def load_affects_relationships(pg_session, neo4j_session):
    """
    (DisruptionEvent) -[AFFECTS]-> (Part)

    Source: disruption_events table
    Logic: EVT-001 affects PRT-104 (via the shipment → PO → part chain)
    """
    events = pg_session.query(DisruptionEvent).all()
    created = 0

    for event in events:
        if event.source_entity_type == "shipment":
            # Follow: event → shipment → purchase_order → part
            shipment = pg_session.query(
                __import__('core.models', fromlist=['Shipment']).Shipment
            ).get(event.source_entity_id)

            if shipment:
                po = pg_session.query(PurchaseOrder).get(
                    shipment.purchase_order_id
                )
                if po:
                    neo4j_session.run(f"""
                        MATCH (e:{NodeLabel.DISRUPTION_EVENT} {{id: $event_id}})
                        MATCH (p:{NodeLabel.PART}             {{id: $part_id}})
                        MERGE (e)-[r:{RelType.AFFECTS}]->(p)
                        SET r.delay_days = $delay_days,
                            r.severity   = $severity
                    """, {
                        "event_id": event.id,
                        "part_id": po.part_id,
                        "delay_days": shipment.delay_days or 0,
                        "severity": event.severity.value
                    })
                    created += 1

    print(f"[OK] {created} AFFECTS relationships created.")


# ---------------------------------------------------------------------------
# MAIN LOADER FUNCTION
# ---------------------------------------------------------------------------

def load_graph(clear_first: bool = True):
    """
    Load all PostgreSQL data into Neo4j as a graph.

    Args:
        clear_first: If True, wipe Neo4j before loading (default: True)
                     Set to False if you want to add to existing graph.
    """
    print("=" * 60)
    print("  SupplyChain Orchestrator -- Graph Loader")
    print("=" * 60)

    # Connect to PostgreSQL
    pg_engine = create_engine(DATABASE_URL)

    # Connect to Neo4j
    neo4j_driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    try:
        # Verify Neo4j connection
        neo4j_driver.verify_connectivity()
        print("[OK] Connected to Neo4j")
    except Exception as e:
        print(f"[ERROR] Cannot connect to Neo4j: {e}")
        print("  Make sure Neo4j Desktop is running and supplychain instance is started.")
        return

    with Session(pg_engine) as pg_session:
        with neo4j_driver.session() as neo4j_session:

            if clear_first:
                clear_graph(neo4j_session)

            print("\nCreating nodes...")
            load_suppliers(pg_session, neo4j_session)
            load_parts(pg_session, neo4j_session)
            load_warehouses(pg_session, neo4j_session)
            load_production_orders(pg_session, neo4j_session)
            load_customer_orders(pg_session, neo4j_session)
            load_disruption_events(pg_session, neo4j_session)

            print("\nCreating relationships (arrows)...")
            load_supplies_relationships(pg_session, neo4j_session)
            load_required_by_relationships(pg_session, neo4j_session)
            load_builds_relationships(pg_session, neo4j_session)
            load_waiting_on_relationships(pg_session, neo4j_session)
            load_stocked_in_relationships(pg_session, neo4j_session)
            load_affects_relationships(pg_session, neo4j_session)

            print("\nCreating indexes...")
            create_indexes(neo4j_driver)

    neo4j_driver.close()

    print("\n" + "=" * 60)
    print("  GRAPH LOAD COMPLETE")
    print("=" * 60)
    print("\n  To view the graph visually:")
    print("  1. Open Neo4j Desktop")
    print("  2. Click 'Open' on your supplychain instance")
    print("  3. In the browser, run:")
    print("     MATCH (n) RETURN n  (shows everything)")
    print("  Or run:")
    print("     MATCH p=(s:Supplier)-[*1..4]->(co:CustomerOrder)")
    print("     RETURN p  (shows full impact chain)")
    print("=" * 60)
