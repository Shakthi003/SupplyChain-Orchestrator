"""
core/impact_analysis/bom_tracer.py -- Bill of Materials Traversal

Answers the question:
  "Which finished goods (products) use a given component?"

This is the KEY to impact tracing. Without this, we cannot know
which production orders are affected by a component shortage.

How BOM traversal works:
  We have a component: PRT-104 (Hydraulic Valve)
  We look up the bill_of_materials table asking:
    "Where does PRT-104 appear as a child_part_id?"

  Answer:
    BOM-002: FGD-201 needs 2x PRT-104   → Hydraulic Control Unit Alpha
    BOM-010: FGD-203 needs 1x PRT-104   → Industrial Pump Assembly P-22

  So if PRT-104 is short:
    FGD-201 production is at risk
    FGD-203 production is at risk
    FGD-202, FGD-204, FGD-205 are NOT affected (don't use PRT-104)

Why "traversal"?
  In a real BOM, products can be nested many levels deep:
    Finished Good → Sub-Assembly → Component → Raw Material
  Traversal means we can walk up or down this tree.
  For now we do one level (direct parents) which covers our scenario.
  The structure supports deeper traversal when needed.
"""

from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from core.models import BillOfMaterials, Part


# ---------------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------------

@dataclass
class AffectedProduct:
    """
    A finished good that is affected because it uses the short component.
    """
    product_id: str           # e.g. "FGD-201"
    product_name: str         # e.g. "Hydraulic Control Unit Alpha"
    quantity_per_unit: float  # How many units of the component needed per product
    bom_entry_id: str         # The BOM record that links them (for audit trail)


@dataclass
class BOMTraceResult:
    """
    Full result of tracing a component through the BOM.
    """
    component_part_id: str
    component_part_name: str

    # List of all finished goods that use this component
    affected_products: list[AffectedProduct] = field(default_factory=list)

    # Summary counts
    total_affected_products: int = 0


# ---------------------------------------------------------------------------
# MAIN TRACE FUNCTION
# ---------------------------------------------------------------------------

def trace_component_to_products(
    session: Session,
    component_part_id: str
) -> BOMTraceResult:
    """
    Find all finished goods (parent parts) that use a given component (child part).

    Args:
        session:            SQLAlchemy DB session
        component_part_id:  The component to trace (e.g. "PRT-104")

    Returns:
        BOMTraceResult listing all products that use this component

    How it queries:
        SELECT bom.*, parts.*
        FROM bill_of_materials bom
        JOIN parts ON bom.parent_part_id = parts.id
        WHERE bom.child_part_id = 'PRT-104'
    """

    # Query: find all BOM entries where this component is the child
    # Then join to get the parent (finished good) details
    bom_entries = (
        session.query(BillOfMaterials)
        .filter(BillOfMaterials.child_part_id == component_part_id)
        .all()
    )

    affected_products = []

    for bom in bom_entries:
        # bom.parent_part gives us the Part object via the relationship
        # No JOIN needed -- SQLAlchemy handles it
        parent = bom.parent_part

        affected = AffectedProduct(
            product_id=parent.id,
            product_name=parent.name,
            quantity_per_unit=bom.quantity_required,
            bom_entry_id=bom.id
        )
        affected_products.append(affected)

    # Get the component name for the result
    component = session.get(Part, component_part_id)
    component_name = component.name if component else component_part_id

    return BOMTraceResult(
        component_part_id=component_part_id,
        component_part_name=component_name,
        affected_products=affected_products,
        total_affected_products=len(affected_products)
    )
