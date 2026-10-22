"""
agents/runner.py -- Agent Entry Point

Two separate steps:
  run_analysis(event_id)  -> runs the pipeline (steps 1-6), NO user input.
                             Used by the terminal CLI below AND by the API.
  submit_decision(...)    -> in agents/decision.py, saves the human decision.

How to run in the terminal:
  uv run python agents/runner.py
  uv run python agents/runner.py --event EVT-001

Prerequisites:
  - PostgreSQL running with generate_data.py already run
  - Neo4j running with load_graph.py already run (optional: skipped if offline)
  - ChromaDB loaded with embedder.py already run
  - .env file has GEMINI_API_KEY set
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

from agents.workflow import workflow_app
from agents.decision import submit_decision, DecisionError


def run_analysis(event_id: str = "EVT-001") -> dict:
    """
    Run the analysis pipeline for a disruption event. Never asks for input.

    Returns the final state dict. Check final_state["event_valid"]:
    False means the event was not found / already resolved
    (see final_state["error"]).
    """
    initial_state = {
        "event_id":          event_id,
        "event_valid":       False,
        "event_description": "",
        "part_id":           "",
        "supplier_id":       "",
        "delay_days":        0,
        "impact_result":     None,
        "planning_result":   None,
        "graph_result":      None,
        "documents_result":  None,
        "explanation":       "",
        "error":             None,
    }
    return workflow_app.invoke(initial_state)


def _ask(prompt: str) -> str:
    print(prompt, end="", flush=True)
    return input().strip()


def run_cli(event_id: str) -> None:
    """Terminal flow: analyze, show the result, ask the human, save."""
    print("\n" + "#" * 65)
    print("#  SupplyChain Orchestrator -- AI Agent")
    print("#" * 65)

    state = run_analysis(event_id)

    if not state.get("event_valid"):
        print(f"\n  Workflow stopped early: {state.get('error', 'Invalid event')}")
        return

    planning = state.get("planning_result") or {}
    options = planning.get("options", [])
    recommended = planning.get("recommended_option_id")

    print("\n" + "=" * 65)
    print("  HUMAN APPROVAL REQUIRED")
    print("=" * 65)
    print("\n  --- AI ANALYSIS AND RECOMMENDATION ---\n")
    for line in state.get("explanation", "").split("\n"):
        print(f"  {line}")

    print("\n  --- RECOVERY OPTIONS ---")
    for o in options:
        tag = "OK" if o["status"] == "feasible" else "NO"
        print(f"  [{tag}] Rank {o['rank']} | {o['option_id']} | {o['title']} "
              f"| score {o['score']:.1f} | ${o['cost']:,.2f}")
    print(f"\n  System recommendation: {recommended}")

    feasible_ids = [o["option_id"] for o in options if o["status"] == "feasible"]
    print(f"  Feasible options     : {feasible_ids}")

    reviewer = _ask("\n  Your name (reviewer): ")
    chosen = _ask("  Option to choose (Enter = recommendation): ").upper() or recommended

    approval = ""
    while approval not in ("y", "n"):
        approval = _ask("  Approve? (y/n): ").lower()

    rationale = _ask("  Reason for your decision: ")

    try:
        result = submit_decision(
            analysis=state,
            approved=(approval == "y"),
            reviewer_name=reviewer,
            rationale=rationale,
            chosen_option_id=chosen,
        )
    except DecisionError as e:
        print(f"\n  [REJECTED INPUT] {e}")
        return

    print(f"\n  [OK] Decision saved. ID={result['decision_id']} "
          f"option={result['chosen_option_id']} "
          f"approved={'YES' if result['approved'] else 'NO'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SupplyChain Orchestrator -- AI Agent Runner")
    parser.add_argument("--event", type=str, default="EVT-001",
                        help="Disruption event ID to process (default: EVT-001)")
    args = parser.parse_args()
    run_cli(args.event)
