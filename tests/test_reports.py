"""Admin reporting tests (chassis v0.10) — RBAC gate + scoped counts."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.reports_service import gather_report
from app.auth.models import User
from app.notifications import service as notif_service
from tests.conftest import make_org, make_user


async def _promote_to_superuser(session: AsyncSession, email: str) -> None:
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.is_superuser = True
    # IA-2(1) (chassis-program v1.0.0): superusers are privileged accounts
    # and MUST have MFA enrolled to use any admin-gated route.
    user.mfa_enabled = True
    await session.commit()


@pytest.mark.asyncio
async def test_unauthenticated_redirects(client: AsyncClient) -> None:
    resp = await client.get("/admin/reports")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_regular_user_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-rep@example.com")
    resp = await client.get("/admin/reports", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_sees_org_scoped_report(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-rep@example.com")
    await make_org(client, u["headers"], name="RepOrg", slug="reporg")
    resp = await client.get("/admin/reports", headers=u["headers"])
    assert resp.status_code == 200
    assert "Reports" in resp.text
    assert "your organization" in resp.text
    # Org-scoped report hides the platform-wide org count card.
    assert "Organizations" not in resp.text


@pytest.mark.asyncio
async def test_platform_admin_sees_global_report(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="super-rep@example.com")
    await _promote_to_superuser(session, "super-rep@example.com")
    resp = await client.get("/admin/reports", headers=u["headers"])
    assert resp.status_code == 200
    assert "all organizations" in resp.text
    assert "Organizations" in resp.text  # platform card shown


@pytest.mark.asyncio
async def test_gather_report_counts(client: AsyncClient, session: AsyncSession) -> None:
    u = await make_user(client, email="rep-counts@example.com")
    org = await make_org(client, u["headers"], name="CountOrg", slug="countorg")
    uid = (
        await session.execute(
            select(User.id).where(User.email == "rep-counts@example.com")
        )
    ).scalar_one()
    # Seed a notification scoped to the org.
    await notif_service.notify(
        session, user_id=uid, title="hi", org_id=org["id"]
    )
    await session.commit()

    org_report = await gather_report(session, org_id=org["id"], platform=False)
    assert org_report.scope == "organization"
    assert org_report.users_total >= 1
    assert org_report.notifications_total == 1

    # Org creation emits an audited "orgs.created" event (NULL org_id, so it
    # surfaces in the platform-wide report, not the org-scoped one).
    platform_report = await gather_report(session, org_id=None, platform=True)
    assert platform_report.scope == "platform"
    assert platform_report.audit_total >= 1
    assert any(a == "orgs.created" for a, _ in platform_report.audit_top_actions)
    assert platform_report.orgs_total >= 1
