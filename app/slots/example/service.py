"""Notes service layer — async, no FastAPI imports.

Notice what this slot DOES NOT do:
  - It does NOT filter `WHERE org_id = X` anywhere. The chassis
    TenantScoped event listener does that automatically.
  - It does NOT set `note.org_id` on insert. The chassis before_flush
    listener does that automatically.
  - It does NOT touch the audit log directly. The @audited decorator does
    that automatically on success.
  - It does NOT check RBAC. The routes do via Depends(requires(...)).

Slot authors write only business logic. Chassis owns isolation, auth,
RBAC, and audit invariants.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.auth.models import User
from app.slots.example.models import Note
from app.slots.example.schemas import NoteCreate, NoteUpdate


class NoteNotFound(Exception):
    pass


# ────────────────────────────────────────────────────────────────────────
# Reads
# ────────────────────────────────────────────────────────────────────────


async def list_notes(session: AsyncSession) -> list[Note]:
    """Return ALL notes the chassis filter allows the caller to see.

    The chassis auto-filter (TenantScoped + current_org_id_var) restricts
    rows to the active org. No `where(Note.org_id == ...)` here — that
    would be redundant AND would prevent the chassis from layering its
    isolation invariant on top.
    """
    result = await session.execute(select(Note).order_by(Note.id))
    return list(result.scalars().all())


async def get_note(session: AsyncSession, note_id: int) -> Note:
    """Look up one note by id within the active org. Raises NoteNotFound."""
    result = await session.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if note is None:
        raise NoteNotFound(note_id)
    return note


# ────────────────────────────────────────────────────────────────────────
# Writes
# ────────────────────────────────────────────────────────────────────────


@audited(
    "notes.created",
    entity_type="note",
    capture_details=lambda note: {"title": note.title},
)
async def create_note(
    session: AsyncSession, user: User, payload: NoteCreate
) -> Note:
    """Create a note. org_id auto-injected by chassis before_flush listener."""
    note = Note(
        author_id=user.id,
        title=payload.title,
        body=payload.body,
    )
    session.add(note)
    await session.flush()
    return note


@audited(
    "notes.updated",
    entity_type="note",
    capture_details=lambda note: {"title": note.title},
)
async def update_note(
    session: AsyncSession, note_id: int, payload: NoteUpdate
) -> Note:
    """Patch a note. Chassis filter ensures the note is in the active org."""
    note = await get_note(session, note_id)
    if payload.title is not None:
        note.title = payload.title
    if payload.body is not None:
        note.body = payload.body
    await session.flush()
    return note


@audited("notes.deleted", entity_type="note")
async def delete_note(session: AsyncSession, note_id: int) -> Note:
    """Delete a note. Returns the deleted instance so audit can capture its id."""
    note = await get_note(session, note_id)
    await session.delete(note)
    await session.flush()
    return note
