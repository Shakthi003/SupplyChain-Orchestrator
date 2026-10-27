"""
api/schemas.py -- Request/response models for the API.
Only the request body needs a schema; responses reuse the tool/agent dicts.
"""

from typing import Optional
from pydantic import BaseModel, Field


class DecisionRequest(BaseModel):
    approved: bool = Field(..., description="True = approve, False = reject. No default.")
    reviewer_name: str = Field(..., min_length=1, max_length=100)
    rationale: str = Field(..., min_length=1, max_length=2000)
    chosen_option_id: Optional[str] = Field(
        None, max_length=20, description="Defaults to the system-recommended option."
    )


class CreateEventRequest(BaseModel):
    shipment_id: str = Field(..., min_length=1, max_length=20,
                             description="The shipment that is delayed, e.g. SHP-441")
    delay_days: int = Field(..., ge=1, le=365,
                            description="How many days late (must be at least 1)")
    delay_reason: str = Field(..., min_length=1, max_length=500,
                              description="Supplier's stated reason for the delay")
    severity: Optional[str] = Field(
        "high",
        description="low | medium | high | critical"
    )
