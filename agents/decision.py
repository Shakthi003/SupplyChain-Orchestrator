"""
agents/decision.py -- Human Decision (Approval Gate)

The analysis pipeline (workflow.py) ends after the AI explanation.
The human decision is a SEPARATE step, so it can be driven by a terminal,
an API call, or a UI button -- no input() is hidden inside the workflow.

Rules enforced here (the approval gate must be explicit):
  - approved must be a real bool (True / False). Nothing is approved by default.
  - reviewer_name and rationale are required.
  - chosen_option_id must be one of the feasible options from the analysis.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.audit_tool import save_decision


class DecisionError(ValueError):
    """Raised when a submitted decision is invalid."""


def submit_decision(
    analysis: dict,
    approved: bool,
    reviewer_name: str,
    rationale: str,
    chosen_option_id: str | None = None,
) -> dict:
    """
    Validate a human decision against the analysis and save it to the audit log.

    Args:
        analysis:         The final state returned by run_analysis()
        approved:         True = approve, False = reject
        reviewer_name:    Who is deciding (required)
        rationale:        Why (required)
        chosen_option_id: Which option; defaults to the system recommendation

    Returns:
        { "decision_id": int, "event_id": str, "approved": bool,
          "chosen_option_id": str, "saved": True }

    Raises:
        DecisionError: if the input is invalid
        RuntimeError:  if the audit log could not be written
    """
    if not isinstance(approved, bool):
        raise DecisionError("approved must be true or false.")
    if not (reviewer_name or "").strip():
        raise DecisionError("reviewer_name is required.")
    if not (rationale or "").strip():
        raise DecisionError("rationale is required.")

    planning = analysis.get("planning_result") or {}
    options = planning.get("options", [])
    if not options:
        raise DecisionError("Analysis has no recovery options to decide on.")

    recommended = planning.get("recommended_option_id") or ""
    chosen = (chosen_option_id or recommended).strip().upper()

    feasible = {o["option_id"]: o for o in options if o["status"] == "feasible"}
    if chosen not in feasible:
        raise DecisionError(
            f"Option '{chosen}' is not a feasible option. "
            f"Choose one of: {sorted(feasible)}"
        )

    impact = analysis.get("impact_result") or {}
    result = save_decision(
        event_id=analysis["event_id"],
        recommended_option_id=recommended,
        chosen_option_id=chosen,
        approved=approved,
        reviewer_name=reviewer_name.strip(),
        rationale=rationale.strip(),
        financial_exposure=impact.get("total_exposure", 0.0),
        estimated_cost=feasible[chosen]["cost"],
    )

    if result.get("error"):
        raise RuntimeError(f"Failed to save decision: {result['error']}")

    return {
        "decision_id": result["decision_id"],
        "event_id": analysis["event_id"],
        "approved": approved,
        "chosen_option_id": chosen,
        "saved": True,
    }
