"""Example slot — Notes.

Reference implementation. Every slot LLMs generate MUST follow this shape:
  - models.py    — SQLAlchemy 2.0 typed, inherits (Base, TenantScoped)
  - schemas.py   — Pydantic v2 with ConfigDict, separate Create/Update/Read
  - service.py   — async functions, @audited on writes, no FastAPI imports
  - routes.py    — APIRouter, uses CurrentUser/CurrentOrg/requires() deps
  - tests/       — pytest-asyncio + httpx.AsyncClient + factories

This module's __init__ registers two permissions at import time, hooked
into the chassis CHASSIS-EXTENSION-POINT in app.rbac.permissions.
"""

from app.rbac.permissions import register

# Slot-defined permissions. These are added to the chassis registry at
# import time so seed_chassis_rbac picks them up on next startup.
NOTES_READ = "notes:read"
NOTES_WRITE = "notes:write"

register(NOTES_READ, "Read notes in the current organization")
register(NOTES_WRITE, "Create, update, or delete notes in the current organization")
