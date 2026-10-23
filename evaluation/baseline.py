"""
evaluation/baseline.py -- the "simple baseline" the system is compared against.

Naive rule a spreadsheet user might apply:
  "A late shipment means a shortage. Flag every open production order for every
   product that uses the part, and every customer order behind them."

It ignores stock on hand, other shipments and order timing -- which is exactly
what the real engine adds.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.models import CustomerOrder, ProductionOrder, ProductionStatus


def naive_baseline(affected_product_ids: list[str]) -> dict:
    with Session(create_engine(DATABASE_URL)) as s:
        prods = (
            s.query(ProductionOrder)
            .filter(ProductionOrder.product_part_id.in_(affected_product_ids),
                    ProductionOrder.status.in_([ProductionStatus.PLANNED, ProductionStatus.IN_PROGRESS]))
            .all()
        )
        prod_ids = [p.id for p in prods]
        custs = s.query(CustomerOrder).filter(CustomerOrder.production_order_id.in_(prod_ids)).all() if prod_ids else []
        return {
            "has_shortage": True,
            "production_orders": [p.id for p in prods],
            "customer_orders": [c.id for c in custs],
            "exposure": sum(c.order_value or 0 for c in custs),
        }
