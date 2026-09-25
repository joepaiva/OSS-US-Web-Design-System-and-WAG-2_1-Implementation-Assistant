"""LLM admin page tests (chassis v0.9) — RBAC gates + key/access flows."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.db import get_sessionmaker
from app.llm.models import LLMProviderKey, OrgLLMAccess
from tests.conftest import make_org, make_user


async def _fetch_keys(provider: str) -> list[LLMProviderKey]:
    """Read keys in a short-lived session so we never hold a transaction
    open across `client` requests (which share the connection pool)."""
    async with get_sessionmaker()() as s:
        return list(
            (
                await s.execute(
                    select(LLMProviderKey).where(LLMProviderKey.provider == provider)
                )
            ).scalars().all()
        )


async def _fetch_access(org_id: int) -> OrgLLMAccess | None:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                select(OrgLLMAccess).where(OrgLLMAccess.organization_id == org_id)
            )
        ).scalar_one_or_none()


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
async def test_unauthenticated_redirects_to_login(client: AsyncClient) -> None:
    resp = await client.get("/admin/llm")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_regular_user_is_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-llm@example.com")
    resp = await client.get("/admin/llm", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_org_admin_can_add_and_deactivate_org_key(
    client: AsyncClient, session: AsyncSession
) -> None:
    u = await make_user(client, email="orgadmin-llm@example.com")
    await make_org(client, u["headers"], name="LlmOrg", slug="llmorg")

    # Page loads.
    page = await client.get("/admin/llm", headers=u["headers"])
    assert page.status_code == 200
    assert "Organization keys" in page.text

    # Add an org key.
    resp = await client.post(
        "/admin/llm/keys",
        data={"provider": "anthropic", "api_key": "sk-org-abcd1234", "scope": "org"},
        headers=u["headers"],
    )
    assert resp.status_code in (200, 303)

    keys = await _fetch_keys("anthropic")
    assert len(keys) == 1
    assert keys[0].organization_id is not None
    assert keys[0].is_active is True
    assert keys[0].encrypted_key != "sk-org-abcd1234"  # stored encrypted
    key_id = keys[0].id

    # Masked key shown, plaintext never present.
    page = await client.get("/admin/llm", headers=u["headers"])
    assert "••••1234" in page.text
    assert "sk-org-abcd1234" not in page.text

    # Deactivate it.
    resp = await client.post(
        f"/admin/llm/keys/{key_id}/deactivate", headers=u["headers"]
    )
    assert resp.status_code in (200, 303)
    keys = await _fetch_keys("anthropic")
    assert keys[0].is_active is False


@pytest.mark.asyncio
async def test_org_admin_cannot_set_shared_key(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-noshared@example.com")
    await make_org(client, u["headers"], name="NoShared", slug="noshared")
    resp = await client.post(
        "/admin/llm/keys",
        data={"provider": "openai", "api_key": "sk-x", "scope": "shared"},
        headers=u["headers"],
    )
    assert resp.status_code == 403
    assert "platform admins" in resp.text.lower()


@pytest.mark.asyncio
async def test_org_admin_does_not_see_shared_or_policy(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-hidden@example.com")
    await make_org(client, u["headers"], name="Hidden", slug="hidden")
    page = await client.get("/admin/llm", headers=u["headers"])
    assert "Platform-shared keys" not in page.text
    assert "Shared-key access policy" not in page.text


@pytest.mark.asyncio
async def test_platform_admin_sets_shared_key_and_policy(
    client: AsyncClient, session: AsyncSession
) -> None:
    # Build the target org via a separate org admin.
    other = await make_user(client, email="targetorg@example.com")
    target_org = await make_org(client, other["headers"], name="Target", slug="target")
    target_id = target_org["id"]

    # Platform admin.
    admin = await make_user(client, email="super-llm@example.com")
    await _promote_to_superuser(session, "super-llm@example.com")

    page = await client.get("/admin/llm", headers=admin["headers"])
    assert page.status_code == 200
    assert "Platform-shared keys" in page.text
    assert "Shared-key access policy" in page.text

    # Set a shared key.
    resp = await client.post(
        "/admin/llm/keys",
        data={"provider": "anthropic", "api_key": "sk-shared-zzzz9999", "scope": "shared"},
        headers=admin["headers"],
    )
    assert resp.status_code in (200, 303)
    async with get_sessionmaker()() as s:
        shared = (
            await s.execute(
                select(LLMProviderKey).where(LLMProviderKey.organization_id.is_(None))
            )
        ).scalars().all()
    assert len(shared) == 1

    # Grant the target org shared access.
    resp = await client.post(
        "/admin/llm/access",
        data={"org_id_target": str(target_id), "allow": "on"},
        headers=admin["headers"],
    )
    assert resp.status_code in (200, 303)
    access = await _fetch_access(target_id)
    assert access is not None and access.allow_shared_key is True

    # Revoke (allow absent).
    resp = await client.post(
        "/admin/llm/access",
        data={"org_id_target": str(target_id)},
        headers=admin["headers"],
    )
    assert resp.status_code in (200, 303)
    access = await _fetch_access(target_id)
    assert access is not None and access.allow_shared_key is False


@pytest.mark.asyncio
async def test_org_admin_cannot_set_access_policy(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-nopolicy@example.com")
    org = await make_org(client, u["headers"], name="NoPolicy", slug="nopolicy")
    resp = await client.post(
        "/admin/llm/access",
        data={"org_id_target": str(org["id"]), "allow": "on"},
        headers=u["headers"],
    )
    assert resp.status_code == 403
