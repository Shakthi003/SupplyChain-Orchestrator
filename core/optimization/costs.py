"""
core/optimization/costs.py -- Cost Calculator

Calculates the estimated cost of each feasible recovery option.

Why calculate costs separately from constraints?
  Constraints answer: "CAN we do this?"
  Costs answer:       "How much WILL it cost?"

  Keeping them separate means:
    - We can change cost formulas without touching constraint logic
    - Every cost is traceable (we show the breakdown)
    - Costs are deterministic -- same inputs, same output every time
    - The AI agent never guesses costs -- it always uses these formulas

Cost components per option type:

  USE_STOCK:
    No extra cost. We already own the stock.
    Opportunity cost = 0 (we would use it anyway).

  TRANSFER:
    Freight cost = distance-based rate * units * weight per unit
    Handling cost = fixed rate per transfer

  EXPEDITE:
    Premium freight = standard freight * expedite_multiplier
    We use air freight rate vs standard ground/ocean rate.

  ALT_SUPPLIER:
    Unit cost difference = (alt_unit_cost - standard_unit_cost) * quantity
    Emergency order premium = fixed surcharge for rush orders
    Qualification check cost = if new supplier, add onboarding cost

All costs are in USD. All formulas are documented and auditable.
"""

from core.optimization.options import RecoveryOption, OptionType, OptionStatus


# ---------------------------------------------------------------------------
# COST CONSTANTS
# These are the rate assumptions. In a real system these come from
# a rates table in the database. Here we hardcode realistic estimates.
# ---------------------------------------------------------------------------

# Transfer costs
FREIGHT_RATE_PER_UNIT    = 2.50    # USD per unit transferred (domestic truck)
HANDLING_FEE_PER_TRANSFER = 150.0  # USD fixed handling fee per transfer

# Expedite costs
STANDARD_FREIGHT_COST    = 500.0   # USD base freight for this shipment
EXPEDITE_MULTIPLIER      = 3.5     # air freight costs 3.5x standard freight
# So expediting costs: 500 * 3.5 = $1,750 extra vs standard

# Alt supplier costs
ALT_SUPPLIER_PREMIUM_PCT = 0.15    # 15% price premium for emergency orders
EMERGENCY_ORDER_FEE      = 250.0   # USD fixed fee for rush purchase order

# Delay cost (what it costs US if production is delayed)
DELAY_COST_PER_DAY       = 1200.0  # USD per day of production delay
# This is the "cost of doing nothing" -- used as baseline comparison


# ---------------------------------------------------------------------------
# INDIVIDUAL COST CALCULATORS
# ---------------------------------------------------------------------------

def cost_use_stock(option: RecoveryOption) -> dict:
    """
    Option A -- USE_STOCK
    No incremental cost -- we already own the stock.

    However we note the monitoring effort cost as negligible.
    """
    return {
        "incremental_freight": 0.0,
        "handling": 0.0,
        "premium": 0.0,
        "total": 0.0,
        "note": "No incremental cost. Stock already owned."
    }


def cost_transfer(option: RecoveryOption) -> dict:
    """
    Option B -- TRANSFER
    Cost = freight per unit * units + handling fee

    Formula:
      freight = transferable_units * FREIGHT_RATE_PER_UNIT
      handling = HANDLING_FEE_PER_TRANSFER (fixed)
      total = freight + handling
    """
    freight = option.transferable_units * FREIGHT_RATE_PER_UNIT
    handling = HANDLING_FEE_PER_TRANSFER
    total = freight + handling

    return {
        "freight": round(freight, 2),
        "handling": round(handling, 2),
        "total": round(total, 2),
        "note": (
            f"{option.transferable_units:.0f} units × "
            f"${FREIGHT_RATE_PER_UNIT}/unit + "
            f"${HANDLING_FEE_PER_TRANSFER} handling = "
            f"${total:,.2f}"
        )
    }


def cost_expedite(option: RecoveryOption) -> dict:
    """
    Option C -- EXPEDITE
    Cost = (air freight rate - standard freight rate)
         = standard_cost * (expedite_multiplier - 1)

    We only charge the EXTRA cost (delta), not the full freight,
    because we would have paid standard freight anyway.

    Formula:
      extra_cost = STANDARD_FREIGHT_COST * (EXPEDITE_MULTIPLIER - 1)
    """
    extra_cost = STANDARD_FREIGHT_COST * (EXPEDITE_MULTIPLIER - 1)
    total = round(extra_cost, 2)

    return {
        "standard_freight": STANDARD_FREIGHT_COST,
        "expedite_premium": round(extra_cost, 2),
        "total": total,
        "note": (
            f"Air freight premium: "
            f"${STANDARD_FREIGHT_COST} × "
            f"{EXPEDITE_MULTIPLIER - 1:.1f}x extra = "
            f"${total:,.2f} above standard freight"
        )
    }


def cost_alt_supplier(option: RecoveryOption, standard_unit_cost: float, quantity: float) -> dict:
    """
    Option D -- ALT_SUPPLIER
    Cost = price premium + emergency order fee

    Formula:
      unit_premium   = standard_unit_cost * ALT_SUPPLIER_PREMIUM_PCT
      premium_total  = unit_premium * quantity
      emergency_fee  = EMERGENCY_ORDER_FEE (fixed)
      total          = premium_total + emergency_fee
    """
    unit_premium = standard_unit_cost * ALT_SUPPLIER_PREMIUM_PCT
    premium_total = unit_premium * quantity
    emergency_fee = EMERGENCY_ORDER_FEE
    total = round(premium_total + emergency_fee, 2)

    return {
        "unit_price_premium": round(unit_premium, 2),
        "total_premium": round(premium_total, 2),
        "emergency_order_fee": emergency_fee,
        "total": total,
        "note": (
            f"${standard_unit_cost} × {ALT_SUPPLIER_PREMIUM_PCT:.0%} premium × "
            f"{quantity:.0f} units + ${emergency_fee} fee = "
            f"${total:,.2f}"
        )
    }


def cost_of_doing_nothing(days_of_delay: int) -> float:
    """
    Calculate the cost if NO recovery action is taken.
    This is the baseline -- every option must be compared against this.

    Formula:
      delay_cost = days_of_delay * DELAY_COST_PER_DAY
    """
    return round(days_of_delay * DELAY_COST_PER_DAY, 2)


# ---------------------------------------------------------------------------
# MAIN COST CALCULATOR
# Runs the right cost formula for each feasible option
# ---------------------------------------------------------------------------

def calculate_all_costs(
    options: list[RecoveryOption],
    standard_unit_cost: float = 67.50,   # PRT-104 unit cost from parts table
    quantity_needed: float = 145.0       # total units needed by all at-risk orders
) -> list[RecoveryOption]:
    """
    Calculate costs for all FEASIBLE options.
    Infeasible options are skipped (no point costing them).

    Args:
        options:            List from constraints.py (with status set)
        standard_unit_cost: Unit cost of the delayed part (from parts table)
        quantity_needed:    Total units needed by upcoming production orders

    Returns:
        Same list with estimated_cost and cost_breakdown filled in
    """
    for option in options:
        # Only cost feasible options
        if option.status != OptionStatus.FEASIBLE:
            option.cost_breakdown = {"note": "Not costed -- option is infeasible."}
            continue

        if option.option_type == OptionType.USE_STOCK:
            breakdown = cost_use_stock(option)

        elif option.option_type == OptionType.TRANSFER:
            breakdown = cost_transfer(option)

        elif option.option_type == OptionType.EXPEDITE:
            breakdown = cost_expedite(option)

        elif option.option_type == OptionType.ALT_SUPPLIER:
            breakdown = cost_alt_supplier(option, standard_unit_cost, quantity_needed)

        else:
            breakdown = {"total": 0.0, "note": "Unknown option type."}

        option.estimated_cost = breakdown.get("total", 0.0)
        option.cost_breakdown = breakdown

    return options
