"""LLM key resolution, CRUD, and completion-transport tests (chassis v0.9)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import service
from app.llm.transport import LLMError, set_transport
from app.orgs.models import Organization


class _FakeTransport:
    """Records the api_key it was handed and returns a canned response."""

    def __init__(self, *, fail: bool = False) -> None:
        self.last_api_key: str | None = None
        self.calls = 0
        self._fail = fail

    async def chat(self, *, api_key: str, model: str, messages: Any, **kw: Any) -> dict:
        self.calls += 1
        self.last_api_key = api_key
        if self._fail:
            raise LLMError("boom")
        return {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}


@pytest.fixture(autouse=True)
def _reset_transport():
    yield
    set_transport(None)


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    org = Organization(name=slug.title(), slug=slug)
    session.add(org)
    await session.flush()
    return org


# ─── Resolution chain ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_org_key_preferred(session: AsyncSession) -> None:
    org = await _make_org(session, "orgone")
    await service.set_key(
        session, provider="anthropic", plaintext="ORG-KEY", org_id=org.id,
        created_by_user_id=None,
    )
    await service.set_key(
        session, provider="anthropic", plaintext="SHARED-KEY", org_id=None,
        created_by_user_id=None,
    )
    await session.commit()

    resolved = await service.resolve_api_key(session, provider="anthropic", org_id=org.id)
    assert resolved == "ORG-KEY"


@pytest.mark.asyncio
async def test_shared_fallback_only_when_allowed(session: AsyncSession) -> None:
    org = await _make_org(session, "orgtwo")
    await service.set_key(
        session, provider="openai", plaintext="SHARED-OAI", org_id=None,
        created_by_user_id=None,
    )
    await session.commit()

    # No policy row → shared access denied.
    with pytest.raises(service.LLMKeyUnavailable):
        await service.resolve_api_key(session, provider="openai", org_id=org.id)

    # Grant access → shared key resolves.
    await service.set_org_shared_access(session, org_id=org.id, allow=True)
    await session.commit()
    resolved = await service.resolve_api_key(session, provider="openai", org_id=org.id)
    assert resolved == "SHARED-OAI"


@pytest.mark.asyncio
async def test_no_key_raises(session: AsyncSession) -> None:
    org = await _make_org(session, "orgthree")
    await session.commit()
    with pytest.raises(service.LLMKeyUnavailable):
        await service.resolve_api_key(session, provider="gemini", org_id=org.id)


@pytest.mark.asyncio
async def test_orgless_caller_uses_shared(session: AsyncSession) -> None:
    await service.set_key(
        session, provider="anthropic", plaintext="PLATFORM", org_id=None,
        created_by_user_id=None,
    )
    await session.commit()
    resolved = await service.resolve_api_key(session, provider="anthropic", org_id=None)
    assert resolved == "PLATFORM"


@pytest.mark.asyncio
async def test_set_key_deactivates_previous(session: AsyncSession) -> None:
    org = await _make_org(session, "orgfour")
    await service.set_key(
        session, provider="anthropic", plaintext="OLD", org_id=org.id,
        created_by_user_id=None,
    )
    await service.set_key(
        session, provider="anthropic", plaintext="NEW", org_id=org.id,
        created_by_user_id=None,
    )
    await session.commit()

    resolved = await service.resolve_api_key(session, provider="anthropic", org_id=org.id)
    assert resolved == "NEW"
    # Exactly one active key remains for the scope+provider.
    views = await service.list_keys(session, org_id=org.id, include_shared=False)
    active = [v for v in views if v.is_active and v.provider == "anthropic"]
    assert len(active) == 1


@pytest.mark.asyncio
async def test_deactivated_key_not_resolved(session: AsyncSession) -> None:
    org = await _make_org(session, "orgfive")
    key = await service.set_key(
        session, provider="anthropic", plaintext="K", org_id=org.id,
        created_by_user_id=None,
    )
    await service.deactivate_key(session, key)
    await session.commit()
    with pytest.raises(service.LLMKeyUnavailable):
        await service.resolve_api_key(session, provider="anthropic", org_id=org.id)


# ─── List views ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_keys_masks_and_scopes(session: AsyncSession) -> None:
    org = await _make_org(session, "orgsix")
    await service.set_key(
        session, provider="anthropic", plaintext="sk-secret-1234", org_id=org.id,
        created_by_user_id=None,
    )
    await service.set_key(
        session, provider="openai", plaintext="sk-shared-9999", org_id=None,
        created_by_user_id=None,
    )
    await session.commit()

    views = await service.list_keys(session, org_id=org.id, include_shared=True)
    by_provider = {v.provider: v for v in views}
    assert by_provider["anthropic"].scope == "org"
    assert by_provider["anthropic"].masked == "••••1234"
    assert "sk-secret" not in by_provider["anthropic"].masked
    assert by_provider["openai"].scope == "shared"
    assert by_provider["openai"].masked == "••••9999"


# ─── Completion through transport ───────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_injects_resolved_key(session: AsyncSession) -> None:
    org = await _make_org(session, "orgseven")
    await service.set_key(
        session, provider="anthropic", plaintext="RESOLVED-KEY", org_id=org.id,
        created_by_user_id=None,
    )
    await session.commit()

    fake = _FakeTransport()
    set_transport(fake)
    result = await service.complete(
        session,
        provider="anthropic",
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "hello"}],
        org_id=org.id,
    )
    assert fake.calls == 1
    assert fake.last_api_key == "RESOLVED-KEY"
    assert result["choices"][0]["message"]["content"] == "hi"


@pytest.mark.asyncio
async def test_complete_raises_without_key(session: AsyncSession) -> None:
    org = await _make_org(session, "orgeight")
    await session.commit()
    set_transport(_FakeTransport())
    with pytest.raises(service.LLMKeyUnavailable):
        await service.complete(
            session, provider="anthropic", model="m",
            messages=[{"role": "user", "content": "x"}], org_id=org.id,
        )


@pytest.mark.asyncio
async def test_complete_propagates_transport_error(session: AsyncSession) -> None:
    await service.set_key(
        session, provider="anthropic", plaintext="K", org_id=None,
        created_by_user_id=None,
    )
    await session.commit()
    set_transport(_FakeTransport(fail=True))
    with pytest.raises(LLMError):
        await service.complete(
            session, provider="anthropic", model="m",
            messages=[{"role": "user", "content": "x"}], org_id=None,
        )


@pytest.mark.asyncio
async def test_set_key_validates_input(session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await service.set_key(
            session, provider="", plaintext="k", org_id=None, created_by_user_id=None
        )
    with pytest.raises(ValueError):
        await service.set_key(
            session, provider="anthropic", plaintext="   ", org_id=None,
            created_by_user_id=None,
        )


@pytest.mark.asyncio
async def test_audit_row_written_on_set_key(session: AsyncSession) -> None:
    from sqlalchemy import select

    from app.audit.models import AuditLog

    await service.set_key(
        session, provider="anthropic", plaintext="K", org_id=None,
        created_by_user_id=None,
    )
    await session.commit()
    rows = (
        await session.execute(select(AuditLog).where(AuditLog.action == "llm.key_set"))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].details.get("provider") == "anthropic"
