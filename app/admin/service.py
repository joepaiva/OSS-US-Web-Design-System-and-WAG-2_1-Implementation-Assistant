"""Admin shell service layer — async, no FastAPI imports (chassis v0.7).

Reuses auth + rbac + orgs services; adds the admin-only queries (list all
users, list an org's members, create a user as an admin, toggle active) and
the platform-admin predicate. Mutations are @audited for AU traceability.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.auth.models import User
from app.auth.service import (
    EmailAlreadyRegistered,
    get_user_by_email,
    get_user_by_id,
    hash_password,
)
from app.orgs.models import Membership, Organization
from app.rbac.models import Role, user_roles
from app.rbac.service import assign_role_to_user


class AdminError(Exception):
    """Raised for admin-shell failures the route layer maps to 4xx."""


async def is_platform_admin(session: AsyncSession, user: User) -> bool:
    """True iff the user is a superuser OR holds the chassis-wide `admin`
    role (via user_roles). This is org-independent — a platform admin need
    not belong to any org. Org-only admins (admin role via a membership)
    return False here and are scoped to their current org in the UI.
    """
    if user.is_superuser:
        return True
    stmt = (
        select(Role.id)
        .join(user_roles, user_roles.c.role_id == Role.id)
        .where(user_roles.c.user_id == user.id, Role.name == "admin")
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def list_all_users(session: AsyncSession) -> list[User]:
    """Every user, oldest first. Platform-admin view."""
    result = await session.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def list_org_member_users(session: AsyncSession, org_id: int) -> list[User]:
    """Users who are members of `org_id`, oldest first. Org-admin view."""
    stmt = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org_id)
        .order_by(User.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_all_orgs(session: AsyncSession) -> list[Organization]:
    """Every organization, oldest first. Platform-admin view."""
    result = await session.execute(select(Organization).order_by(Organization.id))
    return list(result.scalars().all())


@audited(
    "admin.user_created",
    entity_type="user",
    capture_details=lambda user: {"email": user.email},
)
async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None,
    role_name: str,
    org_id: int | None,
) -> User:
    """Create a user as an admin.

    - When `org_id` is set (org-admin path), the new user is added as a
      member of that org with the named per-org role.
    - When `org_id` is None (platform-admin path), the named role is granted
      chassis-wide via user_roles.

    Raises EmailAlreadyRegistered if the email is taken; AdminError on an
    unknown role for the org-membership path.
    """
    if await get_user_by_email(session, email) is not None:
        raise EmailAlreadyRegistered(email)

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name or None,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()

    if org_id is not None:
        role = (
            await session.execute(select(Role).where(Role.name == role_name))
        ).scalar_one_or_none()
        if role is None:
            raise AdminError(f"unknown role: {role_name}")
        session.add(
            Membership(
                user_id=user.id,
                org_id=org_id,
                role_id=role.id,
                is_default=True,
            )
        )
        await session.flush()
    else:
        await assign_role_to_user(session, user, role_name)

    return user


@audited(
    "admin.user_active_changed",
    entity_type="user",
    capture_details=lambda user: {"email": user.email, "is_active": user.is_active},
)
async def set_user_active(
    session: AsyncSession,
    user_id: int,
    active: bool,
    *,
    platform: bool,
    org_id: int | None,
) -> User:
    """Activate / deactivate a user. Raises AdminError if not found.

    FR-ADM-2: an org administrator's WRITE reach is scoped identically to
    their read reach. A platform administrator may act on any user; an org
    administrator may act ONLY on a member of their own organization.

    `platform` and `org_id` are the caller's resolved scope and are
    REQUIRED keyword arguments on purpose. This function previously took
    neither and resolved its target by primary key alone, which let an org
    administrator deactivate or reactivate any user on the platform —
    including another tenant's members — even though the admin user listing
    correctly showed them only their own org (proven by execution,
    2026-09-17). Making the scope required means a future call site cannot
    reintroduce the gap by omitting it: it fails to compile-check instead.

    A target outside the caller's organization raises AdminError("user not
    found") — the FR-TEN-7 convention of reporting cross-scope access as
    not-found rather than a distinguishable 403, which would confirm the
    account exists. The check runs BEFORE the mutation, so a refused call
    leaves the target untouched; the refusal and the non-mutation are two
    separate obligations.
    """
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise AdminError("user not found")

    if not platform:
        # Org administrator: the target MUST be a member of this org. An
        # orgless caller has no one in scope, so nothing is reachable.
        if org_id is None:
            raise AdminError("user not found")
        membership = (
            await session.execute(
                select(Membership.id)
                .where(
                    Membership.user_id == user_id,
                    Membership.org_id == org_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if membership is None:
            raise AdminError("user not found")

    user.is_active = active
    await session.flush()
    return user
