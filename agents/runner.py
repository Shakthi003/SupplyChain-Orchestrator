"""
agents/runner.py -- Agent Entry Point

The start button. Run this file to trigger the full agent workflow.

How to run:
  uv run python agents/runner.py
  uv run python agents/runner.py --event EVT-001

What happens:
  1. Loads EVT-001 from PostgreSQL
  2. Runs full impact analysis (Stage 3)
  3. Runs full recovery planning (Stage 5)
  4. Queries Neo4j impact chain (Stage 4)
  5. Searches ChromaDB for relevant documents (RAG)
  6. Calls Gemini to generate plain English explanation
  7. Prints everything and waits for YOUR approval
  8. Saves your decision to the audit log (PostgreSQL)

Prerequisites:
  - PostgreSQL running with generate_data.py already run
  - Neo4j running with load_graph.py already run
  - ChromaDB loaded with embedder.py already run
  - .env file has GEMINI_API_KEY set
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from datetime import datetime

from agents.workflow import workflow_app


def run_agent(event_id: str = "EVT-001"):
    """
    Run the full agent workflow for a given disruption event.

    Args:
        event_id: The disruption event to process (default: EVT-001)
    """
    print("\n" + "#" * 65)
    print("#  SupplyChain Orchestrator -- AI Agent")
    print("#  Explainable Agentic Supply Chain Risk and Recovery")
    print("#" * 65)
    print(f"\n  Starting workflow for event: {event_id}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n  Pipeline:")
    print(f"    1. Validate event")
    print(f"    2. Run impact analysis   (Stage 3 engine)")
    print(f"    3. Run recovery planning (Stage 5 planner)")
    print(f"    4. Fetch impact chain    (Stage 4 Neo4j)")
    print(f"    5. Fetch documents       (ChromaDB RAG)")
    print(f"    6. Generate explanation  (Gemini AI)")
    print(f"    7. Human approval gate   (YOU decide)")
    print(f"    8. Save decision         (Audit log)")

    # Initial state -- only event_id is needed to start
    initial_state = {
        "event_id":           event_id,
        "event_valid":        False,
        "event_description":  "",
        "part_id":            "",
        "supplier_id":        "",
        "delay_days":         0,
        "impact_result":      None,
        "planning_result":    None,
        "graph_result":       None,
        "documents_result":   None,
        "explanation":        "",
        "approved":           None,
        "reviewer_name":      "",
        "rationale":          "",
        "chosen_option_id":   "",
        "decision_saved":     False,
        "decision_id":        None,
        "error":              None
    }

    # Run the workflow
    # LangGraph executes all nodes in order, passing state between them
    try:
        final_state = workflow_app.invoke(initial_state)
    except KeyboardInterrupt:
        print("\n\n  [CANCELLED] Workflow interrupted by user.")
        return
    except Exception as e:
        print(f"\n  [ERROR] Workflow failed: {e}")
        raise

    # Final summary
    print("\n" + "#" * 65)
    print("#  WORKFLOW COMPLETE")
    print("#" * 65)

    if not final_state.get("event_valid"):
        print(f"\n  Workflow stopped early: {final_state.get('error', 'Invalid event')}")
        return

    print(f"\n  Event            : {event_id}")
    print(f"  Part affected    : {final_state.get('part_id', 'N/A')}")
    print(f"  Supplier         : {final_state.get('supplier_id', 'N/A')}")

    impact = final_state.get("impact_result", {})
    if impact:
        print(f"  Financial exposure: ${impact.get('total_exposure', 0):,.2f}")

    print(f"\n  Decision         : {'APPROVED' if final_state.get('approved') else 'REJECTED'}")
    print(f"  Chosen option    : {final_state.get('chosen_option_id', 'N/A')}")
    print(f"  Reviewer         : {final_state.get('reviewer_name', 'N/A')}")
    print(f"  Decision ID      : {final_state.get('decision_id', 'N/A')}")
    print(f"  Saved to DB      : {'YES' if final_state.get('decision_saved') else 'NO'}")

    if final_state.get("error"):
        print(f"\n  Warning: {final_state['error']}")

    print("\n" + "#" * 65 + "\n")

    return final_state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SupplyChain Orchestrator -- AI Agent Runner"
    )
    parser.add_argument(
        "--event",
        type=str,
        default="EVT-001",
        help="Disruption event ID to process (default: EVT-001)"
    )
    args = parser.parse_args()

    run_agent(args.event)
