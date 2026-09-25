# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# AC-3: requires() FastAPI dependency gates routes to permitted roles
# AC-6: permissions scoped to accessibility_assistant domain only
# ─────────────────────────────────────────────────────────────────
"""Accessibility Assistant slot — v0.1 + v0.2 + v0.3.

Registers slot permissions at import time via the chassis RBAC registry.

Permissions defined in v0.1:
  assistant:read   — browse FAQs, view categories (FR-003)
  assistant:ask    — submit questions, receive responses (FR-002, FR-004, FR-005, FR-006)
  assistant:admin  — admin-level interaction log access (SR-003)

Permissions added in v0.2 (FR-007 through FR-017):
  assistant:source_category_manage — create information source categories (FR-010).
      Granted to: Platform Administrator, Organization Administrator only.
  assistant:source_read            — view information sources/categories (FR-011).
      Granted to: Platform Administrator, Organization Administrator, Content Manager.
  assistant:source_manage          — configure/test information sources (FR-011..FR-014).
      Granted to: Platform Administrator, Organization Administrator, Content Manager.
  assistant:question_category_manage — create question categories (FR-015).
      Granted to: Platform Administrator, Organization Administrator only.
  assistant:faq_manage              — create FAQs (FR-016).
      Granted to: Platform Administrator, Organization Administrator, Content Manager.
  assistant:llm_fallback_manage     — configure LLM fallback mode (FR-009).
      Granted to: Platform Administrator, Organization Administrator only.
  assistant:role_manage             — designate a Content Manager within an org.
      Granted to: Platform Administrator, Organization Administrator only.

Permissions added in v0.3 (FR-017 through FR-022, SR-005..SR-007, NFR-001):
  assistant:platform_share         — designate a resource platform-level shared (FR-020).
      Route-level gate grants this to the chassis "admin" role (both Platform and
      Organization Administrators, per the RBAC-collapse note below); the SERVICE
      layer additionally requires `user.is_superuser` (a genuine Platform
      Administrator) before the share actually takes effect — see service.py's
      `_share_resource`. This is the one place in this slot where the
      Platform-vs-Organization-Administrator distinction that FR-020/FR-027
      require is enforced explicitly in code rather than via a permission grant,
      because this chassis's RBAC model has no permission that could express it
      (see the RBAC-collapse note below).
  assistant:interaction_log_read   — the FR-021 administrator interaction-log view.
      Granted to: Platform Administrator, Organization Administrator (via the shared
      "admin" role); Content Managers and End Users are denied. Deliberately a NEW,
      separate permission from `assistant:admin` (v0.1's own admin-interactions view)
      so that the pre-existing `/assistant/admin/interactions` route/tests are not
      disturbed by FR-021's different (cross-org-for-superusers) scoping.
  T-007/T-008's two automated-FAQ-generation capabilities (FR-017, FR-018) reuse the
  existing `assistant:faq_manage` permission rather than adding a new one — their
  linked personas (Platform Administrator, Organization Administrator, Content
  Manager) are identical to FAQ_MANAGE's.

Every permission registered here is auto-granted to the chassis "admin"
role by `seed_chassis_rbac` (it grants ALL registered permissions to
"admin" — see app/rbac/service.py), which is why "Platform Administrator"
and "Organization Administrator" above collapse onto the single chassis
"admin" role: this chassis's RBAC model does not distinguish the two. The
"Content Manager" persona has no chassis-native role, so this slot
provisions its own "content_manager" role (see service.py
`ensure_content_manager_role`) via the RBAC extension point's underlying
data model (Role/Permission/role_permissions are plain, slot-writable
tables — no chassis code is modified) and exposes a slot-owned admin
endpoint (FR-010's neighbourhood, "assistant:role_manage") so a real
Organization Administrator can designate one in a live deployment, not
just in tests.

Soft-delete: NOT used in this slot (ARCHITECTURE.md §2.9 — opt-in only).
"""

from app.rbac.permissions import register

# Slot-defined permissions — auto-seeded on next startup.
ASSISTANT_READ = "assistant:read"
ASSISTANT_ASK = "assistant:ask"
ASSISTANT_ADMIN = "assistant:admin"

# v0.2 additions.
ASSISTANT_SOURCE_CATEGORY_MANAGE = "assistant:source_category_manage"
ASSISTANT_SOURCE_READ = "assistant:source_read"
ASSISTANT_SOURCE_MANAGE = "assistant:source_manage"
ASSISTANT_QUESTION_CATEGORY_MANAGE = "assistant:question_category_manage"
ASSISTANT_FAQ_MANAGE = "assistant:faq_manage"
ASSISTANT_LLM_FALLBACK_MANAGE = "assistant:llm_fallback_manage"
ASSISTANT_ROLE_MANAGE = "assistant:role_manage"

# v0.3 additions.
ASSISTANT_PLATFORM_SHARE = "assistant:platform_share"
ASSISTANT_INTERACTION_LOG_READ = "assistant:interaction_log_read"

# The permission set granted to the slot-provisioned "content_manager" role.
# Exported so service.py's ensure_content_manager_role() stays in sync with
# this module's own documentation of who gets what.
CONTENT_MANAGER_PERMISSIONS = (
    ASSISTANT_READ,
    ASSISTANT_ASK,
    ASSISTANT_SOURCE_READ,
    ASSISTANT_SOURCE_MANAGE,
    ASSISTANT_FAQ_MANAGE,
)

register(ASSISTANT_READ, "Browse FAQ categories and FAQ entries in the Accessibility Assistant")
register(ASSISTANT_ASK, "Submit questions and receive responses in the Accessibility Assistant")
register(ASSISTANT_ADMIN, "Access interaction logs and admin views in the Accessibility Assistant")
register(
    ASSISTANT_SOURCE_CATEGORY_MANAGE,
    "Create and manage information source categories",
)
register(ASSISTANT_SOURCE_READ, "View information sources and their categories")
register(ASSISTANT_SOURCE_MANAGE, "Configure and test information sources")
register(ASSISTANT_QUESTION_CATEGORY_MANAGE, "Create and manage question categories")
register(ASSISTANT_FAQ_MANAGE, "Create FAQs manually")
register(
    ASSISTANT_LLM_FALLBACK_MANAGE,
    "Configure the LLM fallback mode per source category and question category",
)
register(ASSISTANT_ROLE_MANAGE, "Designate Content Managers within an organization")
register(
    ASSISTANT_PLATFORM_SHARE,
    "Designate an information source, information source category, or FAQ as "
    "platform-level shared",
)
register(
    ASSISTANT_INTERACTION_LOG_READ,
    "View the administrator interaction log view (Platform/Organization Administrator)",
)
