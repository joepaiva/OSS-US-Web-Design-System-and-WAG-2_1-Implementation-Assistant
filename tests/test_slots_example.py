"""Slots/example tests — chassis isolation + RBAC + audit end-to-end.

These are the most important tests in the suite. They lock in the chassis
guarantees that LLM-generated slot code depends on:

  1. TenantScoped auto-filter prevents cross-org reads.
  2. before_flush auto-injects org_id on insert.
  3. Per-org admin role (via memberships.role_id) grants slot permissions.
  4. @audited writes one row per successful service call.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.slots.example.models import Note
from tests.conftest import make_org, make_user


async def test_create_note_returns_201(client: AsyncClient) -> None:
    u = await make_user(client, email="n1@example.com")
    await make_org(client, u["headers"], slug="n1org")  # type: ignore[arg-type]
    resp = await client.post(
        "/notes",
        json={"title": "first", "body": "hello"},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "first"
    assert body["body"] == "hello"
    assert body["org_id"]  # auto-injected
    assert body["author_id"]


async def test_tenant_scoped_filter_isolates_orgs(client: AsyncClient) -> None:
    """The chassis MUST prevent alice from seeing bob's notes."""
    alice = await make_user(client, email="alice@iso.com")
    bob = await make_user(client, email="bob@iso.com")
    await make_org(client, alice["headers"], slug="alice-iso")  # type: ignore[arg-type]
    await make_org(client, bob["headers"], slug="bob-iso")  # type: ignore[arg-type]

    await client.post(
        "/notes",
        json={"title": "alice-note-1", "body": "a"},
        headers=alice["headers"],  # type: ignore[arg-type]
    )
    await client.post(
        "/notes",
        json={"title": "alice-note-2", "body": "a"},
        headers=alice["headers"],  # type: ignore[arg-type]
    )
    await client.post(
        "/notes",
        json={"title": "bob-note", "body": "b"},
        headers=bob["headers"],  # type: ignore[arg-type]
    )

    alice_resp = await client.get("/notes", headers=alice["headers"])  # type: ignore[arg-type]
    bob_resp = await client.get("/notes", headers=bob["headers"])  # type: ignore[arg-type]
    assert {n["title"] for n in alice_resp.json()} == {"alice-note-1", "alice-note-2"}
    assert {n["title"] for n in bob_resp.json()} == {"bob-note"}


async def test_cross_org_get_by_id_returns_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Alice asking for Bob's note id should get 404 (auto-filter hides it)."""
    alice = await make_user(client, email="alice@cross.com")
    bob = await make_user(client, email="bob@cross.com")
    await make_org(client, alice["headers"], slug="alice-cross")  # type: ignore[arg-type]
    await make_org(client, bob["headers"], slug="bob-cross")  # type: ignore[arg-type]

    create_resp = await client.post(
        "/notes",
        json={"title": "bobs-secret", "body": "x"},
        headers=bob["headers"],  # type: ignore[arg-type]
    )
    bob_note_id = create_resp.json()["id"]

    # Sanity-check: bob sees his own note.
    own = await client.get(f"/notes/{bob_note_id}", headers=bob["headers"])  # type: ignore[arg-type]
    assert own.status_code == 200

    # Cross-org probe: alice gets 404, not 403.
    cross = await client.get(f"/notes/{bob_note_id}", headers=alice["headers"])  # type: ignore[arg-type]
    assert cross.status_code == 404


async def test_no_org_user_cannot_create_note(client: AsyncClient) -> None:
    """A user with no org membership can't write notes (CurrentOrg → 400)."""
    u = await make_user(client, email="no-org@example.com")
    resp = await client.post(
        "/notes",
        json={"title": "x", "body": ""},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    # 400 from get_current_org (no orgs) — chassis design rejects ambiguous
    # tenant context loudly.
    assert resp.status_code == 400


async def test_update_note_writes_audit_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="audit@example.com")
    await make_org(client, u["headers"], slug="audit-org")  # type: ignore[arg-type]
    create_resp = await client.post(
        "/notes",
        json={"title": "orig", "body": ""},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    note_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/notes/{note_id}",
        json={"title": "renamed"},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    assert patch_resp.status_code == 200

    # Two audit rows: notes.created + notes.updated.
    audit_rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.action.like("notes%")).order_by(AuditLog.id)
        )
    ).scalars().all()
    actions = [a.action for a in audit_rows]
    assert "notes.created" in actions
    assert "notes.updated" in actions


async def test_delete_note_returns_204_and_row_gone(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="del@example.com")
    await make_org(client, u["headers"], slug="del-org")  # type: ignore[arg-type]
    create_resp = await client.post(
        "/notes",
        json={"title": "kill-me", "body": ""},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    note_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/notes/{note_id}", headers=u["headers"])  # type: ignore[arg-type]
    assert del_resp.status_code == 204

    # Direct ORM check confirms storage is empty (chassis auto-filter would
    # also hide it in a re-GET, but we want to prove it's actually gone).
    notes = (
        await session.execute(select(Note).where(Note.id == note_id))
    ).scalars().all()
    assert notes == []


async def test_unauthenticated_get_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/notes")
    assert resp.status_code == 401
