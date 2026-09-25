"""Re-export chassis test fixtures so slot tests can discover them.

The chassis test fixtures (`client`, `session`, `clean_db`, `app`,
`_ensure_schema_and_seed`) live in `tests/conftest.py` at the chassis
test root. Slot tests live at `app/slots/<domain>/tests/test_routes.py`.

pytest's conftest discovery walks UP from each test file's location.
From `app/slots/<domain>/tests/`, it visits:
  - app/slots/<domain>/tests/conftest.py    (slot-local, optional)
  - app/slots/<domain>/conftest.py          (slot-local, optional)
  - app/slots/conftest.py                   ← THIS FILE
  - app/conftest.py                         (none)
  - <repo-root>/conftest.py                 (none)

It NEVER reaches `tests/conftest.py` — that's a sibling, not an ancestor.

So without this re-export, any slot test that takes `client: AsyncClient`
or `session: AsyncSession` as a parameter fails at collection with
`fixture 'client' not found`.

This file fixes that: import the chassis fixtures and re-bind them at
`app/slots/conftest.py` so pytest discovery finds them when collecting
slot tests. The fixture decorators were already applied in the chassis
conftest; importing the name is enough.

CAL-8 — calibration item surfaced by Phase 3 HelpDesk Build #42 and
EventRSVP Build #43 (both produced httpx-style integration tests that
errored at collection because `client` wasn't found).
"""

# Re-export chassis fixtures into the slot test discovery scope.
# noqa: F401 — these names ARE used by pytest, even though static
# analysis can't see the indirection.
# Convenience builders (NOT pytest fixtures themselves, but slot tests
# routinely import them as `from tests.conftest import make_user, make_org`).
# Re-exporting here means `from app.slots.<your_slot>.tests.<file> import
# make_user, make_org` works too, AND any slot test that uses them via the
# chassis-import path keeps working.
from tests.conftest import (  # noqa: F401
    _ensure_schema_and_seed,
    app,
    clean_db,
    client,
    make_org,
    make_user,
    session,
)
