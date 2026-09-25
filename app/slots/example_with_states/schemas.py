"""Pydantic v2 schemas for the Approval Request slot.

Schema split:
  - ApprovalRequestCreate — payload for POST /approval-requests
  - ApprovalRequestUpdate — payload for PATCH /approval-requests/{id}
                             (mutates title/body; ONLY allowed in DRAFT state;
                              the state machine guards this — see service.py)
  - ApprovalRequestRead   — response shape
  - TransitionRequest     — payload for POST /approval-requests/{id}/transitions
                             carries target_status + optional decision_note
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.slots.example_with_states.models import ApprovalStatus


class ApprovalRequestCreate(BaseModel):
    """Initial creation payload — always lands the row in DRAFT status."""

    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(default="", max_length=8192)


class ApprovalRequestUpdate(BaseModel):
    """Mutate title/body of a DRAFT request. Other states reject via 409."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=8192)


class TransitionRequest(BaseModel):
    """Move the request to a new status.

    target_status MUST be one of the values reachable from the current
    status per the ALLOWED_TRANSITIONS table in service.py. Otherwise
    the service raises IllegalTransition and the route returns 409.

    decision_note is required when target_status is APPROVED or REJECTED
    (it gets stamped onto the row alongside decided_at + approver_id).
    """

    model_config = ConfigDict(extra="forbid")

    target_status: ApprovalStatus
    decision_note: str | None = Field(default=None, max_length=2048)


class ApprovalRequestRead(BaseModel):
    """Response shape — mirrors the model + lifecycle metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: int
    requester_id: int
    title: str
    body: str
    status: ApprovalStatus
    submitted_at: datetime | None
    decided_at: datetime | None
    approver_id: int | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime
