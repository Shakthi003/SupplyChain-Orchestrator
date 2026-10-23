"""
core/impact_analysis/order_impact.py -- Affected Orders Finder

Answers two questions:
  1. Which production orders are at risk due to a component shortage?
  2. Which customer orders are at risk as a result?

How it works:
  Step 1 (from bom_tracer): We know FGD-201 and FGD-203 use PRT-104
  Step 2 (this file):
    Find all production orders building FGD-201 or FGD-203
    Calculate exactly how many units of PRT-104 each order needs
    Compare against available stock to determine if it can start on time
    Find all customer orders linked to at-risk production orders

Risk assessment logic:
  A production order is AT RISK if:
    available_stock < units_needed_by_this_order
    OR the part shortage date is before the production order's planned start

  A customer order is AT RISK if:
    its linked production order is AT RISK
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.models import ProductionOrder, CustomerOrder, BillOfMaterials, ProductionStatus, OrderStatus


# ---------------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------------

@dataclass
class ProductionOrderRisk:
    """Risk assessment for a single production order."""
    order_id: str                     # e.g. "PRD-301"
    product_id: str                   # e.g. "FGD-201"
    product_name: str
    quantity_to_produce: float
    planned_start: datetime
    planned_end: datetime
    current_status: str

    # How many units of the short component this order needs
    component_units_needed: float

    # Risk assessment
    is_at_risk: bool
    risk_reason: str                  # Plain English explanation

    # Financial context
    customer_orders_count: int = 0
    total_customer_value: float = 0.0


@dataclass
class CustomerOrderRisk:
    """Risk assessment for a single customer order."""
    order_id: str                     # e.g. "CO-501"
    customer_name: str
    product_id: str
    product_name: str
    quantity: float
    promised_delivery_date: datetime
    order_value: float
    linked_production_order_id: str

    # Risk assessment
    is_at_risk: bool
    risk_reason: str


@dataclass
class OrderImpactResult:
    """Complete impact assessment across all orders."""
    component_part_id: str
    component_part_name: str

    # All production orders that BUILD products using the component
    production_orders: list[ProductionOrderRisk] = field(default_factory=list)

    # All customer orders linked to at-risk production orders
    customer_orders: list[CustomerOrderRisk] = field(default_factory=list)

    # Summary statistics
    total_production_at_risk: int = 0
    total_customers_at_risk: int = 0
    total_financial_exposure: float = 0.0

    # The daily consumption rate (total units needed / days until first start)
    # Used by inventory.py to calculate coverage
    daily_consumption_rate: float = 0.0


# ---------------------------------------------------------------------------
# HELPER: calculate how many units of a component a production order needs
# ---------------------------------------------------------------------------

def get_component_requirement(
    session: Session,
    product_part_id: str,
    component_part_id: str,
    production_quantity: float
) -> float:
    """
    How many units of component_part_id does one production order need?

    Example:
        product = FGD-201
        component = PRT-104
        BOM says FGD-201 needs 2x PRT-104 per unit
        production_quantity = 25 units
        result = 25 * 2 = 50 units of PRT-104 needed

    Args:
        product_part_id:    The finished good being built
        component_part_id:  The component we are checking
        production_quantity: How many units of the finished good to build
    """
    bom_entry = (
        session.query(BillOfMaterials)
        .filter(
            BillOfMaterials.parent_part_id == product_part_id,
            BillOfMaterials.child_part_id == component_part_id
        )
        .first()
    )

    if bom_entry is None:
        return 0.0  # This product does not use this component at all

    return bom_entry.quantity_required * production_quantity


# ---------------------------------------------------------------------------
# MAIN IMPACT FUNCTION
# ---------------------------------------------------------------------------

def find_affected_orders(
    session: Session,
    component_part_id: str,
    component_part_name: str,
    affected_product_ids: list[str],
    total_available_stock: float,
    shortage_date: Optional[datetime],
    as_of_date: datetime
) -> OrderImpactResult:
    """
    Find all production and customer orders affected by a component shortage.

    Args:
        session:               DB session
        component_part_id:     The short component (e.g. "PRT-104")
        component_part_name:   Human-readable name
        affected_product_ids:  Products that use this component (from bom_tracer)
        total_available_stock: How many units are available right now
        shortage_date:         When stock is expected to run out (None = no shortage)
        as_of_date:            Reference date for calculations (see core/clock.py)
    """
    result = OrderImpactResult(
        component_part_id=component_part_id,
        component_part_name=component_part_name
    )

    # ------------------------------------------------------------------
    # STEP 1: Find all PLANNED or IN_PROGRESS production orders
    # that build any of the affected products
    # ------------------------------------------------------------------
    production_orders = (
        session.query(ProductionOrder)
        .filter(
            ProductionOrder.product_part_id.in_(affected_product_ids),
            ProductionOrder.status.in_([
                ProductionStatus.PLANNED,
                ProductionStatus.IN_PROGRESS
            ])
        )
        .order_by(ProductionOrder.planned_start)
        .all()
    )

    # ------------------------------------------------------------------
    # STEP 2: Calculate daily consumption rate
    # We spread total component usage across the full production window:
    #   window = from today to the end of the LAST production order
    # This gives a realistic average daily draw on inventory.
    #
    # Example:
    #   PRD-301 needs 50 units (starts day+3, ends day+8)
    #   PRD-302 needs 15 units (starts day+5, ends day+12)
    #   Total = 65 units over a 12-day window = 5.4 units/day
    # ------------------------------------------------------------------
    total_units_needed_soon = 0.0
    latest_end_date = None

    for po in production_orders:
        units_needed = get_component_requirement(
            session, po.product_part_id, component_part_id, po.quantity
        )
        total_units_needed_soon += units_needed

        if latest_end_date is None or po.planned_end > latest_end_date:
            latest_end_date = po.planned_end

    # Spread consumption over the full window from today to last order end
    if latest_end_date is not None and total_units_needed_soon > 0:
        window_days = max(1, (latest_end_date - as_of_date).days)
        result.daily_consumption_rate = round(total_units_needed_soon / window_days, 2)

    # ------------------------------------------------------------------
    # STEP 3: Assess risk for each production order
    # ------------------------------------------------------------------
    stock_remaining = total_available_stock  # track as we allocate to orders

    for po in production_orders:
        product = po.product     # via SQLAlchemy relationship

        # How much of the component does this production order need?
        units_needed = get_component_requirement(
            session, po.product_part_id, component_part_id, po.quantity
        )

        days_until_start = max(0, (po.planned_start - as_of_date).days)

        # Risk logic:
        # AT RISK if:
        #   a) There is a shortage date AND production starts after shortage
        #   b) Available stock is less than what this order needs
        #   c) Order was already at-risk status
        is_at_risk = False
        risk_reason = "Within safe stock levels."

        if shortage_date is not None and po.planned_start >= shortage_date:
            is_at_risk = True
            days_short = (po.planned_start - shortage_date).days
            risk_reason = (
                f"Production starts {days_until_start} days from now, but "
                f"stock runs out {days_short} days before planned start. "
                f"Needs {units_needed:.0f} units of {component_part_name}."
            )
        elif units_needed > stock_remaining:
            is_at_risk = True
            risk_reason = (
                f"Needs {units_needed:.0f} units but only "
                f"{stock_remaining:.0f} available after prior allocations."
            )

        # Get linked customer orders for this production order
        linked_cos = (
            session.query(CustomerOrder)
            .filter(CustomerOrder.production_order_id == po.id)
            .all()
        )
        customer_value = sum(co.order_value or 0 for co in linked_cos)

        po_risk = ProductionOrderRisk(
            order_id=po.id,
            product_id=po.product_part_id,
            product_name=product.name,
            quantity_to_produce=po.quantity,
            planned_start=po.planned_start,
            planned_end=po.planned_end,
            current_status=po.status.value,
            component_units_needed=units_needed,
            is_at_risk=is_at_risk,
            risk_reason=risk_reason,
            customer_orders_count=len(linked_cos),
            total_customer_value=customer_value
        )
        result.production_orders.append(po_risk)

        if is_at_risk:
            result.total_production_at_risk += 1

        # Reduce remaining stock (first-come-first-served allocation)
        stock_remaining = max(0.0, stock_remaining - units_needed)

    # ------------------------------------------------------------------
    # STEP 4: Find all customer orders linked to at-risk production orders
    # ------------------------------------------------------------------
    at_risk_prod_ids = [
        po.order_id for po in result.production_orders if po.is_at_risk
    ]

    if at_risk_prod_ids:
        customer_orders = (
            session.query(CustomerOrder)
            .filter(
                CustomerOrder.production_order_id.in_(at_risk_prod_ids),
                CustomerOrder.status.in_([
                    OrderStatus.CONFIRMED,
                    OrderStatus.PENDING
                ])
            )
            .order_by(CustomerOrder.promised_delivery_date)
            .all()
        )

        for co in customer_orders:
            # Find the matching production order risk to get context
            prod_risk = next(
                (p for p in result.production_orders if p.order_id == co.production_order_id),
                None
            )

            co_risk = CustomerOrderRisk(
                order_id=co.id,
                customer_name=co.customer_name,
                product_id=co.part_id,
                product_name=co.production_order.product.name if co.production_order else co.part_id,
                quantity=co.quantity,
                promised_delivery_date=co.promised_delivery_date,
                order_value=co.order_value or 0.0,
                linked_production_order_id=co.production_order_id,
                is_at_risk=True,
                risk_reason=(
                    f"Linked production order {co.production_order_id} is at risk. "
                    f"{prod_risk.risk_reason if prod_risk else ''}"
                )
            )
            result.customer_orders.append(co_risk)
            result.total_customers_at_risk += 1
            result.total_financial_exposure += co.order_value or 0.0

    return result
