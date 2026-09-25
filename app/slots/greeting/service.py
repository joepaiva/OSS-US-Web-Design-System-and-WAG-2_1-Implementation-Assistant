"""GreetingService — orchestration only (Constitution §3, §5; DESIGN.md
§3, §8). Decides nothing about locales, nothing about rate limits;
sequences the owning components and handles their outcomes.

Sequence flow (DESIGN.md §8): RateLimiter.check() BEFORE
TranslationProvider.translate() — a rate-limited request never reaches
the (potentially LLM-backed) translation call. A rate-limit refusal or a
provider failure writes NO GreetingEvent.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.slots.greeting import repository
from app.slots.greeting.models import GreetingEvent
from app.slots.greeting.providers import rate_limit, translation
from app.slots.greeting.providers.rate_limit import RateLimited
from app.slots.greeting.providers.translation import TranslationResult


class GreetingServiceError(Exception):
    pass


class GreetingRateLimited(GreetingServiceError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("rate limited")


@audited(
    "greeting.created",
    entity_type="greeting_event",
    # CP-B.8 fix (Chassis Program, 2026-09-02): greet() returns
    # tuple[GreetingEvent, str] (event, rendered_text) -- see its own
    # docstring on why the text can't be reconstructed from the event
    # alone. capture_details receives that tuple verbatim (the decorator
    # passes the wrapped function's raw return value through), but this
    # lambda was written as if it received the bare GreetingEvent, so
    # every single call raised AttributeError ('tuple' object has no
    # attribute 'locale_used'), silently caught by the decorator's own
    # try/except -- every BR-003 audit row for a greeting was written
    # with an EMPTY details column, not the intended locale/fallback/
    # source facts. Found live via CP-B.8's real Playwright E2E pass
    # (a unit test asserting an AuditLog row exists wouldn't catch its
    # `details` column being silently empty unless it also asserted on
    # that column's content). Unpack the tuple's first element.
    capture_details=lambda r: {
        "locale_used": r[0].locale_used,
        "locale_fallback": r[0].locale_fallback,
        "translation_source": r[0].translation_source,
    },
)
async def greet(
    session: AsyncSession,
    *,
    actor_user_id: int,
    org_id: int,
    name: str,
    locale: str,
    use_llm: bool,
) -> tuple[GreetingEvent, str, tuple[str, ...]]:
    """FR-001/002, BR-002/003. Raises GreetingRateLimited on BR-002 breach.

    Returns (event, greeting_text, tools_used). The rendered text is NOT
    persisted on GreetingEvent — the draft's own 8-field data model has no
    text column (it audits facts: locale/fallback/source, not content), and
    for the LLM path in particular the model output must reach the caller
    exactly once as returned here, never reconstructed after the fact from
    a static template (that would silently produce the wrong text).
    `tools_used` (FR-MCPCLIENT, chassis v1.1.0) is likewise transient —
    qualified MCP tool names actually invoked while producing this
    greeting, always `()` on the static path; not persisted on
    GreetingEvent either, for the same reason.
    """
    try:
        rate_limit.check(org_id)
    except RateLimited as exc:
        raise GreetingRateLimited(exc.retry_after_seconds) from exc

    settings_row = await repository.get_or_create_org_settings(session)

    result: TranslationResult = await translation.translate(
        session,
        name=name,
        locale=locale,
        tenant_default_locale=settings_row.default_locale,
        org_id=org_id,
        use_llm=use_llm,
    )

    event = GreetingEvent(
        actor_user_id=actor_user_id,
        locale_used=result.locale_used,
        locale_requested=locale,
        locale_fallback=result.fallback,
        translation_source=result.source,
        name_supplied=name,
    )
    persisted = await repository.record(session, event)
    return persisted, result.text, result.tools_used


async def history(
    session: AsyncSession, *, page_number: int, locale: str | None
) -> tuple[list[GreetingEvent], int]:
    """FR-004/005. No side effects."""
    if locale is not None:
        return await repository.page_by_locale(session, locale, page_number)
    return await repository.page(session, page_number)
