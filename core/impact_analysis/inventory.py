"""
core/impact_analysis/inventory.py -- Inventory Coverage Calculator

Answers two questions:
  1. How many days of stock do we have for a given part?
  2. Will a delayed shipment cause an actual shortage?

Key concept -- "available" stock vs "on hand" stock:
  on_hand   = everything physically in the warehouse
  reserved  = already committed to existing production orders
  available = on_hand - reserved  (what we can actually use)

A late shipment does NOT automatically mean a shortage.
We only have a shortage if available stock runs out BEFORE the shipment arrives.

Example:
  available = 35 units
  daily consumption = 5 units/day
  coverage = 35 / 5 = 7 days
  shipment delay = 4 days, arrives in 6 days
  verdict = NO SHORTAGE (7 days coverage > 6 days to arrival)

  But if available = 15 units:
  coverage = 15 / 5 = 3 days
  shipment arrives in 6 days
  verdict = SHORTAGE on day 3 (3 < 6)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.models import Inventory, PurchaseOrder, Shipment, OrderStatus


# ---------------------------------------------------------------------------
# DATA CLASSES
# These are simple containers to hold calculation results.
# Using @dataclass means Python auto-generates __init__, __repr__ etc.
# Much cleaner than passing around raw dictionaries.
# ---------------------------------------------------------------------------

@dataclass
class WarehouseStock:
    """Stock position for one part in one warehouse."""
    warehouse_id: str
    warehouse_name: str
    on_hand: float
    reserved: float
    available: float          # = on_hand - reserved


@dataclass
class InboundShipment:
    """An inbound shipment that will replenish stock."""
    shipment_id: str
    purchase_order_id: str
    quantity: float
    original_eta: datetime
    revised_eta: Optional[datetime]   # None if no delay
    delay_days: int
    effective_eta: datetime           # revised_eta if delayed, else original_eta


@dataclass
class CoverageResult:
    """
    Full coverage analysis result for one part.
    This is what gets passed to the rest of the impact engine.
    """
    part_id: str
    part_name: str

    # Stock across all warehouses
    total_on_hand: float
    total_reserved: float
    total_available: float

    # Per-warehouse breakdown
    warehouse_stocks: list[WarehouseStock] = field(default_factory=list)

    # Inbound shipments for this part
    inbound_shipments: list[InboundShipment] = field(default_factory=list)

    # Daily consumption rate (units per day)
    # Calculated from: total quantity needed by upcoming production orders / days until they start
    daily_consumption: float = 0.0

    # How many days the available stock will last
    coverage_days: float = 0.0

    # The specific date when stock is expected to run out
    shortage_date: Optional[datetime] = None

    # Is there actually a shortage?
    has_shortage: bool = False

    # Human-readable verdict
    verdict: str = ""

    # The delayed shipment that triggered this analysis (if any)
    delayed_shipment_id: Optional[str] = None


# ---------------------------------------------------------------------------
# MAIN CALCULATION FUNCTION
# ---------------------------------------------------------------------------

def calculate_coverage(
    session: Session,
    part_id: str,
    daily_consumption: float,
    as_of_date: Optional[datetime] = None
) -> CoverageResult:
    """
    Calculate inventory coverage for a specific part.

    Args:
        session:           SQLAlchemy DB session
        part_id:           The part to analyze (e.g. "PRT-104")
        daily_consumption: How many units are consumed per day
                           (calculated from production order requirements)
        as_of_date:        Reference date for calculations (defaults to today)

    Returns:
        CoverageResult with full analysis

    Why daily_consumption as a parameter?
        The consumption rate depends on upcoming production orders,
        which are computed by order_impact.py.
        We keep this function focused: it only does stock math.
    """
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # STEP 1: Get all inventory records for this part across all warehouses
    # ------------------------------------------------------------------
    # We query the inventory table joining with warehouses to get names.
    # SQLAlchemy lets us do this through the relationship we defined in models.py.
    inventory_records = (
        session.query(Inventory)
        .filter(Inventory.part_id == part_id)
        .all()
    )

    warehouse_stocks = []
    total_on_hand = 0.0
    total_reserved = 0.0

    for inv in inventory_records:
        available = max(0.0, inv.quantity_on_hand - inv.quantity_reserved)
        ws = WarehouseStock(
            warehouse_id=inv.warehouse_id,
            warehouse_name=inv.warehouse.name,    # via relationship, no JOIN needed
            on_hand=inv.quantity_on_hand,
            reserved=inv.quantity_reserved,
            available=available
        )
        warehouse_stocks.append(ws)
        total_on_hand += inv.quantity_on_hand
        total_reserved += inv.quantity_reserved

    total_available = max(0.0, total_on_hand - total_reserved)

    # ------------------------------------------------------------------
    # STEP 2: Get all inbound shipments for this part
    # We join purchase_orders → shipments to find what's coming
    # and when it's expected to arrive.
    # ------------------------------------------------------------------
    inbound_records = (
        session.query(Shipment, PurchaseOrder)
        .join(PurchaseOrder, Shipment.purchase_order_id == PurchaseOrder.id)
        .filter(PurchaseOrder.part_id == part_id)
        .filter(PurchaseOrder.status.in_([
            OrderStatus.CONFIRMED,
            OrderStatus.IN_TRANSIT,
            OrderStatus.DELAYED
        ]))
        .all()
    )

    inbound_shipments = []
    delayed_shipment_id = None

    for shipment, po in inbound_records:
        # effective_eta: use revised_eta if there's a delay, otherwise original
        effective_eta = shipment.revised_eta if shipment.revised_eta else shipment.scheduled_date

        inbound = InboundShipment(
            shipment_id=shipment.id,
            purchase_order_id=po.id,
            quantity=po.quantity,
            original_eta=shipment.scheduled_date,
            revised_eta=shipment.revised_eta,
            delay_days=shipment.delay_days or 0,
            effective_eta=effective_eta
        )
        inbound_shipments.append(inbound)

        # Track if there's a delayed shipment
        if shipment.delay_days and shipment.delay_days > 0:
            delayed_shipment_id = shipment.id

    # ------------------------------------------------------------------
    # STEP 3: Calculate coverage days
    # coverage_days = total_available / daily_consumption
    #
    # Edge cases:
    #   - daily_consumption = 0 → infinite coverage (no production planned)
    #   - total_available = 0   → shortage already exists NOW
    # ------------------------------------------------------------------
    if daily_consumption <= 0:
        # No production orders consuming this part → no shortage possible
        coverage_days = float('inf')
        shortage_date = None
        has_shortage = False
        verdict = "No active consumption — no shortage risk."
    elif total_available <= 0:
        # Already out of stock
        coverage_days = 0.0
        shortage_date = as_of_date
        has_shortage = True
        verdict = "SHORTAGE NOW — zero available stock."
    else:
        # Normal calculation
        coverage_days = total_available / daily_consumption
        shortage_date = as_of_date + timedelta(days=coverage_days)

        # ------------------------------------------------------------------
        # STEP 4: Compare coverage against inbound shipments
        # If the shipment arrives BEFORE we run out → no shortage
        # If the shipment arrives AFTER we run out  → shortage confirmed
        # ------------------------------------------------------------------
        has_shortage = True   # assume shortage until proven otherwise
        verdict = ""

        # Check if any inbound shipment arrives before the shortage date
        for inbound in inbound_shipments:
            days_until_arrival = (inbound.effective_eta - as_of_date).days

            if days_until_arrival <= coverage_days:
                # Shipment arrives before we run out
                has_shortage = False
                verdict = (
                    f"No shortage — stock lasts {coverage_days:.1f} days, "
                    f"shipment {inbound.shipment_id} arrives in {days_until_arrival} days."
                )
                break

        if has_shortage:
            # Find the nearest inbound shipment for context
            if inbound_shipments:
                nearest = min(inbound_shipments, key=lambda s: s.effective_eta)
                days_until_arrival = (nearest.effective_eta - as_of_date).days
                verdict = (
                    f"SHORTAGE CONFIRMED — stock runs out in {coverage_days:.1f} days "
                    f"but nearest shipment ({nearest.shipment_id}) arrives in "
                    f"{days_until_arrival} days. Gap: {days_until_arrival - coverage_days:.1f} days."
                )
            else:
                verdict = (
                    f"SHORTAGE CONFIRMED — stock runs out in {coverage_days:.1f} days "
                    f"and no inbound shipments found."
                )

    # Get part name from the first inventory record's relationship
    part_name = inventory_records[0].part.name if inventory_records else part_id

    return CoverageResult(
        part_id=part_id,
        part_name=part_name,
        total_on_hand=total_on_hand,
        total_reserved=total_reserved,
        total_available=total_available,
        warehouse_stocks=warehouse_stocks,
        inbound_shipments=inbound_shipments,
        daily_consumption=daily_consumption,
        coverage_days=coverage_days if coverage_days != float('inf') else 9999.0,
        shortage_date=shortage_date,
        has_shortage=has_shortage,
        verdict=verdict,
        delayed_shipment_id=delayed_shipment_id
    )
