# Slot Testing Pattern

**Current as of chassis v0.10.0.**

> The reference for writing tests in `app/slots/<domain>/tests/`.
> Mirrors what the platform's chassis-mode Phase 2 prompt expects LLMs to produce.

## TL;DR

Every slot ships three test files:

```
app/slots/<domain>/tests/
├── __init__.py          # empty
├── conftest.py          # SLOT-LOCAL helper fixtures (personas, seeded data)
└── test_routes.py       # the actual pytest cases
```

`tests/conftest.py` is **mandatory** for any slot whose tests use httpx — without slot-local
helper fixtures, pytest cannot resolve `<role>_token`-style parameters and every test errors at
collection.

## Why this exists

Pytest's conftest discovery walks UP from each test file's directory toward the project root.
Slot test files live at `app/slots/<domain>/tests/test_*.py`. The walk visits:

1. `app/slots/<domain>/tests/conftest.py`   ← **THIS FILE** (slot-local)
2. `app/slots/<domain>/conftest.py`         (optional; rarely needed)
3. `app/slots/conftest.py`                  ← ships with chassis (re-exports chassis fixtures)
4. `app/conftest.py`                        (none)
5. `<repo-root>/conftest.py`                (none)

The walk **never** reaches `tests/conftest.py` (chassis tests root — sibling of `app/`, not
ancestor of slot tests). That's why `app/slots/conftest.py` re-exports the chassis fixtures
(`client`, `session`, `clean_db`, `app`, `_ensure_schema_and_seed`, `make_user`, `make_org`)
into the slot test discovery scope.

But the chassis can only provide **generic** fixtures. The chassis does not know what personas
your domain has (`requester_token` for a help-desk ticket? `event_organizer_token` for an
RSVP app? `recipe_author_token`?). Those are **slot-local** — every slot defines its own.

## The pattern

### 1. `tests/__init__.py`

Empty. Required so pytest treats the directory as a package.

```python
# (empty)
```

### 2. `tests/conftest.py`

Defines **persona fixtures** and **seeded-data fixtures** specific to your domain. Each persona
fixture registers a user via the chassis `make_user` builder, creates an org membership, and
yields a dict with `token` / `headers` / `user` / `org` keys.

```python
"""Slot-local pytest fixtures for the <domain> slot."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from httpx import AsyncClient

# Re-import the chassis convenience builders so they're available in the
# slot test scope without each test reaching back to tests.conftest.
from tests.conftest import make_org, make_user  # noqa: F401


@pytest_asyncio.fixture
async def author_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """A user + org with write permission on the domain."""
    auth = await make_user(client, email="author@example.com", password="password-password")
    org = await make_org(client, cast(dict[str, str], auth["headers"]), name="Co", slug="co")
    yield {"token": auth["token"], "headers": auth["headers"], "user": auth["user"], "org": org}


@pytest_asyncio.fixture
async def seeded_entity(
    client: AsyncClient, author_token: dict[str, object]
) -> dict[str, object]:
    """One pre-existing entity for GET/PATCH/DELETE tests."""
    headers = cast(dict[str, str], author_token["headers"])
    resp = await client.post("/your-route", json={...}, headers=headers)
    assert resp.status_code == 201, resp.text
    return cast(dict[str, object], resp.json())
```

### 3. `tests/test_routes.py`

Cover these six categories:

| Category | What it asserts | Typical status code |
|---|---|---|
| Happy path | Authenticated caller with right perm gets the expected resource | 200 / 201 |
| Auth gate | No `Authorization` header → 401 | 401 |
| Permission gate | Auth'd user without perm → 403 | 403 |
| Cross-org isolation | User in org A cannot see org B's data | 404 (NOT 403) |
| Validation | Bad payload → 422 (FastAPI/Pydantic) | 422 |
| Domain edge cases | State machine transitions, calculations, etc. | varies |

See `app/slots/example/tests/test_routes.py` for the full reference.

## Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Importing a slot-local fixture from `tests.conftest` | `fixture '<name>' not found` at collection | Define the fixture in `app/slots/<domain>/tests/conftest.py` |
| No `tests/__init__.py` | pytest cannot collect | Add an empty `__init__.py` |
| Using `requests.post(...)` instead of `await client.post(...)` | `RuntimeError: ...` | Use the chassis `client` fixture (httpx.AsyncClient) |
| `Session.query(...)` in test code | mypy --strict fails | Use `await session.execute(select(...))` |
| Cross-org test asserts 403 instead of 404 | False assertion failure | Chassis returns 404 to avoid info leakage |

## Reference implementation

`app/slots/example/tests/` is the canonical reference. Every LLM-generated slot's test files
should mirror its shape exactly:
- Persona fixture defined as a `pytest_asyncio.fixture` with `client: AsyncClient` parameter
- `make_user` + `make_org` chained inside the fixture body
- `yield` (not `return`) the dict so cleanup works
- Each test takes the persona fixture as a parameter; pytest resolves it
- HTTP assertions via `resp.status_code` and `resp.json()`; direct ORM via the `session` fixture
