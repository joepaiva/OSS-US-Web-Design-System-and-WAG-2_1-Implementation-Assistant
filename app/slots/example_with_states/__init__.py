"""Example slot with state machine — Approval Request.

Reference implementation for slot domains that have a state machine.
Mirrors the shape of slots/example/ (CRUD) but adds:
  - models.py — Status enum + lifecycle column
  - schemas.py — TransitionRequest schema
  - service.py — transition() function with illegal-transition rejection
                 (raises IllegalTransition; routes map to 409 Conflict)
  - routes.py  — POST /approval-requests/{id}/transitions endpoint
  - tests/     — pytest cases covering happy path, illegal transitions,
                 terminal state guards, and cross-org isolation

Domain: a simple Approval Request workflow.

  draft  ──▶  submitted  ──▶  approved   (terminal)
   ▲    │     │
   │    │     └─▶ rejected   (terminal)
   └────┘     (resubmit not allowed; the requester must create a NEW
              draft to retry — that's a business rule, not a chassis rule)

Why a separate example: Phase 3 found that LeaveLite, RecipeShare,
HelpDesk, and EventRSVP ALL had state machines. The chassis had zero
reference for the pattern, so the LLM kept reinventing it (sometimes
without the illegal-transition guard, which produced apps that
silently allowed approved→draft transitions).

Permissions: approval-requests:read + approval-requests:write registered
at import time so seed_chassis_rbac picks them up on startup.
"""

from app.rbac.permissions import register

APPROVAL_REQUESTS_READ = "approval-requests:read"
APPROVAL_REQUESTS_WRITE = "approval-requests:write"

register(APPROVAL_REQUESTS_READ, "Read approval requests in the current organization")
register(
    APPROVAL_REQUESTS_WRITE,
    "Create, update, transition, or delete approval requests in the current organization",
)
