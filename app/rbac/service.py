"""RBAC service layer — async methods, no FastAPI imports.

Authorization decision logic:
  - Superusers always pass.
  - Otherwise: user has the permission IF any of their roles grants it.

Role/permission seeding:
  - `seed_chassis_rbac` upserts every CorePermissions entry into the
    `permissions` table and creates the `admin` and `user` roles. Called
    once at app startup; idempotent.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import User
from app.db import current_org_id_var
from app.rbac.models import Permission, Role, role_permissions, user_roles
from app.rbac.permissions import CorePermissions, all_permissions


class RBACError(Exception):
    pass


class PermissionDenied(RBACError):
    pass


# ────────────────────────────────────────────────────────────────────────
# Authorization
# ────────────────────────────────────────────────────────────────────────


async def user_has_permission(
    session: AsyncSession, user: User, permission_name: str
) -> bool:
    """Return True iff the user has the named permission.

    Chassis RBAC has TWO grant paths:
      1. Chassis-wide roles (`user_roles` table) — apply across all orgs.
         Use for platform admin / superuser / default-user grants.
      2. Per-org roles (`memberships.role_id`) — only count when the
         current org context matches the membership's org. Use for
         "this user is admin in this org but not others".

    The check inspects both. Superusers short-circuit to True.

    Membership import is lazy to break the rbac↔orgs cycle (orgs.service
    imports rbac.models for the admin Role; rbac.service would otherwise
    pull orgs.models in at module import time).
    """
    if user.is_superuser:
        return True

    # Path 1: chassis-wide via user_roles.
    chassis_stmt = (
        select(Permission.id)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .where(user_roles.c.user_id == user.id, Permission.name == permission_name)
        .limit(1)
    )
    if (await session.execute(chassis_stmt)).scalar_one_or_none() is not None:
        return True

    # Path 2: per-org via memberships.role_id, only if a current org is bound.
    current_org_id = current_org_id_var.get(None)
    if current_org_id is None:
        return False

    from app.orgs.models import Membership  # lazy import to break rbac↔orgs cycle

    org_stmt = (
        select(Permission.id)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(Membership, Membership.role_id == role_permissions.c.role_id)
        .where(
            Membership.user_id == user.id,
            Membership.org_id == current_org_id,
            Permission.name == permission_name,
        )
        .limit(1)
    )
    return (await session.execute(org_stmt)).scalar_one_or_none() is not None


async def is_privileged_user(session: AsyncSession, user: User) -> bool:
    """Return True iff `user` is a PLATFORM-level privileged account —
    `is_superuser`, or holding the `admin` role chassis-wide (user_roles).

    Used exclusively by app/deps.py's `requires()` and
    app/admin/routes.py's `_resolve()` for the MFA-mandate gate (IA-2(1),
    FISMA-Moderate): a privileged user is required to have `mfa_enabled`
    before a permission-gated action succeeds.

    Deliberately scoped to PLATFORM-wide privilege only, not per-org
    membership. The chassis auto-grants the `admin` role to a user within
    the org they create (see app/orgs/service.py:create_org), which would
    otherwise make every tenant's very first user "privileged" and force
    MFA on ordinary multi-tenant onboarding — a materially different, much
    larger product decision than closing the platform's actual MFA gap
    (SECURITY-SELF-AUDIT.md's "Gap for FISMA Moderate" note has always
    been about system/platform-administrator-class accounts). IA-2(1)'s
    "privileged account" reading, and this program's own FISMA delta doc,
    are both satisfied by scoping to platform-wide `admin`/superuser; a
    per-org admin who ALSO holds platform-wide admin is still covered via
    the `is_superuser`/chassis-wide-role check above.
    """
    if user.is_superuser:
        return True

    chassis_stmt = (
        select(Role.id)
        .join(user_roles, user_roles.c.role_id == Role.id)
        .where(user_roles.c.user_id == user.id, Role.name == "admin")
        .limit(1)
    )
    return (await session.execute(chassis_stmt)).scalar_one_or_none() is not None


async def user_permission_names(session: AsyncSession, user: User) -> set[str]:
    """Return the set of permission names this user has across all roles.

    For superusers, returns the universe of permissions (every row in
    `permissions`). For everyone else: only the names granted by their
    assigned roles.
    """
    if user.is_superuser:
        result = await session.execute(select(Permission.name))
        return set(result.scalars().all())

    stmt = (
        select(Permission.name)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .where(user_roles.c.user_id == user.id)
    )
    result = await session.execute(stmt)
    return set(result.scalars().all())


# ────────────────────────────────────────────────────────────────────────
# Seeding
# ────────────────────────────────────────────────────────────────────────


async def seed_chassis_rbac(session: AsyncSession) -> None:
    """Ensure all chassis permissions + admin/user roles exist. Idempotent.

    Called once at app startup. Safe to call multiple times.
    """
    # Upsert permissions.
    existing_perms = await session.execute(select(Permission.name))
    existing_perm_names = set(existing_perms.scalars().all())
    new_perms: list[Permission] = []
    for name, description in all_permissions():
        if name not in existing_perm_names:
            new_perms.append(Permission(name=name, description=description or None))
    if new_perms:
        session.add_all(new_perms)
        await session.flush()

    # Upsert roles.
    admin = await _get_or_create_role(session, "admin", "Full access including future slots.")
    user_role = await _get_or_create_role(session, "user", "Read-only on owned resources.")

    # Re-fetch all permissions WITH their roles eagerly loaded so we can
    # mutate the .roles collection without lazy-IO surprises.
    perm_result = await session.execute(
        select(Permission).options(selectinload(Permission.roles))
    )
    all_perms = list(perm_result.scalars().all())

    # Grant ALL permissions to admin.
    for perm in all_perms:
        if admin not in perm.roles:
            perm.roles.append(admin)

    # Grant a minimal read-only set to the `user` role.
    user_grants = {
        CorePermissions.USERS_READ,
        CorePermissions.ORGS_READ,
    }
    for perm in all_perms:
        if perm.name in user_grants and user_role not in perm.roles:
            perm.roles.append(user_role)

    await session.flush()


async def _get_or_create_role(
    session: AsyncSession, name: str, description: str
) -> Role:
    result = await session.execute(select(Role).where(Role.name == name))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=description)
        session.add(role)
        await session.flush()
    return role


async def assign_role_to_user(session: AsyncSession, user: User, role_name: str) -> None:
    """Grant a role to a user. Raises RBACError if role doesn't exist. Idempotent."""
    result = await session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if role is None:
        raise RBACError(f"unknown role: {role_name}")

    existing = await session.execute(
        select(user_roles.c.user_id).where(
            user_roles.c.user_id == user.id, user_roles.c.role_id == role.id
        )
    )
    if existing.scalar_one_or_none() is None:
        await session.execute(
            user_roles.insert().values(user_id=user.id, role_id=role.id)
        )
