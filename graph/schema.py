"""
graph/schema.py -- Neo4j Graph Schema Definition

Defines what NODES and RELATIONSHIPS exist in our graph.

Same concept as core/models.py for PostgreSQL:
  models.py  defines tables and columns
  schema.py  defines nodes and relationships

But unlike models.py, schema.py does NOT create anything in Neo4j.
It just defines constants and provides a function to create indexes.

WHY INDEXES?
  When queries.py asks "find the node where id = SUP-005",
  Neo4j scans every single node unless we create an index.
  An index is like the index at the back of a book --
  instead of reading every page, you jump straight to the right page.
  We create one index per node type on the id property.

OUR GRAPH STRUCTURE:
  Nodes (things):
    Supplier, Part, Warehouse, ProductionOrder, CustomerOrder, DisruptionEvent

  Relationships (connections):
    (Supplier)        -[SUPPLIES]->         (Part)
    (Part)            -[REQUIRED_BY]->      (Part)        via BOM
    (ProductionOrder) -[BUILDS]->           (Part)        finished good
    (CustomerOrder)   -[WAITING_ON]->       (ProductionOrder)
    (Part)            -[STOCKED_IN]->       (Warehouse)
    (Shipment)        -[DELIVERS]->         (Part)
    (DisruptionEvent) -[AFFECTS]->          (Part)

  Reading it:
    SUP-005 SUPPLIES PRT-104
    PRT-104 REQUIRED_BY FGD-201   (FGD-201 needs PRT-104)
    PRD-301 BUILDS FGD-201
    CO-501  WAITING_ON PRD-301
"""

from neo4j import GraphDatabase
from core.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


# ---------------------------------------------------------------------------
# NODE LABELS
# These are the "types" of nodes in our graph.
# Like table names in PostgreSQL.
# ---------------------------------------------------------------------------

class NodeLabel:
    SUPPLIER          = "Supplier"
    PART              = "Part"
    WAREHOUSE         = "Warehouse"
    PURCHASE_ORDER    = "PurchaseOrder"
    SHIPMENT          = "Shipment"
    PRODUCTION_ORDER  = "ProductionOrder"
    CUSTOMER_ORDER    = "CustomerOrder"
    DISRUPTION_EVENT  = "DisruptionEvent"


# ---------------------------------------------------------------------------
# RELATIONSHIP TYPES
# These are the "arrows" between nodes.
# Like foreign keys in PostgreSQL -- but directional and named.
# ---------------------------------------------------------------------------

class RelType:
    SUPPLIES      = "SUPPLIES"       # Supplier  → Part
    REQUIRED_BY   = "REQUIRED_BY"    # Part(comp) → Part(finished good)
    BUILDS        = "BUILDS"         # ProductionOrder → Part(finished good)
    WAITING_ON    = "WAITING_ON"     # CustomerOrder → ProductionOrder
    STOCKED_IN    = "STOCKED_IN"     # Part → Warehouse
    DELIVERS      = "DELIVERS"       # Shipment → Part
    AFFECTS       = "AFFECTS"        # DisruptionEvent → Part
    ORDERED_FROM  = "ORDERED_FROM"   # PurchaseOrder → Supplier


# ---------------------------------------------------------------------------
# CREATE INDEXES
# Run this once after loading data.
# Makes all id-based lookups fast.
# ---------------------------------------------------------------------------

def create_indexes(driver: GraphDatabase.driver):
    """
    Create indexes on the id property of each node type.

    Without indexes:
      MATCH (s:Supplier {id: 'SUP-005'})
      → Neo4j scans ALL Supplier nodes to find it  (slow)

    With indexes:
      → Neo4j jumps directly to SUP-005  (fast)

    Safe to run multiple times -- IF NOT EXISTS prevents duplicates.
    """
    indexes = [
        f"CREATE INDEX supplier_id IF NOT EXISTS FOR (n:{NodeLabel.SUPPLIER}) ON (n.id)",
        f"CREATE INDEX part_id IF NOT EXISTS FOR (n:{NodeLabel.PART}) ON (n.id)",
        f"CREATE INDEX warehouse_id IF NOT EXISTS FOR (n:{NodeLabel.WAREHOUSE}) ON (n.id)",
        f"CREATE INDEX po_id IF NOT EXISTS FOR (n:{NodeLabel.PURCHASE_ORDER}) ON (n.id)",
        f"CREATE INDEX shipment_id IF NOT EXISTS FOR (n:{NodeLabel.SHIPMENT}) ON (n.id)",
        f"CREATE INDEX prod_id IF NOT EXISTS FOR (n:{NodeLabel.PRODUCTION_ORDER}) ON (n.id)",
        f"CREATE INDEX co_id IF NOT EXISTS FOR (n:{NodeLabel.CUSTOMER_ORDER}) ON (n.id)",
        f"CREATE INDEX event_id IF NOT EXISTS FOR (n:{NodeLabel.DISRUPTION_EVENT}) ON (n.id)",
    ]

    with driver.session() as session:
        for index_query in indexes:
            session.run(index_query)

    print(f"[OK] {len(indexes)} indexes created in Neo4j.")


def get_driver():
    """Create and return a Neo4j driver using credentials from .env"""
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
