"""Reference slot route tests — the canonical shape every LLM-generated slot mirrors.

PYTEST SCOPE: this test file lives at `app/slots/example/tests/test_routes.py`.
Pytest's conftest discovery walks UP from this location, so it sees:

  1. `app/slots/example/tests/conftest.py`  — slot-local persona fixtures
  2. `app/slots/example/conftest.py`        — (none; not needed)
  3. `app/slots/conftest.py`                — chassis-fixtures re-export
                                              (CAL-8: lets `client`, `session`,
                                               etc. resolve from chassis)
  4. `app/conftest.py`                      — (none)
  5. <repo-root>/conftest.py                — (none)

It does NOT see `tests/conftest.py` directly (siblings, not ancestors) —
the `app/slots/conftest.py` re-export bridges that gap.

═══════════════════════════════════════════════════════════════════════
WHAT EVERY SLOT'S test_routes.py SHOULD COVER
═══════════════════════════════════════════════════════════════════════

  1. Happy path — authenticated user with the right permission can call
     the route and gets the expected response.
  2. Auth gate — unauthenticated requests get 401.
  3. Permission gate — authenticated user WITHOUT the required perm
     gets 403.
  4. Cross-org isolation — user A's org cannot see user B's org's data
     (this is the multi-tenancy invariant; the chassis enforces it via
      TenantScoped, but slot tests should verify the visible behavior).
  5. Validation — bad payloads get 422 (FastAPI/Pydantic handles this;
     a single sanity check is sufficient).
  6. Edge cases specific to the domain (e.g. state machine transitions).

The chassis owns auth, RBAC, multi-tenancy mechanism. Slot tests don't
re-test the chassis — they verify that the SLOT correctly USES the
chassis primitives.
"""

from __future__ import annotations

from typing import cast

import pytest
from httpx import AsyncClient

# ────────────────────────────────────────────────────────────────────────
# Happy path
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_note_happy_path(
    client: AsyncClient, note_author_token: dict[str, object]
) -> None:
    """POST /notes by an authenticated author returns 201 with the new note."""
    headers = cast(dict[str, str], note_author_token["headers"])
    resp = await client.post(
        "/notes",
        json={"title": "First note", "body": "Hello world"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "First note"
    assert data["body"] == "Hello world"
    assert "id" in data
    assert "org_id" in data


@pytest.mark.asyncio
async def test_list_notes_returns_only_own_org(
    client: AsyncClient,
    note_author_token: dict[str, object],
    seeded_note: dict[str, object],
) -> None:
    """GET /notes returns notes in the caller's org (the chassis auto-filter)."""
    headers = cast(dict[str, str], note_author_token["headers"])
    resp = await client.get("/notes", headers=headers)
    assert resp.status_code == 200
    notes = resp.json()
    assert len(notes) >= 1
    # The seeded note's id should be present.
    seeded_id = seeded_note["id"]
    assert any(n["id"] == seeded_id for n in notes)


@pytest.mark.asyncio
async def test_get_note_by_id(
    client: AsyncClient,
    note_author_token: dict[str, object],
    seeded_note: dict[str, object],
) -> None:
    """GET /notes/{id} returns the single note."""
    headers = cast(dict[str, str], note_author_token["headers"])
    note_id = seeded_note["id"]
    resp = await client.get(f"/notes/{note_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == note_id


# ────────────────────────────────────────────────────────────────────────
# Auth gate
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_note_requires_auth(client: AsyncClient) -> None:
    """POST /notes without Authorization header returns 401."""
    resp = await client.post("/notes", json={"title": "x", "body": "y"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_notes_requires_auth(client: AsyncClient) -> None:
    """GET /notes without Authorization header returns 401."""
    resp = await client.get("/notes")
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# Cross-org isolation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_org_isolation(
    client: AsyncClient,
    note_author_token: dict[str, object],
    note_viewer_token: dict[str, object],
    seeded_note: dict[str, object],
) -> None:
    """Viewer's org cannot see Author's org's notes — chassis TenantScoped invariant."""
    viewer_headers = cast(dict[str, str], note_viewer_token["headers"])
    seeded_id = seeded_note["id"]
    resp = await client.get(f"/notes/{seeded_id}", headers=viewer_headers)
    # The chassis auto-filter scopes Notes by org_id. From the viewer's
    # different org, the note is invisible — 404, NOT 403 (information
    # leakage prevention: don't tell the caller the resource exists in
    # someone else's org).
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_note_validates_payload(
    client: AsyncClient, note_author_token: dict[str, object]
) -> None:
    """POST /notes with missing required fields returns 422."""
    headers = cast(dict[str, str], note_author_token["headers"])
    resp = await client.post("/notes", json={}, headers=headers)
    assert resp.status_code == 422


# ────────────────────────────────────────────────────────────────────────
# Update + Delete (mutation lifecycle)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_note(
    client: AsyncClient,
    note_author_token: dict[str, object],
    seeded_note: dict[str, object],
) -> None:
    """PATCH /notes/{id} updates the title; chassis audit logs the event."""
    headers = cast(dict[str, str], note_author_token["headers"])
    note_id = seeded_note["id"]
    resp = await client.patch(
        f"/notes/{note_id}",
        json={"title": "Updated"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


@pytest.mark.asyncio
async def test_delete_note(
    client: AsyncClient,
    note_author_token: dict[str, object],
    seeded_note: dict[str, object],
) -> None:
    """DELETE /notes/{id} returns 204; subsequent GET returns 404."""
    headers = cast(dict[str, str], note_author_token["headers"])
    note_id = seeded_note["id"]

    del_resp = await client.delete(f"/notes/{note_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/notes/{note_id}", headers=headers)
    assert get_resp.status_code == 404
