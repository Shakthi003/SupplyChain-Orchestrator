"""
scripts/load_graph.py -- Run the graph loader and then test all queries.

How to run:
  uv run python scripts/load_graph.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.loader import load_graph
from graph.queries import (
    get_impact_chain, get_supplier_risk_ranking,
    get_dependency_concentration, check_spare_stock,
    print_impact_chain, print_risk_ranking,
    print_dependency_concentration, print_spare_stock
)

if __name__ == "__main__":

    # Step 1: Load PostgreSQL data into Neo4j
    load_graph(clear_first=True)

    sep = "=" * 60

    # Step 2: Run Query 1 -- Impact chain from SUP-005
    print(f"\n{sep}")
    print("  QUERY 1: Full Impact Chain from SUP-005")
    print(sep)
    rows = get_impact_chain("SUP-005")
    print_impact_chain(rows)

    # Step 3: Run Query 2 -- Supplier risk ranking
    print(f"\n{sep}")
    print("  QUERY 2: Supplier Risk Ranking")
    print(sep)
    rows = get_supplier_risk_ranking()
    print_risk_ranking(rows)

    # Step 4: Run Query 3 -- Dependency concentration
    print(f"\n{sep}")
    print("  QUERY 3: Dependency Concentration (Single Points of Failure)")
    print(sep)
    rows = get_dependency_concentration()
    print_dependency_concentration(rows)

    # Step 5: Run Query 4 -- Spare stock for PRT-104
    print(f"\n{sep}")
    print("  QUERY 4: Spare Stock for PRT-104 (excluding WH-01)")
    print(sep)
    rows = check_spare_stock("PRT-104", exclude_warehouse_id="WH-01")
    print_spare_stock(rows, "PRT-104")

    print(f"\n{sep}")
    print("  ALL GRAPH QUERIES COMPLETE")
    print(sep)
