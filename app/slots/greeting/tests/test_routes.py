"""Greeting slot tests — implements the scenarios TEST-SCENARIOS.md's
draft specifies, per its "both floors" discipline (Floor 1:
architecture-derived auth/permission/tenancy/validation gates every
endpoint needs; Floor 2: domain-derived scenarios specific to this
slot's behavior), covering FR-001..005, BR-001..004, and the two
chassis-program adaptations (real MFA gate, LLM translation path).

Chassis-derived scenarios (auth mechanism itself, tenancy mechanism
itself) are NOT re-tested here — only that this slot correctly USES them.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import service as llm_service
from app.llm.transport import LLMError, set_transport

# ────────────────────────────────────────────────────────────────────────
# FR-001 — authenticated greeting, happy path + validation + auth
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greeting_happy_path(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "es-ES"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["locale"] == "es-ES"
    assert data["locale_fallback"] is False
    assert data["translation_source"] == "static"
    assert "Ada" in data["greeting"]


@pytest.mark.asyncio
async def test_greeting_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/greetings", json={"name": "Ada", "locale": "en-US"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_greeting_empty_name_is_400_validation_failed(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    """NFR-004 closed error-code set — 400, not FastAPI's default 422."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "   ", "locale": "en-US"}, headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_greeting_name_over_100_chars_is_400(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "x" * 101, "locale": "en-US"}, headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_greeting_name_exactly_100_chars_succeeds(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "x" * 100, "locale": "en-US"}, headers=headers
    )
    assert resp.status_code == 200, resp.text


# ────────────────────────────────────────────────────────────────────────
# FR-002/FR-003 — locale fallback + the fixed six
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "locale", ["en-US", "en-GB", "es-ES", "es-US", "fr-FR", "fr-CA"]
)
async def test_all_six_supported_locales_no_fallback(
    client: AsyncClient, greeting_admin_token: dict[str, object], locale: str
) -> None:
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": locale}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["locale"] == locale
    assert resp.json()["locale_fallback"] is False


@pytest.mark.asyncio
async def test_unsupported_locale_falls_back_to_tenant_default(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    """Tenant default is en-US (lazily created by repository.py on first
    access) — regional proximity (is-IS is not close to any of the six)
    does not make a locale supported."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "is-IS"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["locale"] == "en-US"
    assert data["locale_fallback"] is True
    assert data["translation_source"] == "static"


@pytest.mark.asyncio
async def test_near_miss_locale_es_mx_is_not_treated_as_supported(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "es-MX"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["locale_fallback"] is True


# ────────────────────────────────────────────────────────────────────────
# LLM-delta adaptation — opt-in LLM translation path
# ────────────────────────────────────────────────────────────────────────


class _FakeLLMTransport:
    """Deterministic fake — never a live third party."""

    def __init__(self, reply: str | None = None, raise_error: bool = False) -> None:
        self._reply = reply
        self._raise_error = raise_error

    async def chat(self, **_: Any) -> dict[str, Any]:
        if self._raise_error:
            raise LLMError("simulated upstream failure")
        return {"choices": [{"message": {"content": self._reply or "Hallo, Ada!"}}]}


@pytest.fixture(autouse=True)
def _reset_llm_transport() -> Any:
    yield
    set_transport(None)


@pytest.mark.asyncio
async def test_llm_translation_used_when_opted_in_and_key_configured(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    await session.commit()
    set_transport(_FakeLLMTransport(reply="Hallo, Ada!"))

    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings",
        json={"name": "Ada", "locale": "de-DE", "use_llm": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["translation_source"] == "llm"
    assert data["locale"] == "de-DE"  # LLM serves the ACTUAL requested locale
    assert data["locale_fallback"] is False
    assert data["greeting"] == "Hallo, Ada!"


@pytest.mark.asyncio
async def test_llm_translation_not_used_without_opt_in(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    """Never a silent default: no key even configured, and use_llm omitted
    (defaults False) — must fall back to static, not attempt the LLM path."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "de-DE"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["translation_source"] == "static"
    assert data["locale_fallback"] is True


@pytest.mark.asyncio
async def test_llm_failure_falls_through_to_static(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    await session.commit()
    set_transport(_FakeLLMTransport(raise_error=True))

    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings",
        json={"name": "Ada", "locale": "de-DE", "use_llm": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["translation_source"] == "static"
    assert data["locale_fallback"] is True


# ────────────────────────────────────────────────────────────────────────
# FR-004/FR-005 — MFA-gated, paginated history
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_history_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/greetings/history")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_history_nonadmin_gets_403_not_empty_list(
    client: AsyncClient, greeting_nonadmin_token: dict[str, object]
) -> None:
    """This 403 is raised by the chassis's own `requires()` permission gate
    (app/deps.py) — the caller lacks `greetings:history:read` entirely, so
    this slot's route body never runs. `requires()` is chassis-owned code
    outside the two marked extension points this slot may edit, and it
    uses the chassis's plain-string error convention (ERR_FORBIDDEN), not
    this slot's structured `{error_code, message}` body — so only the
    status code is asserted here, not NFR-004's error_code shape. The
    admin-without-MFA case below DOES get the structured body, because
    that check is this slot's own explicit assertion."""
    headers = cast(dict[str, str], greeting_nonadmin_token["headers"])
    resp = await client.get("/api/greetings/history", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_history_admin_without_mfa_gets_403(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    """The chassis's own built-in MFA mandate (requires()) is scoped to
    PLATFORM-wide privileged accounts only, so a per-org admin without MFA
    is NOT blocked by that gate — this slot's own explicit assertion
    (routes.py) is what enforces FR-004's "admin without MFA also gets
    403" requirement. This test is the one that would fail if that
    explicit assertion were ever removed."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.get("/api/greetings/history", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "AUTHORIZATION_FAILED"


@pytest.mark.asyncio
async def test_history_mfa_admin_happy_path_pagination(
    client: AsyncClient, greeting_admin_mfa_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_mfa_token["headers"])
    for i in range(45):
        resp = await client.post(
            "/api/greetings", json={"name": f"User{i}", "locale": "en-US"}, headers=headers
        )
        assert resp.status_code == 200, resp.text

    page1 = await client.get("/api/greetings/history?page=1", headers=headers)
    assert page1.status_code == 200
    assert len(page1.json()["entries"]) == 20
    assert page1.json()["total"] == 45

    page3 = await client.get("/api/greetings/history?page=3", headers=headers)
    assert len(page3.json()["entries"]) == 5

    page4 = await client.get("/api/greetings/history?page=4", headers=headers)
    assert page4.status_code == 200
    assert page4.json()["entries"] == []


@pytest.mark.asyncio
async def test_history_ordered_most_recent_first(
    client: AsyncClient, greeting_admin_mfa_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_mfa_token["headers"])
    await client.post("/api/greetings", json={"name": "First", "locale": "en-US"}, headers=headers)
    await client.post("/api/greetings", json={"name": "Second", "locale": "en-US"}, headers=headers)

    resp = await client.get("/api/greetings/history", headers=headers)
    entries = resp.json()["entries"]
    assert entries[0]["name_supplied"] == "Second"
    assert entries[1]["name_supplied"] == "First"


@pytest.mark.asyncio
async def test_history_filter_by_locale(
    client: AsyncClient, greeting_admin_mfa_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_mfa_token["headers"])
    await client.post("/api/greetings", json={"name": "A", "locale": "en-US"}, headers=headers)
    await client.post("/api/greetings", json={"name": "B", "locale": "fr-FR"}, headers=headers)

    resp = await client.get("/api/greetings/history?locale=fr-FR", headers=headers)
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["locale_used"] == "fr-FR"


@pytest.mark.asyncio
async def test_history_filter_unsupported_locale_is_400(
    client: AsyncClient, greeting_admin_mfa_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_mfa_token["headers"])
    resp = await client.get("/api/greetings/history?locale=de-DE", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_history_filter_no_matching_events_returns_empty_200(
    client: AsyncClient, greeting_admin_mfa_token: dict[str, object]
) -> None:
    headers = cast(dict[str, str], greeting_admin_mfa_token["headers"])
    await client.post("/api/greetings", json={"name": "A", "locale": "en-US"}, headers=headers)

    resp = await client.get("/api/greetings/history?locale=fr-CA", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


# ────────────────────────────────────────────────────────────────────────
# BR-001 — tenant isolation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_org_isolation_on_history(
    client: AsyncClient,
    greeting_admin_mfa_token: dict[str, object],
    seeded_greeting: dict[str, object],
) -> None:
    """A second org's MFA-enrolled admin sees NONE of the first org's
    greeting history — the chassis TenantScoped auto-filter."""
    other_admin = await client.post(
        "/auth/register",
        json={"email": "other-org-admin@example.com", "password": "TestPassword123!"},
    )
    assert other_admin.status_code == 201
    other_headers = {"Authorization": f"Bearer {other_admin.json()['access_token']}"}
    other_org = await client.post(
        "/orgs", json={"name": "Other Co", "slug": "other-co"}, headers=other_headers
    )
    assert other_org.status_code == 201

    start = await client.post("/auth/mfa/enroll", headers=other_headers)
    import pyotp

    code = pyotp.TOTP(start.json()["secret"]).now()
    await client.post("/auth/mfa/enroll/confirm", json={"code": code}, headers=other_headers)

    resp = await client.get("/api/greetings/history", headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["entries"] == []
    assert resp.json()["total"] == 0


# ────────────────────────────────────────────────────────────────────────
# BR-002 — rate limit (1,000 / rolling 60 minutes, per org)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_enforced_at_1001st_request(
    client: AsyncClient, greeting_admin_token: dict[str, object], session: AsyncSession
) -> None:
    """Directly exercises the RateLimiter component rather than 1,000 real
    HTTP round-trips (which would make this suite extremely slow) — seeds
    the Redis counter to 1,000 for this org, then confirms request 1,001
    is rejected with 429 RATE_LIMITED and NO GreetingEvent is written."""
    from app.slots.greeting.providers import rate_limit as rl
    from app.tasks.queue import get_redis

    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    headers = cast(dict[str, str], greeting_admin_token["headers"])

    import time

    bucket = int(time.time()) // rl.WINDOW_SECONDS
    key = f"greeting_ratelimit:{org_id}:{bucket}"
    redis = get_redis()
    redis.set(key, rl.CEILING, ex=rl.WINDOW_SECONDS)

    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "en-US"}, headers=headers
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["error_code"] == "RATE_LIMITED"
    assert "Retry-After" in resp.headers

    from sqlalchemy import func, select

    from app.slots.greeting.models import GreetingEvent

    count = (
        await session.execute(select(func.count()).select_from(GreetingEvent))
    ).scalar_one()
    assert count == 0

    redis.delete(key)


# ────────────────────────────────────────────────────────────────────────
# BR-003 — every greeting is audited
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_greeting_persists_audit_fields(
    client: AsyncClient, greeting_admin_token: dict[str, object], session: AsyncSession
) -> None:
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "en-US"}, headers=headers
    )
    assert resp.status_code == 200

    from sqlalchemy import select

    from app.slots.greeting.models import GreetingEvent

    row = (
        await session.execute(select(GreetingEvent).order_by(GreetingEvent.id.desc()))
    ).scalars().first()
    assert row is not None
    assert row.actor_user_id is not None
    assert row.org_id is not None
    assert row.locale_used == "en-US"
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_greeting_audit_log_details_are_actually_populated(
    client: AsyncClient, greeting_admin_token: dict[str, object], session: AsyncSession
) -> None:
    """Regression test for a real bug found live via CP-B.8's Playwright E2E
    pass: greet() returns tuple[GreetingEvent, str], but the @audited
    decorator's capture_details lambda was written as if it received the
    bare GreetingEvent, so every call raised AttributeError ('tuple' object
    has no attribute 'locale_used') -- silently caught by the decorator's
    own try/except. The GreetingEvent domain row (asserted above in
    test_greeting_persists_audit_fields) was always written correctly, so
    that test passed throughout -- only the separate AuditLog audit-trail
    row's `details` column was silently empty, which no existing test
    checked. This is the actual regression surface."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings", json={"name": "Ada", "locale": "en-US"}, headers=headers
    )
    assert resp.status_code == 200

    from sqlalchemy import select

    from app.audit.models import AuditLog

    row = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.action == "greeting.created")
            .order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert row is not None
    assert row.details, "AuditLog.details must not be empty for a successful greeting"
    assert row.details["locale_used"] == "en-US"
    assert row.details["locale_fallback"] is False
    assert row.details["translation_source"] == "static"


# ────────────────────────────────────────────────────────────────────────
# NFR-005 — no deletion path exists anywhere in this slot
# ────────────────────────────────────────────────────────────────────────


def test_repository_has_no_delete_purge_or_truncate() -> None:
    """A test for an ABSENCE: NFR-005 forbids any application deletion
    path, and the absence is the design decision (mirrors the draft's
    DESIGN.md §4 exactly)."""
    from app.slots.greeting import repository

    for forbidden in ("delete", "purge", "truncate"):
        assert not hasattr(repository, forbidden)


# ────────────────────────────────────────────────────────────────────────
# CP-B.8 regression — the greeting page must actually render
# ────────────────────────────────────────────────────────────────────────


async def test_greeting_page_renders_for_authenticated_user(
    client: AsyncClient, greeting_admin_token: dict[str, object]
) -> None:
    """Regression test for a real bug found live via CP-B.8's Playwright E2E
    pass: greeting_page() built its own ad hoc template context
    ({"user", "org", "supported_locales"}) instead of reusing
    _common_context() like every other page in this chassis, so base.html's
    nav (which unconditionally reads `settings.is_gov_app`) threw
    jinja2.exceptions.UndefinedError and the page 500'd for every real
    request. A unit test calling the service layer directly never exercised
    this -- only rendering the actual template does."""
    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.get("/greet", headers=headers)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Greeting" in resp.text or "greeting" in resp.text.lower()
