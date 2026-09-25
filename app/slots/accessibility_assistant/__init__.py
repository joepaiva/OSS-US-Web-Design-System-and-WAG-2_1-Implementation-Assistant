# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# AC-3: requires() FastAPI dependency gates routes to permitted roles
# AC-6: permissions scoped to accessibility_assistant domain only
# ─────────────────────────────────────────────────────────────────
"""Accessibility Assistant slot — v0.1.

Registers slot permissions at import time via the chassis RBAC registry.

Permissions defined:
  assistant:read   — browse FAQs, view categories (FR-003)
  assistant:ask    — submit questions, receive responses (FR-002, FR-004, FR-005, FR-006)
  assistant:admin  — admin-level interaction log access (SR-003)

Soft-delete: NOT used in this slot (ARCHITECTURE.md §2.9 — opt-in only).
"""

from app.rbac.permissions import register

# Slot-defined permissions — auto-seeded on next startup.
ASSISTANT_READ = "assistant:read"
ASSISTANT_ASK = "assistant:ask"
ASSISTANT_ADMIN = "assistant:admin"

register(ASSISTANT_READ, "Browse FAQ categories and FAQ entries in the Accessibility Assistant")
register(ASSISTANT_ASK, "Submit questions and receive responses in the Accessibility Assistant")
register(ASSISTANT_ADMIN, "Access interaction logs and admin views in the Accessibility Assistant")
