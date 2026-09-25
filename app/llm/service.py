"""LLM service — key resolution, key management, and completions (v0.9).

Resolution chain (Rule-7 parity):
    org-scoped active key → platform-shared active key (iff org policy
    allows) → raise LLMKeyUnavailable.

A caller with no org (`org_id=None`) is a platform-context call and may use
the shared key directly. An org-scoped caller may use the shared key ONLY
when an `OrgLLMAccess` row grants it — absence of a row means deny.

All mutations are @audited. Plaintext keys exist only transiently in this
module (encrypt on write, decrypt on resolve); the DB holds ciphertext only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.llm.crypto import DecryptionError, decrypt, encrypt, mask
from app.llm.models import LLMProviderKey, OrgLLMAccess
from app.llm.transport import get_transport
from app.logging import get_logger

log = get_logger("llm.service")


class LLMKeyUnavailable(Exception):
    """No usable API key could be resolved for the requested provider/org."""


@dataclass(frozen=True)
class KeyView:
    """Admin-display row for a stored key (never carries the plaintext)."""

    id: int
    provider: str
    scope: str  # "shared" or "org"
    organization_id: int | None
    is_active: bool
    masked: str


# ─── Resolution ─────────────────────────────────────────────────────────


async def _active_key(
    session: AsyncSession, *, provider: str, org_id: int | None
) -> LLMProviderKey | None:
    """Most-recent active key for an exact scope (org_id may be None)."""
    stmt = (
        select(LLMProviderKey)
        .where(
            LLMProviderKey.provider == provider,
            LLMProviderKey.is_active.is_(True),
            LLMProviderKey.organization_id.is_(None)
            if org_id is None
            else LLMProviderKey.organization_id == org_id,
        )
        .order_by(LLMProviderKey.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def org_allows_shared(session: AsyncSession, org_id: int) -> bool:
    """True iff a policy row grants this org shared-key access (default deny)."""
    stmt = select(OrgLLMAccess.allow_shared_key).where(
        OrgLLMAccess.organization_id == org_id
    )
    result = (await session.execute(stmt)).scalar_one_or_none()
    return bool(result)


async def resolve_api_key(
    session: AsyncSession, *, provider: str, org_id: int | None
) -> str:
    """Resolve the plaintext API key per the Rule-7 chain. Raises
    LLMKeyUnavailable when nothing usable is found."""
    if org_id is not None:
        org_key = await _active_key(session, provider=provider, org_id=org_id)
        if org_key is not None:
            return decrypt(org_key.encrypted_key)

    if org_id is None or await org_allows_shared(session, org_id):
        shared = await _active_key(session, provider=provider, org_id=None)
        if shared is not None:
            return decrypt(shared.encrypted_key)

    raise LLMKeyUnavailable(
        f"no active key for provider '{provider}'"
        + ("" if org_id is None else f" (org {org_id}); shared access denied or unset")
    )


# ─── Key management (CRUD) ──────────────────────────────────────────────


async def _deactivate_existing(
    session: AsyncSession, *, provider: str, org_id: int | None
) -> None:
    """Deactivate any currently-active keys for the same scope+provider so
    that at most one key per (scope, provider) is active."""
    stmt = select(LLMProviderKey).where(
        LLMProviderKey.provider == provider,
        LLMProviderKey.is_active.is_(True),
        LLMProviderKey.organization_id.is_(None)
        if org_id is None
        else LLMProviderKey.organization_id == org_id,
    )
    for key in (await session.execute(stmt)).scalars().all():
        key.is_active = False
    await session.flush()


@audited(
    "llm.key_set",
    entity_type="llm_provider_key",
    capture_details=lambda k: {
        "provider": k.provider,
        "scope": "shared" if k.organization_id is None else "org",
        "organization_id": k.organization_id,
    },
)
async def set_key(
    session: AsyncSession,
    *,
    provider: str,
    plaintext: str,
    org_id: int | None,
    created_by_user_id: int | None,
) -> LLMProviderKey:
    """Store a new active key (org-scoped when org_id set, else shared),
    deactivating any prior active key for the same scope+provider."""
    provider = provider.strip().lower()
    if not provider:
        raise ValueError("provider is required")
    if not plaintext.strip():
        raise ValueError("API key is required")

    await _deactivate_existing(session, provider=provider, org_id=org_id)
    key = LLMProviderKey(
        organization_id=org_id,
        provider=provider,
        encrypted_key=encrypt(plaintext.strip()),
        is_active=True,
        created_by_user_id=created_by_user_id,
    )
    session.add(key)
    await session.flush()
    return key


@audited(
    "llm.key_deactivated",
    entity_type="llm_provider_key",
    capture_details=lambda k: {"provider": k.provider, "key_id": k.id},
)
async def deactivate_key(session: AsyncSession, key: LLMProviderKey) -> LLMProviderKey:
    """Mark a key inactive. Caller is responsible for authorization."""
    key.is_active = False
    await session.flush()
    return key


async def get_key(session: AsyncSession, key_id: int) -> LLMProviderKey | None:
    return await session.get(LLMProviderKey, key_id)


async def list_keys(
    session: AsyncSession, *, org_id: int | None, include_shared: bool
) -> list[KeyView]:
    """Return display rows. `org_id` selects an org's keys; `include_shared`
    additionally includes platform-shared keys (platform-admin view)."""
    conds = []
    if org_id is not None:
        conds.append(LLMProviderKey.organization_id == org_id)
    if include_shared:
        conds.append(LLMProviderKey.organization_id.is_(None))
    if not conds:
        return []

    from sqlalchemy import or_

    stmt = (
        select(LLMProviderKey)
        .where(or_(*conds))
        .order_by(LLMProviderKey.organization_id.is_(None).desc(), LLMProviderKey.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    views: list[KeyView] = []
    for k in rows:
        try:
            masked = mask(decrypt(k.encrypted_key))
        except DecryptionError:
            masked = "(unreadable — wrong key?)"
        views.append(
            KeyView(
                id=k.id,
                provider=k.provider,
                scope="shared" if k.organization_id is None else "org",
                organization_id=k.organization_id,
                is_active=k.is_active,
                masked=masked,
            )
        )
    return views


@audited(
    "llm.shared_access_set",
    entity_type="org_llm_access",
    capture_details=lambda a: {
        "organization_id": a.organization_id,
        "allow_shared_key": a.allow_shared_key,
    },
)
async def set_org_shared_access(
    session: AsyncSession, *, org_id: int, allow: bool
) -> OrgLLMAccess:
    """Upsert the per-org shared-key access policy (platform-admin action)."""
    stmt = select(OrgLLMAccess).where(OrgLLMAccess.organization_id == org_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = OrgLLMAccess(organization_id=org_id, allow_shared_key=allow)
        session.add(row)
    else:
        row.allow_shared_key = allow
    await session.flush()
    return row


async def list_org_access(session: AsyncSession) -> dict[int, bool]:
    """org_id → allow_shared_key for every org with a policy row."""
    rows = (await session.execute(select(OrgLLMAccess))).scalars().all()
    return {r.organization_id: r.allow_shared_key for r in rows}


# ─── Completion ─────────────────────────────────────────────────────────


async def complete(
    session: AsyncSession,
    *,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    org_id: int | None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Resolve a key and run a chat completion through the transport.

    Raises LLMKeyUnavailable if no key resolves; LLMError on transport
    failure. The plaintext key is never logged or returned.
    """
    api_key = await resolve_api_key(session, provider=provider.strip().lower(), org_id=org_id)
    return await get_transport().chat(
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **extra,
    )
