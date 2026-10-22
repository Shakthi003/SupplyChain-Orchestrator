"""
tools/audit_tool.py -- Audit Log Tool

Saves human approval/rejection decisions to PostgreSQL.
Every decision made by a human reviewer is permanently recorded here.

Why audit logging matters:
  - Compliance: regulators may ask "why did you choose option X?"
  - Learning: over time, you can see which decisions led to good outcomes
  - Accountability: clear record of who decided what and when
  - Training data: future AI models can learn from past decisions
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.config import DATABASE_URL
from core.models import DecisionLog


def save_decision(
    event_id: str,
    recommended_option_id: str,
    chosen_option_id: str,
    approved: bool,
    reviewer_name: str,
    rationale: str,
    financial_exposure: float = 0.0,
    estimated_cost: float = 0.0
) -> dict:
    """
    Save a human decision to the DecisionLog table.

    Args:
        event_id:              The disruption event (e.g. "EVT-001")
        recommended_option_id: What the system recommended (e.g. "OPT-A")
        chosen_option_id:      What the human actually chose (may differ)
        approved:              True = approved, False = rejected
        reviewer_name:         Who made the decision (e.g. "Sarah Chen")
        rationale:             Why they made this decision (free text)
        financial_exposure:    Total at-risk value ($)
        estimated_cost:        Cost of chosen option ($)

    Returns:
        { "decision_id": "DEC-...", "saved": True, "error": None }
    """
    try:
        db_engine = create_engine(DATABASE_URL)

        with Session(db_engine) as session:
            decision = DecisionLog(
                event_id=event_id,
                recommended_option_id=recommended_option_id,
                chosen_option_id=chosen_option_id,
                approved=approved,
                reviewer_name=reviewer_name,
                rationale=rationale,
                financial_exposure=financial_exposure,
                estimated_cost=estimated_cost,
                decided_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            session.add(decision)
            session.commit()
            session.refresh(decision)

            return {
                "decision_id": decision.id,
                "event_id":    event_id,
                "approved":    approved,
                "saved":       True,
                "error":       None
            }

    except Exception as e:
        return {
            "decision_id": None,
            "event_id":    event_id,
            "approved":    approved,
            "saved":       False,
            "error":       str(e)
        }


def get_past_decisions(event_id: str = None, limit: int = 10) -> list[dict]:
    """
    Retrieve past decisions from the audit log.
    Used by the agent to show decision history.
    """
    try:
        db_engine = create_engine(DATABASE_URL)

        with Session(db_engine) as session:
            query = session.query(DecisionLog)
            if event_id:
                query = query.filter(DecisionLog.event_id == event_id)
            decisions = query.order_by(DecisionLog.decided_at.desc()).limit(limit).all()

            return [
                {
                    "decision_id":      d.id,
                    "event_id":         d.event_id,
                    "recommended":      d.recommended_option_id,
                    "chosen":           d.chosen_option_id,
                    "approved":         d.approved,
                    "reviewer":         d.reviewer_name,
                    "rationale":        d.rationale,
                    "exposure":         d.financial_exposure,
                    "cost":             d.estimated_cost,
                    "decided_at":       d.decided_at.strftime("%Y-%m-%d %H:%M") if d.decided_at else None
                }
                for d in decisions
            ]
    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    # Test: save a sample decision
    result = save_decision(
        event_id="EVT-001",
        recommended_option_id="OPT-A",
        chosen_option_id="OPT-A",
        approved=True,
        reviewer_name="Test User",
        rationale="Testing audit tool -- stock coverage is sufficient.",
        financial_exposure=20300.0,
        estimated_cost=0.0
    )
    print(f"\nSaved decision: {result}")

    # Retrieve it back
    past = get_past_decisions(event_id="EVT-001")
    print(f"Past decisions for EVT-001: {len(past)}")
    for d in past:
        print(f"  {d}")
