"""Org routes — create, list-mine, current, switch.

Per ARCHITECTURE.md, these endpoints sit ABOVE the multi-tenant filter:
they list/operate on the user's own membership set, which is intentionally
NOT filtered by current org context.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.db import SessionDep
from app.deps import CurrentUser
from app.logging import get_logger
from app.orgs.schemas import OrgCreate, OrgRead, SwitchOrgRequest
from app.orgs.service import (
    NotAMember,
    SlugTaken,
    create_org,
    get_default_org_for_user,
    list_orgs_for_user,
    switch_default_org,
)

log = get_logger("orgs")

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.post(
    "",
    response_model=OrgRead,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    payload: OrgCreate, user: CurrentUser, session: SessionDep
) -> OrgRead:
    """Create a new org. The creator becomes the first admin member.

    Returns 409 if the slug is already taken.
    """
    try:
        org = await create_org(session, user, payload.name, payload.slug)
    except SlugTaken as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"slug already taken: {payload.slug}",
        ) from exc
    log.info("orgs.create.success", org_id=org.id, slug=org.slug, creator_id=user.id)
    return OrgRead.model_validate(org)


@router.get("", response_model=list[OrgRead])
async def list_mine(user: CurrentUser, session: SessionDep) -> list[OrgRead]:
    """List the user's orgs (those they have a membership in)."""
    orgs = await list_orgs_for_user(session, user)
    return [OrgRead.model_validate(o) for o in orgs]


@router.get("/me", response_model=OrgRead | None)
async def my_default_org(
    user: CurrentUser, session: SessionDep
) -> OrgRead | None:
    """Return the user's current default org. None if no memberships."""
    org = await get_default_org_for_user(session, user)
    return OrgRead.model_validate(org) if org is not None else None


@router.put("/me", response_model=OrgRead)
async def switch_my_default_org(
    payload: SwitchOrgRequest, user: CurrentUser, session: SessionDep
) -> OrgRead:
    """Flip the user's default-org flag to `payload.org_id`.

    Returns 403 if the user has no membership in the target org.
    """
    try:
        org = await switch_default_org(session, user, payload.org_id)
    except NotAMember as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of target org",
        ) from exc
    log.info("orgs.switch_default.success", user_id=user.id, org_id=org.id)
    return OrgRead.model_validate(org)
