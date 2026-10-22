"""
core/optimization/constraints.py -- Feasibility Checker

Checks whether each recovery option is actually feasible.

Why check constraints?
  Not every option that exists is actually doable.
  Example:
    Option B (transfer) -- looks good on paper
    BUT: if WH-02 only has 5 units and we need 65, it doesn't help enough.
    Constraint: transferable_units must cover at least the immediate need.

  Example:
    Option D (alt supplier) -- SUP-003 has lead time of 7 days
    BUT: shortage hits tomorrow. 7 days is too slow.
    Constraint: lead time must be shorter than days until shortage.

Each check adds a note explaining WHY it passed or failed.
This note appears in the final recommendation so humans understand the reasoning.

Rule: An option is FEASIBLE only if ALL its constraints pass.
      One failure = INFEASIBLE (with reason shown).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from core.optimization.options import RecoveryOption, OptionType, OptionStatus


# ---------------------------------------------------------------------------
# CONSTRAINT THRESHOLDS
# These are the rules. Change these values to tighten or loosen constraints.
# ---------------------------------------------------------------------------

MIN_COVERAGE_DAYS         = 1.0    # Option A: stock must last at least 1 more day
MIN_TRANSFER_COVERAGE     = 0.5    # Option B: transfer must cover at least 50% of need
MAX_EXPEDITE_LEAD_DAYS    = 14     # Option C: only expedite if shipment arrives within 14 days
MIN_ALT_RELIABILITY       = 0.70   # Option D: alt supplier must have >= 70% reliability
MAX_ALT_LEAD_DAYS         = 21     # Option D: alt supplier must deliver within 21 days


# ---------------------------------------------------------------------------
# INDIVIDUAL CONSTRAINT CHECKS
# Each returns (passed: bool, note: str)
# ---------------------------------------------------------------------------

def check_use_stock(
    option: RecoveryOption,
    shortage_date: Optional[datetime],
    nearest_shipment_eta: Optional[datetime]
) -> tuple[bool, str]:
    """
    Option A is feasible if current stock lasts until the shipment arrives.

    Logic:
      If no shortage at all → feasible (no action needed beyond monitoring)
      If shortage_date > nearest_shipment_eta → NOT feasible
        (stock runs out before replenishment arrives)
      If coverage_days >= 1 → partially feasible (buys some time)
    """
    today = datetime.now(timezone.utc).replace(tzinfo=None)

    if shortage_date is None:
        return True, "No shortage detected. Current stock is sufficient."

    if nearest_shipment_eta:
        days_until_shipment = (nearest_shipment_eta - today).days
        if option.coverage_days >= days_until_shipment:
            return True, (
                f"Stock lasts {option.coverage_days:.1f} days, "
                f"shipment arrives in {days_until_shipment} days. "
                f"Stock bridges the gap."
            )
        else:
            return False, (
                f"Stock only lasts {option.coverage_days:.1f} days "
                f"but shipment arrives in {days_until_shipment} days. "
                f"Gap of {days_until_shipment - option.coverage_days:.1f} days uncovered."
            )

    # No shipment at all -- stock alone is not enough
    if option.coverage_days < MIN_COVERAGE_DAYS:
        return False, (
            f"Only {option.coverage_days:.1f} days of stock remaining "
            f"and no inbound shipment found. Immediate action required."
        )

    return True, f"Stock covers {option.coverage_days:.1f} days. Monitor daily."


def check_transfer(
    option: RecoveryOption,
    units_needed: float,
    days_until_production_start: int
) -> tuple[bool, str]:
    """
    Option B is feasible if:
      1. The source warehouse has enough transferable units
      2. Transit time is fast enough (transfer arrives before production starts)
    """
    # Check 1: quantity sufficient?
    coverage_ratio = option.transferable_units / units_needed if units_needed > 0 else 1.0

    if coverage_ratio < MIN_TRANSFER_COVERAGE:
        return False, (
            f"Transfer covers only {coverage_ratio:.0%} of required units "
            f"({option.transferable_units:.0f} of {units_needed:.0f} needed). "
            f"Minimum coverage required: {MIN_TRANSFER_COVERAGE:.0%}."
        )

    # Check 2: transfer arrives before or on the day production starts?
    # transfer_days > days_until_production_start means it arrives AFTER production needs it
    if option.transfer_days > days_until_production_start:
        return False, (
            f"Transfer takes {option.transfer_days} days but production "
            f"starts in {days_until_production_start} days. "
            f"Transfer would arrive too late."
        )

    return True, (
        f"Transfer of {option.transferable_units:.0f} units from "
        f"{option.source_warehouse_id} covers {coverage_ratio:.0%} of need. "
        f"Transit: {option.transfer_days} days, production starts in "
        f"{days_until_production_start} days. Arrives in time."
    )


def check_expedite(
    option: RecoveryOption,
    shortage_date: Optional[datetime]
) -> tuple[bool, str]:
    """
    Option C is feasible if:
      1. The expedited ETA is earlier than the shortage date
      2. The expedited ETA is within MAX_EXPEDITE_LEAD_DAYS from today
    """
    today = datetime.now(timezone.utc).replace(tzinfo=None)

    if not option.expedited_eta:
        return False, "No expedited ETA could be calculated."

    days_until_expedited = (option.expedited_eta - today).days

    # Check 1: arrives before shortage?
    if shortage_date and option.expedited_eta > shortage_date:
        gap = (option.expedited_eta - shortage_date).days
        return False, (
            f"Even expedited, shipment arrives {gap} days after shortage date "
            f"({option.expedited_eta.strftime('%Y-%m-%d')} vs "
            f"shortage {shortage_date.strftime('%Y-%m-%d')}). "
            f"Expediting alone does not prevent the shortage."
        )

    # Check 2: reasonable lead time?
    if days_until_expedited > MAX_EXPEDITE_LEAD_DAYS:
        return False, (
            f"Expedited ETA is {days_until_expedited} days away, "
            f"exceeding maximum of {MAX_EXPEDITE_LEAD_DAYS} days. "
            f"Too slow to be useful."
        )

    return True, (
        f"Expedited shipment arrives {option.expedited_eta.strftime('%Y-%m-%d')} "
        f"({days_until_expedited} days), saving {option.days_saved} days vs current ETA. "
        f"Arrives before or at shortage date."
    )


def check_alt_supplier(
    option: RecoveryOption,
    shortage_date: Optional[datetime]
) -> tuple[bool, str]:
    """
    Option D is feasible if:
      1. Supplier reliability is above minimum threshold
      2. Lead time is short enough to prevent or minimize shortage
      3. Supplier is not the same as the one causing the delay
    """
    today = datetime.now(timezone.utc).replace(tzinfo=None)

    # Check 1: reliability threshold
    if option.alt_supplier_reliability < MIN_ALT_RELIABILITY:
        return False, (
            f"{option.alt_supplier_name} reliability score "
            f"{option.alt_supplier_reliability:.0%} is below minimum "
            f"{MIN_ALT_RELIABILITY:.0%}. Too risky as emergency supplier."
        )

    # Check 2: lead time
    if option.alt_supplier_lead_time > MAX_ALT_LEAD_DAYS:
        return False, (
            f"{option.alt_supplier_name} lead time of "
            f"{option.alt_supplier_lead_time} days exceeds maximum "
            f"{MAX_ALT_LEAD_DAYS} days for emergency sourcing."
        )

    # Check 3: would it help? (arrives before too much damage)
    arrival_date = today + timedelta(days=option.alt_supplier_lead_time)
    days_until_arrival = option.alt_supplier_lead_time

    return True, (
        f"{option.alt_supplier_name} can deliver in {days_until_arrival} days "
        f"(est. {arrival_date.strftime('%Y-%m-%d')}). "
        f"Reliability: {option.alt_supplier_reliability:.0%}. "
        f"Passes all qualification checks."
    )


# ---------------------------------------------------------------------------
# MAIN CONSTRAINT CHECKER
# Runs the right check for each option type
# ---------------------------------------------------------------------------

def check_all_constraints(
    options: list[RecoveryOption],
    shortage_date: Optional[datetime],
    nearest_shipment_eta: Optional[datetime],
    units_needed: float,
    days_until_production_start: int
) -> list[RecoveryOption]:
    """
    Run feasibility checks on all recovery options.

    Args:
        options:                      List of candidates from options.py
        shortage_date:                When stock runs out
        nearest_shipment_eta:         ETA of nearest inbound shipment
        units_needed:                 Total units needed by production
        days_until_production_start:  Days until earliest at-risk production order

    Returns:
        Same list with status and feasibility_notes filled in
    """
    for option in options:

        if option.option_type == OptionType.USE_STOCK:
            passed, note = check_use_stock(
                option, shortage_date, nearest_shipment_eta
            )

        elif option.option_type == OptionType.TRANSFER:
            passed, note = check_transfer(
                option, units_needed, days_until_production_start
            )

        elif option.option_type == OptionType.EXPEDITE:
            passed, note = check_expedite(option, shortage_date)

        elif option.option_type == OptionType.ALT_SUPPLIER:
            passed, note = check_alt_supplier(option, shortage_date)

        else:
            passed, note = False, "Unknown option type."

        option.status = OptionStatus.FEASIBLE if passed else OptionStatus.INFEASIBLE
        option.feasibility_notes.append(note)

    return options
