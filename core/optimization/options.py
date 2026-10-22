"""
core/optimization/options.py -- Recovery Option Generator

Generates all possible recovery options for a component shortage.

The 4 option types:
  A. USE_STOCK      -- Use available stock as-is, monitor remaining coverage
  B. TRANSFER       -- Move spare stock from another warehouse
  C. EXPEDITE       -- Pay extra freight to speed up the delayed shipment
  D. ALT_SUPPLIER   -- Buy from a different approved supplier

Each option is a data object describing WHAT could be done.
constraints.py then checks IF it's actually feasible.
costs.py then calculates HOW MUCH it costs.
planner.py then ranks them and picks the best.

Why generate first, then check?
  Separation of concerns -- each file does one job.
  options.py doesn't need to know about costs.
  constraints.py doesn't need to know about rankings.
  Easy to add a 5th option type later without touching other files.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum

from sqlalchemy.orm import Session
from core.models import (
    Inventory, Supplier, PurchaseOrder, Shipment,
    OrderStatus, SupplierStatus
)


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------

class OptionType(str, Enum):
    USE_STOCK    = "use_stock"
    TRANSFER     = "transfer"
    EXPEDITE     = "expedite"
    ALT_SUPPLIER = "alt_supplier"


class OptionStatus(str, Enum):
    CANDIDATE  = "candidate"    # generated, not yet checked
    FEASIBLE   = "feasible"     # passed constraint checks
    INFEASIBLE = "infeasible"   # failed constraint checks
    SELECTED   = "selected"     # chosen by planner


# ---------------------------------------------------------------------------
# DATA CLASS -- one recovery option
# ---------------------------------------------------------------------------

@dataclass
class RecoveryOption:
    """
    Represents one possible recovery action.

    Think of this as a "proposal card":
      - What type of action is it?
      - What are the key parameters?
      - Is it feasible? (filled by constraints.py)
      - What does it cost? (filled by costs.py)
      - What is its rank? (filled by planner.py)
    """
    option_id: str                    # e.g. "OPT-A", "OPT-B1"
    option_type: OptionType
    title: str                        # short human-readable label
    description: str                  # full plain English explanation

    # --- Option-specific parameters ---
    # For USE_STOCK:
    available_units: float = 0.0
    coverage_days: float = 0.0

    # For TRANSFER:
    source_warehouse_id: str = ""
    source_warehouse_name: str = ""
    transferable_units: float = 0.0
    transfer_days: int = 2            # assumed 2 days transit between warehouses

    # For EXPEDITE:
    shipment_id: str = ""
    current_delay_days: int = 0
    days_saved: int = 0               # how many days earlier it would arrive
    expedited_eta: Optional[datetime] = None

    # For ALT_SUPPLIER:
    alt_supplier_id: str = ""
    alt_supplier_name: str = ""
    alt_supplier_lead_time: int = 0
    alt_supplier_reliability: float = 0.0

    # --- Filled by constraints.py ---
    status: OptionStatus = OptionStatus.CANDIDATE
    feasibility_notes: list[str] = field(default_factory=list)

    # --- Filled by costs.py ---
    estimated_cost: float = 0.0
    cost_breakdown: dict = field(default_factory=dict)

    # --- Filled by planner.py ---
    rank: int = 0
    score: float = 0.0
    recommendation_reason: str = ""


# ---------------------------------------------------------------------------
# OPTION GENERATORS
# Each function generates one type of recovery option.
# ---------------------------------------------------------------------------

def generate_use_stock_option(
    available_units: float,
    daily_consumption: float,
    shortage_date: datetime
) -> RecoveryOption:
    """
    Option A -- USE_STOCK
    "Just use what we have and monitor coverage."

    This is always the first option to consider.
    If we have enough stock to bridge the gap, no other action needed.

    Feasible if: available stock lasts until the delayed shipment arrives.
    Cost: zero extra cost (we already have the stock).
    """
    coverage = available_units / daily_consumption if daily_consumption > 0 else 999

    return RecoveryOption(
        option_id="OPT-A",
        option_type=OptionType.USE_STOCK,
        title="Use Available Stock",
        description=(
            f"Use the {available_units:.0f} available units across all warehouses. "
            f"At {daily_consumption:.1f} units/day consumption, "
            f"stock covers {coverage:.1f} days. "
            f"Monitor daily and escalate if consumption increases."
        ),
        available_units=available_units,
        coverage_days=coverage
    )


def generate_transfer_options(
    session: Session,
    part_id: str,
    primary_warehouse_id: str,
    units_needed: float
) -> list[RecoveryOption]:
    """
    Option B -- TRANSFER
    "Move spare stock from another warehouse to cover the shortage."

    Looks at all OTHER warehouses that have available stock of this part.
    Generates one option per warehouse that has spare stock.

    Feasible if:
      - Other warehouse has enough available units
      - Transit time is fast enough to prevent production stoppage
    """
    # Find all inventory records for this part EXCEPT the primary warehouse
    other_inventory = (
        session.query(Inventory)
        .filter(
            Inventory.part_id == part_id,
            Inventory.warehouse_id != primary_warehouse_id
        )
        .all()
    )

    options = []
    idx = 1

    for inv in other_inventory:
        available = inv.quantity_on_hand - inv.quantity_reserved
        if available <= 0:
            continue

        transferable = min(available, units_needed)

        opt = RecoveryOption(
            option_id=f"OPT-B{idx}",
            option_type=OptionType.TRANSFER,
            title=f"Transfer Stock from {inv.warehouse_id}",
            description=(
                f"Transfer {transferable:.0f} units of PRT-104 from "
                f"{inv.warehouse.name} ({inv.warehouse_id}) to the primary warehouse. "
                f"Transit time estimated at 2 days. "
                f"Source warehouse has {available:.0f} units available "
                f"({inv.quantity_on_hand:.0f} on hand - {inv.quantity_reserved:.0f} reserved)."
            ),
            source_warehouse_id=inv.warehouse_id,
            source_warehouse_name=inv.warehouse.name,
            transferable_units=transferable,
            transfer_days=2
        )
        options.append(opt)
        idx += 1

    return options


def generate_expedite_options(
    session: Session,
    part_id: str
) -> list[RecoveryOption]:
    """
    Option C -- EXPEDITE
    "Pay extra freight to get the delayed shipment here faster."

    Looks at all delayed shipments for this part.
    Estimates how many days could be saved by expediting.

    Feasible if:
      - There IS a delayed shipment (otherwise nothing to expedite)
      - The supplier can actually move faster
    """
    # Find delayed purchase orders for this part
    delayed_pos = (
        session.query(PurchaseOrder, Shipment)
        .join(Shipment, Shipment.purchase_order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.part_id == part_id,
            PurchaseOrder.status == OrderStatus.DELAYED
        )
        .all()
    )

    options = []
    idx = 1

    for po, shipment in delayed_pos:
        if not shipment.revised_eta:
            continue

        today = datetime.now(timezone.utc).replace(tzinfo=None)

        # Assumption: expediting can save 2 days (air freight vs standard)
        days_saved = 2
        expedited_eta = shipment.revised_eta - timedelta(days=days_saved)

        opt = RecoveryOption(
            option_id=f"OPT-C{idx}",
            option_type=OptionType.EXPEDITE,
            title=f"Expedite Shipment {shipment.id}",
            description=(
                f"Request expedited freight for shipment {shipment.id} "
                f"(PO {po.id}, {po.quantity:.0f} units from {po.supplier.name}). "
                f"Current revised ETA: {shipment.revised_eta.strftime('%Y-%m-%d')}. "
                f"Expediting via air freight could save ~{days_saved} days, "
                f"new ETA: {expedited_eta.strftime('%Y-%m-%d')}."
            ),
            shipment_id=shipment.id,
            current_delay_days=shipment.delay_days or 0,
            days_saved=days_saved,
            expedited_eta=expedited_eta
        )
        options.append(opt)
        idx += 1

    return options


def generate_alt_supplier_options(
    session: Session,
    part_id: str,
    current_supplier_id: str
) -> list[RecoveryOption]:
    """
    Option D -- ALT_SUPPLIER
    "Buy from a different supplier who can deliver faster."

    Looks at all OTHER active suppliers who have previously supplied this part
    (i.e. have a purchase order for it in our system).

    In a real system this would check an approved supplier list.
    Here we check purchase_orders for other suppliers of the same part.

    Feasible if:
      - Another supplier exists for this part
      - Their lead time is shorter than the current delay gap
      - They are active (not on hold)
    """
    # Find other suppliers who have supplied this part before
    other_suppliers = (
        session.query(PurchaseOrder)
        .filter(
            PurchaseOrder.part_id == part_id,
            PurchaseOrder.supplier_id != current_supplier_id
        )
        .all()
    )

    # Deduplicate by supplier
    seen_suppliers = set()
    options = []
    idx = 1

    for po in other_suppliers:
        if po.supplier_id in seen_suppliers:
            continue
        seen_suppliers.add(po.supplier_id)

        supplier = po.supplier
        if supplier.status != SupplierStatus.ACTIVE:
            continue

        opt = RecoveryOption(
            option_id=f"OPT-D{idx}",
            option_type=OptionType.ALT_SUPPLIER,
            title=f"Buy from {supplier.name}",
            description=(
                f"Place an emergency purchase order with {supplier.name} "
                f"({supplier.id}, {supplier.country}). "
                f"Standard lead time: {supplier.lead_time_days} days. "
                f"Historical reliability: {supplier.reliability_score:.0%}. "
                f"This supplier has previously supplied this part."
            ),
            alt_supplier_id=supplier.id,
            alt_supplier_name=supplier.name,
            alt_supplier_lead_time=supplier.lead_time_days,
            alt_supplier_reliability=supplier.reliability_score
        )
        options.append(opt)
        idx += 1

    return options


# ---------------------------------------------------------------------------
# MAIN FUNCTION -- generate ALL options for a given shortage
# ---------------------------------------------------------------------------

def generate_all_options(
    session: Session,
    part_id: str,
    primary_warehouse_id: str,
    current_supplier_id: str,
    available_units: float,
    daily_consumption: float,
    shortage_date: Optional[datetime],
    units_needed: float
) -> list[RecoveryOption]:
    """
    Generate all possible recovery options for a component shortage.

    Args:
        session:               DB session
        part_id:               The short component (e.g. PRT-104)
        primary_warehouse_id:  Main warehouse (e.g. WH-01)
        current_supplier_id:   The delayed supplier (e.g. SUP-005)
        available_units:       Total units available right now
        daily_consumption:     Units consumed per day
        shortage_date:         When stock runs out
        units_needed:          Total units needed by upcoming production

    Returns:
        List of all RecoveryOption candidates (not yet checked for feasibility)
    """
    all_options = []

    # Option A -- always generate this
    all_options.append(generate_use_stock_option(
        available_units, daily_consumption, shortage_date
    ))

    # Option B -- one per warehouse with spare stock
    transfer_opts = generate_transfer_options(
        session, part_id, primary_warehouse_id, units_needed
    )
    all_options.extend(transfer_opts)

    # Option C -- one per delayed shipment
    expedite_opts = generate_expedite_options(session, part_id)
    all_options.extend(expedite_opts)

    # Option D -- one per alternate supplier
    alt_opts = generate_alt_supplier_options(
        session, part_id, current_supplier_id
    )
    all_options.extend(alt_opts)

    return all_options
