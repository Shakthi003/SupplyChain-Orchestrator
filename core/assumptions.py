"""
core/assumptions.py -- the rules and rates the engines assume.

These are shown in every result (UI + AI briefing) so a reviewer can see
what the numbers rest on. Rates are read from the code that uses them so
this list cannot drift from the calculations.
"""

from core.optimization.costs import (
    DELAY_COST_PER_DAY, FREIGHT_RATE_PER_UNIT, HANDLING_FEE_PER_TRANSFER,
    ALT_SUPPLIER_PREMIUM_PCT, EMERGENCY_ORDER_FEE,
)

ASSUMPTIONS = [
    "Stock is allocated to production orders first-come-first-served, in order of planned start date "
    "(order value or penalty is not considered).",
    "Each production order uses its component evenly between its planned start and end dates.",
    "Inbound shipments count as stock once their revised ETA has passed.",
    "Warehouse-to-warehouse transfers are assumed to take 2 days.",
    "Expediting a shipment is assumed to save 2 days.",
    f"Cost of doing nothing = ${DELAY_COST_PER_DAY:,.0f} per day of delay.",
    f"Transfer cost = ${FREIGHT_RATE_PER_UNIT:.2f} per unit + ${HANDLING_FEE_PER_TRANSFER:,.0f} handling.",
    f"Alternate-supplier cost = {ALT_SUPPLIER_PREMIUM_PCT:.0%} price premium + ${EMERGENCY_ORDER_FEE:,.0f} rush fee.",
    "All data is synthetic.",
]
