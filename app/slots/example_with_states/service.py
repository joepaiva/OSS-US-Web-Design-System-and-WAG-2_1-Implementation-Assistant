"""Approval Request service layer — the canonical state-machine reference.

What slot authors should mirror EXACTLY for new state-machine slots:

  1. ALLOWED_TRANSITIONS — a frozen dict mapping {current_status: {valid_next_statuses}}.
     Terminal states map to empty sets. This is the SINGLE SOURCE OF TRUTH for
     the state machine. The transition() function below consults it before
     applying any change.

  2. IllegalTransition exception — distinct from generic ValueError. Routes
     map it to HTTP 409 Conflict (NOT 422 — the payload was structurally
     valid, the business rule rejected it).

  3. transition() function — handles ALL state changes. Mutating the
     status column directly via update_*() functions is a slot anti-pattern;
     all state changes go through transition() so the audit log and
     transition-timestamps stay consistent.

  4. Side-effect stamping — submitted_at on draft→submitted; decided_at +
     approver_id + decision_note on submitted→approved/rejected. The chassis
     @audited decorator covers the audit log entry; transition-timestamps
     are slot-domain bookkeeping.

  5. Terminal-state guards — APPROVED and REJECTED have no outbound transitions.
     The state machine catches this; downstream code (e.g. update_approval_request)
     also rejects mutations on terminal rows for an extra layer of safety.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.auth.models import User
from app.slots.example_with_states.models import ApprovalRequest, ApprovalStatus
from app.slots.example_with_states.schemas import (
    ApprovalRequestCreate,
    ApprovalRequestUpdate,
    TransitionRequest,
)

# ─────────────────────────────────────────────────────────────────────────
# State machine — the single source of truth
# ─────────────────────────────────────────────────────────────────────────

# ALLOWED_TRANSITIONS maps current_status → set of valid next statuses.
# Terminal states map to an empty frozenset (no outbound transitions).
# Slot authors writing new state machines should mirror this exact shape.
ALLOWED_TRANSITIONS: Final[dict[ApprovalStatus, frozenset[ApprovalStatus]]] = {
    ApprovalStatus.DRAFT: frozenset({ApprovalStatus.SUBMITTED}),
    ApprovalStatus.SUBMITTED: frozenset(
        {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}
    ),
    ApprovalStatus.APPROVED: frozenset(),  # terminal
    ApprovalStatus.REJECTED: frozenset(),  # terminal
}


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class ApprovalNotFound(Exception):
    """Raised by reads when the id is missing or out-of-org."""


class IllegalTransition(Exception):
    """Raised by transition() when the proposed target is unreachable
    from the current status. Routes catch this and return HTTP 409.

    Carries the rejected (current → target) pair so the response can
    surface a clear error message.
    """

    def __init__(
        self,
        current: ApprovalStatus,
        target: ApprovalStatus,
        message: str | None = None,
    ) -> None:
        self.current = current
        self.target = target
        self.message = message or (
            f"Cannot transition from {current.value} to {target.value}; "
            f"allowed next statuses: {sorted(s.value for s in ALLOWED_TRANSITIONS[current])}"
        )
        super().__init__(self.message)


class DecisionNoteRequired(Exception):
    """Raised when a transition to APPROVED or REJECTED is missing
    its decision_note. Routes map to HTTP 422 (Unprocessable Entity)
    since the body was missing a required field for THIS transition.
    """


# ─────────────────────────────────────────────────────────────────────────
# Reads
# ─────────────────────────────────────────────────────────────────────────


async def list_approval_requests(session: AsyncSession) -> list[ApprovalRequest]:
    """Return all approval requests visible to the active org (chassis-filtered)."""
    result = await session.execute(
        select(ApprovalRequest).order_by(ApprovalRequest.id.desc())
    )
    return list(result.scalars().all())


async def get_approval_request(
    session: AsyncSession, request_id: int
) -> ApprovalRequest:
    """Look up one approval request by id within the active org."""
    result = await session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise ApprovalNotFound(request_id)
    return req


# ─────────────────────────────────────────────────────────────────────────
# Writes
# ─────────────────────────────────────────────────────────────────────────


@audited(
    "approval_request.created",
    entity_type="approval_request",
    capture_details=lambda r: {"title": r.title, "status": r.status.value},
)
async def create_approval_request(
    session: AsyncSession, user: User, payload: ApprovalRequestCreate
) -> ApprovalRequest:
    """Create a new approval request — always lands in DRAFT status."""
    req = ApprovalRequest(
        requester_id=user.id,
        title=payload.title,
        body=payload.body,
        status=ApprovalStatus.DRAFT,
    )
    session.add(req)
    await session.flush()
    return req


@audited(
    "approval_request.updated",
    entity_type="approval_request",
    capture_details=lambda r: {"title": r.title, "status": r.status.value},
)
async def update_approval_request(
    session: AsyncSession, request_id: int, payload: ApprovalRequestUpdate
) -> ApprovalRequest:
    """Mutate title/body — ONLY allowed when status is DRAFT.

    Defense in depth: the state machine catches transition attempts; this
    function adds an additional guard so non-state mutations to non-DRAFT
    rows are blocked too. Returns the unchanged row + raises
    IllegalTransition (handled the same way at the route layer) if the
    request is in any other state.
    """
    req = await get_approval_request(session, request_id)
    if req.status != ApprovalStatus.DRAFT:
        raise IllegalTransition(
            current=req.status,
            target=req.status,
            message=(
                f"Cannot edit title/body of an approval request in {req.status.value} "
                f"state; only DRAFT requests are editable."
            ),
        )
    if payload.title is not None:
        req.title = payload.title
    if payload.body is not None:
        req.body = payload.body
    await session.flush()
    return req


@audited(
    "approval_request.transitioned",
    entity_type="approval_request",
    capture_details=lambda r: {
        "title": r.title,
        "status": r.status.value,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    },
)
async def transition(
    session: AsyncSession,
    user: User,
    request_id: int,
    payload: TransitionRequest,
) -> ApprovalRequest:
    """Move the approval request to a new status.

    Enforces ALLOWED_TRANSITIONS. Raises IllegalTransition if the proposed
    target is unreachable. Raises DecisionNoteRequired for APPROVED/REJECTED
    transitions without a decision_note. Otherwise mutates the row, stamps
    transition timestamps, and persists.
    """
    req = await get_approval_request(session, request_id)

    # Look up the allowed targets for the current status. If the current
    # state is missing from the map, that's a chassis bug (impossible by
    # the type system, but defensive). We treat missing as terminal.
    allowed = ALLOWED_TRANSITIONS.get(req.status, frozenset())
    if payload.target_status not in allowed:
        raise IllegalTransition(current=req.status, target=payload.target_status)

    # Side effects per transition. The state machine TABLE governs which
    # transitions are legal; this block governs the BOOKKEEPING side
    # effects of each legal transition.
    now = datetime.now(UTC)
    if (
        req.status == ApprovalStatus.DRAFT
        and payload.target_status == ApprovalStatus.SUBMITTED
    ):
        req.submitted_at = now
    elif req.status == ApprovalStatus.SUBMITTED and payload.target_status in {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
    }:
        if not payload.decision_note or not payload.decision_note.strip():
            raise DecisionNoteRequired(
                "decision_note is required when transitioning to APPROVED or REJECTED"
            )
        req.decided_at = now
        req.approver_id = user.id
        req.decision_note = payload.decision_note

    req.status = payload.target_status
    await session.flush()
    return req
