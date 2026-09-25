"""Admin shell tests (chassis v0.7).

Covers the RBAC gate (unauthenticated → login redirect; regular user → 403;
org admin → users yes / orgs no; platform admin → full access) and the core
mutations (create user, deactivate/reactivate, can't-deactivate-self, create
org). Server-rendered HTML routes, so assertions check status codes + page text.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from tests.conftest import make_org, make_user


async def _promote_to_superuser(session: AsyncSession, user_id: int) -> None:
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one()
    user.is_superuser = True
    # IA-2(1) (chassis-program v1.0.0): superusers are privileged accounts
    # and MUST have MFA enrolled to use any admin-gated route — set the
    # flag directly here rather than exercising the real enroll/confirm
    # HTTP flow, since these tests aren't exercising MFA itself.
    user.mfa_enabled = True
    await session.commit()


async def _get_user(session: AsyncSession, email: str) -> User:
    # Expire the identity map so we re-read committed state written by the
    # request's separate session (avoids stale is_active reads).
    session.expire_all()
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()


@pytest.mark.asyncio
async def test_unauthenticated_redirects_to_login(client: AsyncClient) -> None:
    resp = await client.get("/admin")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_regular_user_is_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg@example.com")
    resp = await client.get("/admin", headers=u["headers"])
    assert resp.status_code == 403
    assert "Access denied" in resp.text


@pytest.mark.asyncio
async def test_org_admin_sees_users_but_not_orgs(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin@example.com")
    await make_org(client, u["headers"], name="Acme", slug="acme")

    r_users = await client.get("/admin/users", headers=u["headers"])
    assert r_users.status_code == 200
    assert "orgadmin@example.com" in r_users.text

    # Org Management is platform-admin only.
    r_orgs = await client.get("/admin/orgs", headers=u["headers"])
    assert r_orgs.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_has_full_access(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super@example.com")
    await _promote_to_superuser(session, int(u["user"]["id"]))  # type: ignore[index]

    assert (await client.get("/admin", headers=u["headers"])).status_code == 200
    assert (await client.get("/admin/users", headers=u["headers"])).status_code == 200
    r_orgs = await client.get("/admin/orgs", headers=u["headers"])
    assert r_orgs.status_code == 200


@pytest.mark.asyncio
async def test_platform_admin_creates_and_deactivates_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super2@example.com")
    await _promote_to_superuser(session, int(u["user"]["id"]))  # type: ignore[index]

    # Create a user via the admin form.
    r = await client.post(
        "/admin/users",
        headers=u["headers"],
        data={
            "email": "newbie@example.com",
            "password": "NewbiePass123!",
            "full_name": "New Bie",
            "role": "user",
        },
    )
    assert r.status_code == 303
    listing = await client.get("/admin/users", headers=u["headers"])
    assert "newbie@example.com" in listing.text

    newbie = await _get_user(session, "newbie@example.com")
    assert newbie.is_active is True

    # Deactivate.
    r2 = await client.post(
        f"/admin/users/{newbie.id}/deactivate", headers=u["headers"]
    )
    assert r2.status_code == 303
    refreshed = await _get_user(session, "newbie@example.com")
    assert refreshed.is_active is False

    # Reactivate.
    r3 = await client.post(
        f"/admin/users/{newbie.id}/reactivate", headers=u["headers"]
    )
    assert r3.status_code == 303
    refreshed2 = await _get_user(session, "newbie@example.com")
    assert refreshed2.is_active is True


@pytest.mark.asyncio
async def test_duplicate_email_rejected(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super5@example.com")
    await _promote_to_superuser(session, int(u["user"]["id"]))  # type: ignore[index]
    r = await client.post(
        "/admin/users",
        headers=u["headers"],
        data={"email": "super5@example.com", "password": "X1234567!", "role": "user"},
    )
    assert r.status_code == 409
    assert "already exists" in r.text


@pytest.mark.asyncio
async def test_cannot_deactivate_self(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super3@example.com")
    uid = int(u["user"]["id"])  # type: ignore[index]
    await _promote_to_superuser(session, uid)
    r = await client.post(f"/admin/users/{uid}/deactivate", headers=u["headers"])
    assert r.status_code == 400
    assert "your own account" in r.text


@pytest.mark.asyncio
async def test_platform_admin_creates_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super4@example.com")
    await _promote_to_superuser(session, int(u["user"]["id"]))  # type: ignore[index]
    r = await client.post(
        "/admin/orgs",
        headers=u["headers"],
        data={"name": "Globex", "slug": "globex"},
    )
    assert r.status_code == 303
    listing = await client.get("/admin/orgs", headers=u["headers"])
    assert "globex" in listing.text

@pytest.mark.asyncio
async def test_org_admin_cannot_mutate_other_org_member(
    client: AsyncClient, session: AsyncSession
) -> None:
    """TS-ADM: an org admin MUST NOT be able to deactivate another org's member.

    The read side of this is already covered (an org admin's /admin/users
    listing shows only their own org). The MUTATION side was not: the
    deactivate/reactivate route authorizes on the `users:write` permission,
    which an org admin holds, and the target user is resolved by primary key.
    Without an explicit membership check that is a cross-tenant privilege
    escalation, so this test asserts BOTH halves — the refusal status AND that
    the target's state did not change. Asserting only the status would pass
    against a handler that mutates first and refuses afterwards.

    Cross-tenant access is "not found", never a distinguishable 403 — the
    same rule the sibling Node/.NET/Go chassis enforce.
    """
    # Org A's admin.
    a = await make_user(client, email="a-admin@example.com")
    await make_org(client, a["headers"], name="Org A", slug="org-a")

    # A member of a DIFFERENT org — not merely an orgless user, which a guard
    # that only tested "has any membership" would wrongly survive.
    await make_user(client, email="b-member@example.com")
    b_headers = (await make_user(client, email="b-admin@example.com"))["headers"]
    await make_org(client, b_headers, name="Org B", slug="org-b")

    target = await _get_user(session, "b-member@example.com")
    assert target.is_active is True

    # Deactivate must be refused AND must not take effect.
    resp = await client.post(
        f"/admin/users/{target.id}/deactivate", headers=a["headers"]
    )
    assert resp.status_code == 404, (
        f"org admin reached another org's member: got {resp.status_code}"
    )
    assert (await _get_user(session, "b-member@example.com")).is_active is True

    # Reactivate is the same surface and must be refused the same way. A guard
    # placed on only one of the two verbs is the likelier bug.
    resp2 = await client.post(
        f"/admin/users/{target.id}/reactivate", headers=a["headers"]
    )
    assert resp2.status_code == 404
