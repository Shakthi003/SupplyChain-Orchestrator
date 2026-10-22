"""
tools/graph_tool.py -- Graph Query Tool (Wrapper for Stage 4)

Wraps graph/queries.py for use by the AI agent.
Returns the full impact chain from supplier to customer as readable text.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.queries import (
    get_impact_chain,
    get_supplier_risk_ranking,
    check_spare_stock
)


def get_impact_chain_tool(supplier_id: str, part_id: str) -> dict:
    """
    Get the full impact chain from a supplier through to affected customer orders.

    Returns:
        {
          "supplier_id": "SUP-005",
          "part_id":     "PRT-104",
          "chain_text":  "SUP-005 (Apex Hydraulics) -> PRT-104 -> PRD-306 -> CO-506 ($20,300)",
          "paths":       [ { ... } ],
          "error":       None
        }
    """
    try:
        results = get_impact_chain(supplier_id)

        if not results:
            return {
                "supplier_id": supplier_id,
                "part_id":     part_id,
                "chain_text":  f"No impact chain found for {supplier_id}.",
                "paths":       [],
                "error":       None
            }

        # Build readable chain summary
        lines = []
        total_exposure = 0.0
        for r in results:
            sup_name  = r.get("supplier_name", supplier_id)
            part_name = r.get("part_name", part_id)
            prod_id   = r.get("production_order_id", "?")
            co_id     = r.get("customer_order_id", "?")
            customer  = r.get("customer_name", "?")
            value     = r.get("order_value", 0) or 0
            total_exposure += value
            lines.append(
                f"  {sup_name} ({supplier_id})"
                f" -> {part_name} ({part_id})"
                f" -> {prod_id}"
                f" -> {co_id} ({customer}, ${value:,.0f})"
            )

        chain_text = (
            f"Impact chain for {supplier_id}:\n"
            + "\n".join(lines)
            + f"\n  Total exposure: ${total_exposure:,.0f}"
        )

        return {
            "supplier_id":    supplier_id,
            "part_id":        part_id,
            "chain_text":     chain_text,
            "total_exposure": total_exposure,
            "paths":          results,
            "error":          None
        }

    except Exception as e:
        return {
            "supplier_id": supplier_id,
            "part_id":     part_id,
            "chain_text":  f"Graph query failed: {str(e)}",
            "paths":       [],
            "error":       str(e)
        }


def get_spare_stock_tool(part_id: str) -> dict:
    """
    Check if any warehouse has spare stock of a part for transfer.

    Returns:
        {
          "part_id":     "PRT-104",
          "spare_text":  "WH-02 (Dallas) has 80 units available for transfer.",
          "warehouses":  [ { "warehouse_id": "WH-02", "available": 80 } ],
          "error":       None
        }
    """
    try:
        results = check_spare_stock(part_id)

        if not results:
            return {
                "part_id":    part_id,
                "spare_text": f"No spare stock found for {part_id} in any warehouse.",
                "warehouses": [],
                "error":      None
            }

        lines = []
        for r in results:
            wh_id   = r.get("warehouse_id", "?")
            wh_name = r.get("warehouse_name", wh_id)
            avail   = r.get("available", 0)
            lines.append(f"  {wh_name} ({wh_id}): {avail:.0f} units available")

        spare_text = f"Spare stock for {part_id}:\n" + "\n".join(lines)

        return {
            "part_id":    part_id,
            "spare_text": spare_text,
            "warehouses": results,
            "error":      None
        }

    except Exception as e:
        return {
            "part_id":    part_id,
            "spare_text": f"Graph query failed: {str(e)}",
            "warehouses": [],
            "error":      str(e)
        }


if __name__ == "__main__":
    import json
    print("\n--- Impact Chain ---")
    r1 = get_impact_chain_tool("SUP-005", "PRT-104")
    print(r1["chain_text"])

    print("\n--- Spare Stock ---")
    r2 = get_spare_stock_tool("PRT-104")
    print(r2["spare_text"])
