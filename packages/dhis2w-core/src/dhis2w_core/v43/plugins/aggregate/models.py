"""Plugin-internal view-models for the aggregate plugin."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FollowUpResult(BaseModel):
    """Outcome of a follow-up flag update — DHIS2's follow-up endpoint returns an empty 200."""

    model_config = ConfigDict(frozen=True)

    count: int
    followup: bool
