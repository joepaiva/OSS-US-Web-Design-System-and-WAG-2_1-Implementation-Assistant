"""Approval Request routes — the canonical state-machine route shape.

Endpoints:
  - POST   /approval-requests                            — create (DRAFT)
  - GET    /approval-requests                            — list (chassis-filtered)
  - GET    /approval-requests/{id}                       — get one
  - PATCH  /approval-requests/{id}                       — update title/body (DRAFT only)
  - POST   /approval-requests/{id}/transitions           — apply a transition
  - DELETE /approval-requests/{id}                       — delete (any state)

Note on the transitions sub-resource: POST creates a transition. The
target status lives in the body, NOT the URL. This keeps the URL space
agnostic to the state machine (so adding states later doesn't require
adding routes) and lets the service layer's ALLOWED_TRANSITIONS table
remain the single source of truth.

Exception mapping at this layer:
  - ApprovalNotFound      → 404
  - IllegalTransition     → 409
  - DecisionNoteRequired  → 422
  - Generic ValueError    → 422 (FastAPI default)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.db import SessionDep
from app.deps import CurrentOrg, CurrentUser, requires
from app.logging import get_logger
from app.slots.example_with_states import (
    APPROVAL_REQUESTS_READ,
    APPROVAL_REQUESTS_WRITE,
)
from app.slots.example_with_states.schemas import (
    ApprovalRequestCreate,
    ApprovalRequestRead,
    ApprovalRequestUpdate,
    TransitionRequest,
)
from app.slots.example_with_states.service import (
    ApprovalNotFound,
    DecisionNoteRequired,
    IllegalTransition,
    create_approval_request,
    get_approval_request,
    list_approval_requests,
    transition,
    update_approval_request,
)

log = get_logger("slots.example_with_states")

router = APIRouter(prefix="/approval-requests", tags=["approval-requests"])


@router.get(
    "",
    response_model=list[ApprovalRequestRead],
    dependencies=[Depends(requires(APPROVAL_REQUESTS_READ))],
)
async def list_(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[ApprovalRequestRead]:
    rows = await list_approval_requests(session)
    return [ApprovalRequestRead.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=ApprovalRequestRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(APPROVAL_REQUESTS_WRITE))],
)
async def create(
    payload: ApprovalRequestCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> ApprovalRequestRead:
    req = await create_approval_request(session, user, payload)
    log.info(
        "approval_request.created",
        request_id=req.id,
        org_id=org.id,
        requester_id=user.id,
    )
    return ApprovalRequestRead.model_validate(req)


@router.get(
    "/{request_id}",
    response_model=ApprovalRequestRead,
    dependencies=[Depends(requires(APPROVAL_REQUESTS_READ))],
)
async def retrieve(
    request_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> ApprovalRequestRead:
    try:
        req = await get_approval_request(session, request_id)
    except ApprovalNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found"
        ) from exc
    return ApprovalRequestRead.model_validate(req)


@router.patch(
    "/{request_id}",
    response_model=ApprovalRequestRead,
    dependencies=[Depends(requires(APPROVAL_REQUESTS_WRITE))],
)
async def update(
    request_id: int,
    payload: ApprovalRequestUpdate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> ApprovalRequestRead:
    try:
        req = await update_approval_request(session, request_id, payload)
    except ApprovalNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found"
        ) from exc
    except IllegalTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "illegal_state",
                "current_status": exc.current.value,
                "message": exc.message,
            },
        ) from exc
    return ApprovalRequestRead.model_validate(req)


@router.post(
    "/{request_id}/transitions",
    response_model=ApprovalRequestRead,
    dependencies=[Depends(requires(APPROVAL_REQUESTS_WRITE))],
)
async def apply_transition(
    request_id: int,
    payload: TransitionRequest,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> ApprovalRequestRead:
    """Apply a state transition.

    Returns the updated approval request on success. Returns 409 on
    illegal transition, 422 on missing decision_note for terminal
    transitions, 404 if the id is missing.
    """
    try:
        req = await transition(session, user, request_id, payload)
    except ApprovalNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found"
        ) from exc
    except IllegalTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "illegal_transition",
                "current_status": exc.current.value,
                "attempted_target": exc.target.value,
                "message": exc.message,
            },
        ) from exc
    except DecisionNoteRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "decision_note_required",
                "message": str(exc),
            },
        ) from exc
    log.info(
        "approval_request.transitioned",
        request_id=req.id,
        org_id=org.id,
        actor_id=user.id,
        new_status=req.status.value,
    )
    return ApprovalRequestRead.model_validate(req)


@router.delete(
    "/{request_id}",
    dependencies=[Depends(requires(APPROVAL_REQUESTS_WRITE))],
)
async def destroy(
    request_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> Response:
    """Delete an approval request (any state). Returns 204."""
    try:
        req = await get_approval_request(session, request_id)
        await session.delete(req)
        await session.flush()
    except ApprovalNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
