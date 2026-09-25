"""Permission registry — chassis-owned defaults + slot extension point.

Each permission is a colon-scoped string. The chassis ships with the
permissions below. Slots add their own at the marked extension point.

Why a registry: at app startup we ensure every registered permission has a
row in the `permissions` table. New permissions added by slots auto-seed
on next boot — no migration required for permission additions.
"""

from __future__ import annotations


class CorePermissions:
    """Chassis-owned permissions. NEVER rename — they are stored verbatim in DB."""

    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    ORGS_READ = "orgs:read"
    ORGS_WRITE = "orgs:write"
    AUDIT_READ = "audit:read"
    LLM_READ = "llm:read"
    LLM_WRITE = "llm:write"
    # chassis-program FR-MCPCLIENT — MCP server connection registration
    # (client role only) and the tools it exposes to the embedded LLM.
    MCP_READ = "mcp:read"
    MCP_WRITE = "mcp:write"
    # chassis-program FR-PLATHEALTH — Platform Health (component inventory,
    # currency, vulnerability scan, gated remediation).
    PLATFORM_HEALTH_READ = "platform_health:read"
    PLATFORM_HEALTH_WRITE = "platform_health:write"
    # chassis-program FR-FISMAAUDIT — FISMA self-audit + report.
    FISMA_AUDIT_READ = "fisma_audit:read"


# Registry — populated by chassis at module import, extended by slots.
_registered: set[str] = {
    CorePermissions.USERS_READ,
    CorePermissions.USERS_WRITE,
    CorePermissions.ORGS_READ,
    CorePermissions.ORGS_WRITE,
    CorePermissions.AUDIT_READ,
    CorePermissions.LLM_READ,
    CorePermissions.LLM_WRITE,
    CorePermissions.MCP_READ,
    CorePermissions.MCP_WRITE,
    CorePermissions.PLATFORM_HEALTH_READ,
    CorePermissions.PLATFORM_HEALTH_WRITE,
    CorePermissions.FISMA_AUDIT_READ,
}

# ─── CHASSIS-EXTENSION-POINT: slot-permissions ────────────────────────
# Slots register additional permissions here by calling `register(...)`
# at module import (typically in app/slots/<name>/__init__.py or models.py).
# Example for a hypothetical inventory slot:
#     from app.rbac.permissions import register
#     register("inventory:read", "Read inventory items")
#     register("inventory:write", "Create or modify inventory items")
# ─────────────────────────────────────────────────────────────────────


_descriptions: dict[str, str] = {
    CorePermissions.USERS_READ: "Read user records",
    CorePermissions.USERS_WRITE: "Create, modify, or deactivate users",
    CorePermissions.ORGS_READ: "Read organization records",
    CorePermissions.ORGS_WRITE: "Create, modify, or delete organizations",
    CorePermissions.AUDIT_READ: "Read the audit log",
    CorePermissions.LLM_READ: "Read LLM provider key metadata",
    CorePermissions.LLM_WRITE: "Manage LLM provider keys and shared-access policy",
    CorePermissions.MCP_READ: "Read MCP server connection metadata",
    CorePermissions.MCP_WRITE: "Register, enable/disable, and delete MCP server connections",
    CorePermissions.PLATFORM_HEALTH_READ: "View component inventory, currency, and vulnerability scan results",
    CorePermissions.PLATFORM_HEALTH_WRITE: "Trigger scans and decide remediation proposals",
    CorePermissions.FISMA_AUDIT_READ: "View the FISMA controls self-audit report",
}


def register(name: str, description: str = "") -> None:
    """Register a permission. Idempotent — safe to call repeatedly."""
    _registered.add(name)
    if description and name not in _descriptions:
        _descriptions[name] = description


def all_permissions() -> list[tuple[str, str]]:
    """Return every registered permission as (name, description) pairs."""
    return sorted((name, _descriptions.get(name, "")) for name in _registered)
