"""Note routes — the reference shape for slot routes.

LLMs mirror this for new slots:
  - APIRouter(prefix=..., tags=[...])
  - Dependencies: CurrentUser, CurrentOrg, Depends(requires(perm))
  - Service-layer calls; no business logic here.
  - HTTPException for service-layer errors.

CurrentOrg is REQUIRED on every slot route that touches TenantScoped models
— it binds the org_id var that powers the chassis auto-filter. Forgetting
it means the route returns 400 or shows ALL orgs' data depending on the
caller's prior context (the chassis chose 400 in v0.1.0 to be loud).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.db import SessionDep
from app.deps import CurrentOrg, CurrentUser, requires
from app.logging import get_logger
from app.slots.example import NOTES_READ, NOTES_WRITE
from app.slots.example.schemas import NoteCreate, NoteRead, NoteUpdate
from app.slots.example.service import (
    NoteNotFound,
    create_note,
    delete_note,
    get_note,
    list_notes,
    update_note,
)

log = get_logger("slots.example")

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get(
    "",
    response_model=list[NoteRead],
    dependencies=[Depends(requires(NOTES_READ))],
)
async def list_(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[NoteRead]:
    notes = await list_notes(session)
    return [NoteRead.model_validate(n) for n in notes]


@router.post(
    "",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires(NOTES_WRITE))],
)
async def create(
    payload: NoteCreate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> NoteRead:
    note = await create_note(session, user, payload)
    log.info("notes.created", note_id=note.id, org_id=org.id, author_id=user.id)
    return NoteRead.model_validate(note)


@router.get(
    "/{note_id}",
    response_model=NoteRead,
    dependencies=[Depends(requires(NOTES_READ))],
)
async def retrieve(
    note_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> NoteRead:
    try:
        note = await get_note(session, note_id)
    except NoteNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from exc
    return NoteRead.model_validate(note)


@router.patch(
    "/{note_id}",
    response_model=NoteRead,
    dependencies=[Depends(requires(NOTES_WRITE))],
)
async def update(
    note_id: int,
    payload: NoteUpdate,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> NoteRead:
    try:
        note = await update_note(session, note_id, payload)
    except NoteNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from exc
    return NoteRead.model_validate(note)


@router.delete(
    "/{note_id}",
    dependencies=[Depends(requires(NOTES_WRITE))],
)
async def destroy(
    note_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> Response:
    """Delete a note. Returns 204.

    FastAPI 0.115 rejects routes declared with `status_code=204` AND a
    `response: Response` parameter (or any signature it deems body-producing)
    via the `is_body_allowed_for_status_code` assert. Pattern: drop the
    decorator status_code and return a fresh Response(status_code=204).
    Same shape as `/auth/logout`.
    """
    try:
        await delete_note(session, note_id)
    except NoteNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
