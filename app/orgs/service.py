"""Org/Membership service layer — async, no FastAPI imports."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.auth.models import User
from app.orgs.models import Membership, Organization
from app.rbac.models import Role


class OrgError(Exception):
    pass


class SlugTaken(OrgError):
    pass


class NotAMember(OrgError):
    pass


# ────────────────────────────────────────────────────────────────────────
# Org CRUD
# ────────────────────────────────────────────────────────────────────────


@audited(
    "orgs.created",
    entity_type="organization",
    capture_details=lambda org: {"name": org.name, "slug": org.slug},
)
async def create_org(
    session: AsyncSession, user: User, name: str, slug: str
) -> Organization:
    """Create a new org and make `user` the first admin member.

    The new membership is flagged `is_default=True` ONLY when the user has
    no existing memberships — otherwise the user's existing default org
    stays the default.
    """
    existing = await session.execute(select(Organization).where(Organization.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise SlugTaken(slug)

    org = Organization(name=name, slug=slug)
    session.add(org)
    await session.flush()

    # Look up the admin role so we can attach it as the per-org role.
    admin_role = (
        await session.execute(select(Role).where(Role.name == "admin"))
    ).scalar_one_or_none()

    # Is this the user's first org? If so, this membership is default.
    has_existing = (
        await session.execute(
            select(Membership.id).where(Membership.user_id == user.id).limit(1)
        )
    ).scalar_one_or_none() is not None

    membership = Membership(
        user_id=user.id,
        org_id=org.id,
        role_id=admin_role.id if admin_role else None,
        is_default=not has_existing,
    )
    session.add(membership)
    await session.flush()
    return org


async def list_orgs_for_user(
    session: AsyncSession, user: User
) -> list[Organization]:
    """Return the user's orgs (those they have a membership in)."""
    stmt = (
        select(Organization)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_default_org_for_user(
    session: AsyncSession, user: User
) -> Organization | None:
    """Resolve the user's current default org.

    Lookup precedence:
      1. Membership with `is_default=True`
      2. Lowest membership id (oldest membership)
      3. None (user has no orgs)
    """
    stmt = (
        select(Organization)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Membership.is_default.desc(), Membership.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@audited(
    "orgs.default_switched",
    entity_type="organization",
    capture_details=lambda org: {"slug": org.slug},
)
async def switch_default_org(
    session: AsyncSession, user: User, target_org_id: int
) -> Organization:
    """Flip the user's default-org membership to `target_org_id`.

    Raises NotAMember if the user has no membership in the target org.
    """
    # Verify membership.
    member_check = await session.execute(
        select(Membership.id).where(
            Membership.user_id == user.id, Membership.org_id == target_org_id
        )
    )
    if member_check.scalar_one_or_none() is None:
        raise NotAMember(f"user {user.id} not a member of org {target_org_id}")

    # Clear is_default on all memberships for this user.
    await session.execute(
        update(Membership)
        .where(Membership.user_id == user.id)
        .values(is_default=False)
    )
    # Set is_default on the target membership.
    await session.execute(
        update(Membership)
        .where(Membership.user_id == user.id, Membership.org_id == target_org_id)
        .values(is_default=True)
    )

    org = (
        await session.execute(select(Organization).where(Organization.id == target_org_id))
    ).scalar_one_or_none()
    if org is None:
        # Defensive: should be unreachable given the membership check above.
        raise OrgError(f"org {target_org_id} not found")
    return org
