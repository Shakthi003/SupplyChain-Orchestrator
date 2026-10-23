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
