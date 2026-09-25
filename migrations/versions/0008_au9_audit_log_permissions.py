"""au-9: REVOKE UPDATE/DELETE on audit_logs from app_user (chassis v0.6)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-05

NIST 800-53 AU-9 (Protection of Audit Information) compliance: audit
records must be protected from unauthorized modification or deletion.

The chassis convention is "append-only by code policy" (NEVER UPDATE,
NEVER DELETE in app/audit/), but defense-in-depth requires enforcing
this at the database layer: even if a slot author or an attacker
bypasses the chassis service layer, the database itself refuses
UPDATE and DELETE on the audit_logs table from the application's
DB role.

This migration applies that REVOKE if-and-only-if the application's
DB role exists. By default the role is named "app_user" but operators
can override via the AU9_APP_ROLE environment variable to match their
deploy convention (e.g., "chassis_app", "myapp_prod_role"). If no
matching role exists at migration time, this migration is a no-op +
WARNING log — operators should then run the REVOKE manually as a
post-deploy task.

The migration also issues:
  GRANT SELECT, INSERT ON audit_logs TO :role;

so the application can still read + append (via the @audited decorator).
We REVOKE UPDATE, DELETE but NOT TRUNCATE — TRUNCATE is a chassis-admin
op that operators may still need for development resets; production
should disable TRUNCATE via a separate trigger or by removing the
psql admin role from app_user.

The companion audit_logs_archive table (migration 0007) is
intentionally NOT protected by this REVOKE — the archival job (running
as app_user) needs INSERT and the archive is the cold storage that
operators may need to query/extract for compliance reporting. The
chassis-wide pattern of "never UPDATE, never DELETE archived records"
is enforced by the same code-level convention as audit_logs.

Downgrade restores the original full GRANTs (slot authors should not
rely on this being executed — production environments should treat
the GRANTs as a one-way migration).
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role_name() -> str:
    """Read the app DB role name from the env, falling back to 'app_user'."""
    return os.environ.get("AU9_APP_ROLE", "app_user").strip() or "app_user"


def _role_exists(role: str) -> bool:
    """Return True if a PostgreSQL role with this name is defined."""
    result = op.get_bind().exec_driver_sql(
        "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
    )
    return result.first() is not None


def upgrade() -> None:
    role = _role_name()
    if not _role_exists(role):
        # No matching role — log a warning and document the manual step.
        # Alembic doesn't provide an "official" warning mechanism; we use
        # print so it shows up in operator output during the migration.
        import warnings

        warnings.warn(
            f"\n"
            f"[AU-9 chassis v0.6] Migration 0008 found no PostgreSQL role "
            f"named '{role}'. To complete AU-9 compliance, the operator "
            f"MUST run the following SQL after deploy as the database "
            f"superuser:\n\n"
            f"    REVOKE UPDATE, DELETE ON audit_logs FROM {role};\n"
            f"    GRANT SELECT, INSERT ON audit_logs TO {role};\n\n"
            f"Override the role name with AU9_APP_ROLE env var if your "
            f"deploy uses a different convention.",
            UserWarning,
            stacklevel=2,
        )
        return

    # Apply the AU-9 protection.
    op.execute(f"GRANT SELECT, INSERT ON audit_logs TO {role};")
    op.execute(f"REVOKE UPDATE, DELETE ON audit_logs FROM {role};")
    # The archive table stays writable for the archival job; SELECT also
    # granted so operators can read it directly via psql if needed.
    op.execute(f"GRANT SELECT, INSERT ON audit_logs_archive TO {role};")


def downgrade() -> None:
    role = _role_name()
    if not _role_exists(role):
        return
    # Restore the role's full privileges. Production environments should
    # NEVER need to downgrade this; it's documented for completeness.
    op.execute(f"GRANT UPDATE, DELETE ON audit_logs TO {role};")
    op.execute(f"GRANT UPDATE, DELETE ON audit_logs_archive TO {role};")
