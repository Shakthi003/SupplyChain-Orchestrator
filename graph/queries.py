"""
graph/queries.py -- Cypher Query Library

Contains all Neo4j graph queries as Python functions.
Each function sends a Cypher query to Neo4j and returns results.

These queries answer questions that PostgreSQL struggles with:
  - Which customers are affected if a supplier is delayed?
  - Which supplier is the biggest single point of failure?
  - Is there spare stock in another warehouse?
  - What is the full impact chain for a disruption?
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.schema import get_driver, NodeLabel, RelType


# ---------------------------------------------------------------------------
# QUERY 1 -- Full Impact Chain
# "Starting from a supplier, find every affected customer"
#
# Path it follows:
#   Supplier -[SUPPLIES]-> Part -[REQUIRED_BY]-> FinishedGood
#   FinishedGood <-[BUILDS]- ProductionOrder <-[WAITING_ON]- CustomerOrder
#
# This answers: "If SUP-005 delays, who are the affected customers?"
# ---------------------------------------------------------------------------

def get_impact_chain(supplier_id: str) -> list[dict]:
    """
    Trace the full impact chain from a supplier to affected customers.

    Args:
        supplier_id: e.g. "SUP-005"

    Returns:
        List of dicts with supplier, part, product, production order,
        customer order details

    Cypher path drawn out:
      (Supplier) -SUPPLIES-> (Part) -REQUIRED_BY-> (FinishedGood)
                 <-BUILDS- (ProductionOrder) <-WAITING_ON- (CustomerOrder)
    """
    driver = get_driver()

    query = f"""
        MATCH (s:{NodeLabel.SUPPLIER} {{id: $supplier_id}})
              -[:{RelType.SUPPLIES}]->
              (part:{NodeLabel.PART})
              -[req:{RelType.REQUIRED_BY}]->
              (product:{NodeLabel.PART})
              <-[:{RelType.BUILDS}]-
              (prd:{NodeLabel.PRODUCTION_ORDER})
              <-[:{RelType.WAITING_ON}]-
              (co:{NodeLabel.CUSTOMER_ORDER})
        RETURN
            s.id            AS supplier_id,
            s.name          AS supplier_name,
            part.id         AS part_id,
            part.name       AS part_name,
            req.quantity_required AS qty_required,
            product.id      AS product_id,
            product.name    AS product_name,
            prd.id          AS production_order_id,
            prd.status      AS production_status,
            co.id           AS customer_order_id,
            co.customer_name AS customer_name,
            co.order_value  AS order_value,
            co.promised_delivery_date AS promised_date
        ORDER BY co.order_value DESC
    """

    with driver.session() as session:
        result = session.run(query, {"supplier_id": supplier_id})
        rows = [dict(record) for record in result]

    driver.close()
    return rows


# ---------------------------------------------------------------------------
# QUERY 2 -- Supplier Risk Ranking
# "Which suppliers are most risky?"
#
# Risk = low reliability score + supplies many critical parts
# We count how many customer orders depend on each supplier
# and combine with reliability score to get a risk ranking.
# ---------------------------------------------------------------------------

def get_supplier_risk_ranking() -> list[dict]:
    """
    Rank all suppliers by risk level.

    Risk factors:
      - Low reliability score (historical on-time rate)
      - Many customer orders depend on this supplier
      - Long lead time (more time for things to go wrong)

    Returns:
        List of suppliers ranked by risk (highest risk first)
    """
    driver = get_driver()

    query = f"""
        MATCH (s:{NodeLabel.SUPPLIER})
              -[:{RelType.SUPPLIES}]->
              (part:{NodeLabel.PART})
              -[:{RelType.REQUIRED_BY}]->
              (product:{NodeLabel.PART})
              <-[:{RelType.BUILDS}]-
              (prd:{NodeLabel.PRODUCTION_ORDER})
              <-[:{RelType.WAITING_ON}]-
              (co:{NodeLabel.CUSTOMER_ORDER})
        WITH
            s.id               AS supplier_id,
            s.name             AS supplier_name,
            s.reliability_score AS reliability_score,
            s.lead_time_days   AS lead_time_days,
            s.country          AS country,
            COUNT(DISTINCT co) AS customer_orders_at_risk,
            COUNT(DISTINCT part) AS parts_supplied,
            SUM(co.order_value)  AS total_value_at_risk

        // Risk score formula:
        // Lower reliability = higher risk
        // More customer orders affected = higher risk
        // Combined into a 0-100 risk score
        WITH *,
            ROUND(
                ((1 - reliability_score) * 50) +
                (customer_orders_at_risk * 10)
            , 1) AS risk_score

        RETURN
            supplier_id,
            supplier_name,
            reliability_score,
            lead_time_days,
            country,
            parts_supplied,
            customer_orders_at_risk,
            total_value_at_risk,
            risk_score,
            CASE
                WHEN risk_score >= 30 THEN 'HIGH'
                WHEN risk_score >= 15 THEN 'MEDIUM'
                ELSE 'LOW'
            END AS risk_level
        ORDER BY risk_score DESC
    """

    with driver.session() as session:
        result = session.run(query)
        rows = [dict(record) for record in result]

    driver.close()
    return rows


# ---------------------------------------------------------------------------
# QUERY 3 -- Dependency Concentration
# "Which single supplier failure would cause the most damage?"
#
# Shows: for each supplier, how many UNIQUE customers ultimately
# depend on them (directly or indirectly through the supply chain)
# ---------------------------------------------------------------------------

def get_dependency_concentration() -> list[dict]:
    """
    Find which suppliers are single points of failure.

    A supplier is a single point of failure if:
      - Many products depend on parts it supplies
      - No alternative supplier exists for those parts

    Returns:
        List of suppliers with their downstream customer count
        and total financial exposure if they fail
    """
    driver = get_driver()

    query = f"""
        MATCH (s:{NodeLabel.SUPPLIER})
              -[:{RelType.SUPPLIES}]->
              (part:{NodeLabel.PART})
        WITH s, COLLECT(DISTINCT part.name) AS parts_supplied

        OPTIONAL MATCH (s)
              -[:{RelType.SUPPLIES}]->
              (part2:{NodeLabel.PART})
              -[:{RelType.REQUIRED_BY}]->
              (product:{NodeLabel.PART})
              <-[:{RelType.BUILDS}]-
              (prd:{NodeLabel.PRODUCTION_ORDER})
              <-[:{RelType.WAITING_ON}]-
              (co:{NodeLabel.CUSTOMER_ORDER})

        RETURN
            s.id                AS supplier_id,
            s.name              AS supplier_name,
            s.reliability_score AS reliability,
            s.country           AS country,
            parts_supplied,
            COUNT(DISTINCT co)  AS downstream_customers,
            COALESCE(SUM(co.order_value), 0) AS financial_exposure
        ORDER BY downstream_customers DESC, financial_exposure DESC
    """

    with driver.session() as session:
        result = session.run(query)
        rows = [dict(record) for record in result]

    driver.close()
    return rows


# ---------------------------------------------------------------------------
# QUERY 4 -- Spare Stock Check
# "Is there spare stock of a delayed part in another warehouse?"
#
# This supports the TRANSFER recovery option:
# If WH-01 has a shortage of PRT-104 but WH-02 has spare stock,
# we can transfer stock from WH-02 to WH-01 as a recovery action.
# ---------------------------------------------------------------------------

def check_spare_stock(part_id: str, exclude_warehouse_id: str = None) -> list[dict]:
    """
    Find warehouses that have available stock of a given part.
    Used to evaluate the "transfer stock" recovery option.

    Args:
        part_id:              The part to check (e.g. "PRT-104")
        exclude_warehouse_id: Skip this warehouse (it's the one with shortage)

    Returns:
        List of warehouses with available stock, sorted by availability
    """
    driver = get_driver()

    if exclude_warehouse_id:
        query = f"""
            MATCH (p:{NodeLabel.PART} {{id: $part_id}})
                  -[r:{RelType.STOCKED_IN}]->
                  (w:{NodeLabel.WAREHOUSE})
            WHERE w.id <> $exclude_wh
              AND r.available > 0
            RETURN
                w.id       AS warehouse_id,
                w.name     AS warehouse_name,
                w.location AS location,
                r.on_hand  AS on_hand,
                r.reserved AS reserved,
                r.available AS available
            ORDER BY r.available DESC
        """
        params = {"part_id": part_id, "exclude_wh": exclude_warehouse_id}
    else:
        query = f"""
            MATCH (p:{NodeLabel.PART} {{id: $part_id}})
                  -[r:{RelType.STOCKED_IN}]->
                  (w:{NodeLabel.WAREHOUSE})
            WHERE r.available > 0
            RETURN
                w.id       AS warehouse_id,
                w.name     AS warehouse_name,
                w.location AS location,
                r.on_hand  AS on_hand,
                r.reserved AS reserved,
                r.available AS available
            ORDER BY r.available DESC
        """
        params = {"part_id": part_id}

    with driver.session() as session:
        result = session.run(query, params)
        rows = [dict(record) for record in result]

    driver.close()
    return rows


# ---------------------------------------------------------------------------
# PRETTY PRINTER -- formats query results for terminal output
# ---------------------------------------------------------------------------

def print_impact_chain(rows: list[dict]):
    if not rows:
        print("  No impact chain found.")
        return
    print(f"\n  {'SUPPLIER':<15} {'PART':<12} {'PRODUCT':<12} {'PROD ORDER':<12} {'CUSTOMER':<25} {'VALUE':>10}")
    print("  " + "-" * 90)
    for r in rows:
        print(f"  {r['supplier_id']:<15} {r['part_id']:<12} {r['product_id']:<12} "
              f"{r['production_order_id']:<12} {r['customer_name']:<25} ${r['order_value']:>9,.0f}")


def print_risk_ranking(rows: list[dict]):
    if not rows:
        print("  No suppliers found.")
        return
    print(f"\n  {'SUPPLIER':<25} {'COUNTRY':<10} {'RELIABILITY':>12} {'CUSTOMERS AT RISK':>18} {'RISK SCORE':>11} {'LEVEL':<8}")
    print("  " + "-" * 90)
    for r in rows:
        print(f"  {r['supplier_name']:<25} {r['country']:<10} "
              f"{r['reliability_score']:>12.2f} {r['customer_orders_at_risk']:>18} "
              f"{r['risk_score']:>11.1f} {r['risk_level']:<8}")


def print_dependency_concentration(rows: list[dict]):
    if not rows:
        print("  No data found.")
        return
    print(f"\n  {'SUPPLIER':<25} {'COUNTRY':<10} {'RELIABILITY':>12} {'DOWNSTREAM CUSTOMERS':>21} {'EXPOSURE':>12}")
    print("  " + "-" * 85)
    for r in rows:
        print(f"  {r['supplier_name']:<25} {r['country']:<10} "
              f"{r['reliability']:>12.2f} {r['downstream_customers']:>21} "
              f"${r['financial_exposure']:>11,.0f}")


def print_spare_stock(rows: list[dict], part_id: str):
    if not rows:
        print(f"  No spare stock found for {part_id} in other warehouses.")
        return
    print(f"\n  Spare stock for {part_id}:")
    print(f"  {'WAREHOUSE':<30} {'LOCATION':<20} {'ON HAND':>9} {'RESERVED':>9} {'AVAILABLE':>10}")
    print("  " + "-" * 82)
    for r in rows:
        print(f"  {r['warehouse_name']:<30} {r['location']:<20} "
              f"{r['on_hand']:>9.0f} {r['reserved']:>9.0f} {r['available']:>10.0f}")
