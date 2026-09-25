"""Slot-local pytest fixtures for the example (Notes) slot.

THIS FILE IS THE REFERENCE PATTERN for slot tests across the chassis.
Every LLM-generated slot's `app/slots/<domain>/tests/conftest.py` should
mirror this shape. The chassis ships `app/slots/conftest.py` which
re-exports the core chassis fixtures (`client`, `session`, `clean_db`,
`app`, `_ensure_schema_and_seed`, `make_user`, `make_org`) so they're
discoverable from inside `app/slots/<domain>/tests/`. This file ADDS
slot-local helper fixtures that are specific to the slot's domain.

═══════════════════════════════════════════════════════════════════════
THE HELPER-FIXTURE PATTERN — WHY IT EXISTS, HOW TO USE IT
═══════════════════════════════════════════════════════════════════════

The chassis provides:
  - `client` — an httpx.AsyncClient bound to the FastAPI app
  - `session` — an AsyncSession for direct ORM assertions
  - `clean_db` — autouse TRUNCATE between tests
  - `make_user(client, email, password)` — registers + returns token+headers
  - `make_org(client, headers, name, slug)` — creates an org

The chassis does NOT provide:
  - Slot-specific "author_token", "viewer_token", "admin_token" fixtures
  - Slot-specific seeded data (e.g. a Note that already exists)
  - Slot-specific role grants (e.g. "user has notes:write permission")

These are DOMAIN-SPECIFIC. Each slot defines them in its own
`tests/conftest.py` as a layer on top of the chassis fixtures. Pytest's
conftest discovery walks UP from each test file, so fixtures defined
here are visible to every test in `app/slots/example/tests/`.

Pattern for a slot:
  1. Define `<role>_token` async fixtures (one per persona the slot tests).
     Each fixture:
       - awaits `make_user(client, ...)` → registers + gets a token
       - awaits `make_org(client, headers)` → creates an org membership
       - optionally grants slot permissions to the user's role
       - yields a dict with `token`, `headers`, `user`, `org`
  2. Define `seeded_<entity>` async fixtures for tests that need
     pre-existing data — e.g. `seeded_note` creates one Note via the
     POST /notes API as `note_author_token`.
  3. Tests take these fixtures as parameters; pytest resolves them.

Common mistake to avoid: do NOT try to import `requester_token` /
`agent_token` / etc. from `tests.conftest` (chassis-level). They don't
exist there. Define them HERE, slot-local. Each slot is responsible
for its own personas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from httpx import AsyncClient

# Re-import the chassis convenience builders so test files can use them
# via the slot-local conftest scope without reaching up.
from tests.conftest import make_org, make_user  # noqa: F401

# ────────────────────────────────────────────────────────────────────────
# Persona fixtures — one per role/persona the slot's tests need
# ────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def note_author_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """A user registered + in an org, ready to POST /notes.

    Returns a dict with keys: token, headers, user, org.
    Tests use the headers value for authenticated requests:
        await client.post("/notes", json={...}, headers=note_author_token["headers"])

    The chassis seeds the 'admin' role for the FIRST user in an org. Since
    notes:write is granted to the 'admin' role by default (see
    app/rbac/service.py:seed_chassis_rbac), this user can write notes.
    For slots that need a NON-admin persona, see `note_viewer_token` below.
    """
    auth = await make_user(client, email="author@example.com", password="TestPassword123!")
    org = await make_org(
        client, cast(dict[str, str], auth["headers"]), name="Author Co", slug="author-co"
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def note_viewer_token(
    client: AsyncClient, note_author_token: dict[str, object]
) -> AsyncIterator[dict[str, object]]:
    """A SECOND user in the SAME org as note_author_token, role=user.

    The chassis assigns the 'user' role to non-first members. In the seeded
    RBAC config, 'user' has notes:read but NOT notes:write — perfect for
    testing permission boundaries.

    Returns the same dict shape as note_author_token. Useful for tests
    asserting that read-only personas can GET /notes but cannot POST.
    """
    author_org = cast(dict[str, object], note_author_token["org"])
    org_slug = cast(str, author_org["slug"])
    viewer = await make_user(
        client, email="viewer@example.com", password="TestPassword123!"
    )
    # Note: in v0.3.x chassis, joining an existing org as a non-first user
    # requires an invite flow that's not yet shipped. For now this fixture
    # creates a SEPARATE org for the viewer. Slots that need same-org
    # multi-persona testing should mock the membership directly via the
    # `session` fixture (see test_routes.py for a worked example).
    viewer_org = await make_org(
        client, cast(dict[str, str], viewer["headers"]), name="Viewer Co", slug=f"viewer-{org_slug}"
    )
    yield {
        "token": viewer["token"],
        "headers": viewer["headers"],
        "user": viewer["user"],
        "org": viewer_org,
    }


# ────────────────────────────────────────────────────────────────────────
# Seeded-data fixtures — pre-existing entities for tests that need them
# ────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_note(
    client: AsyncClient, note_author_token: dict[str, object]
) -> dict[str, object]:
    """Create one Note via POST /notes; return the response body.

    Useful for GET/PATCH/DELETE tests that need an existing note to operate
    on without each test paying for the create-it-first step.

    Returns the JSON dict from the POST response (has `id`, `title`,
    `body`, `org_id`, etc.).
    """
    headers = cast(dict[str, str], note_author_token["headers"])
    resp = await client.post(
        "/notes",
        json={"title": "Seeded note", "body": "Initial body"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return cast(dict[str, object], resp.json())
