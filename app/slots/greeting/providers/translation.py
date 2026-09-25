"""TranslationProvider — sole owner of locale resolution, fallback
selection, and message formatting (Constitution §3, DESIGN.md §6).

Callers receive an outcome, never a strategy: `translate()` returns a
`TranslationResult` and no caller inspects `locale` to decide anything.

Two paths, per chassis-program-DESIGN.md §3's LLM-delta adaptation rule:

  - STATIC (the draft's original design): exactly the six locales of
    FR-003. Deterministic, no external call, always available. This is
    the ONLY path used unless a caller explicitly opts in to `use_llm`.
  - LLM (this package's addition, since it carries the LLM delta): when
    `use_llm=True` AND the requested locale is outside the static six,
    attempt an LLM-generated translation into the ACTUAL requested
    locale — extending coverage beyond the fixed six, rather than
    falling back to the tenant default. On any failure (no key
    configured, transport error, timeout), falls through to the same
    static-fallback behavior FR-002 specifies. Never a silent default:
    only engaged when the caller sets `use_llm=True` on the request.

MCP tool-calling extension (chassis v1.1.0, FR-MCPCLIENT, DESIGN.md §6.14):
when the org has one or more *enabled* MCP server connections, their tools
are discovered and offered to the LLM alongside the translation prompt —
plausibly a "regional greeting convention" lookup — before the final text
is produced. An org with zero enabled connections takes the exact prior
single-`complete()`-call path: `discover_tools` returns `[]` from one fast,
local, org-scoped query (no MCP network call), so no `tools` kwarg is ever
added and no latency is added (NFR-MCPCLIENT-1).

Outbound calls (LLM + MCP paths) are mocked in tests; never a live third
party.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.service import LLMKeyUnavailable, complete
from app.llm.transport import LLMError
from app.logging import get_logger
from app.mcp.service import discover_tools, invoke_tool

log = get_logger("slots.greeting.translation")

# FR-003 — exactly these six, no more.
_STATIC_GREETINGS: dict[str, str] = {
    "en-US": "Hello, {name}!",
    "en-GB": "Hello, {name}!",
    "es-ES": "¡Hola, {name}!",
    "es-US": "¡Hola, {name}!",
    "fr-FR": "Bonjour, {name} !",
    "fr-CA": "Bonjour, {name} !",
}

SUPPORTED_LOCALES: frozenset[str] = frozenset(_STATIC_GREETINGS)

# Local, slot-scoped defaults — kept out of the chassis-owned Settings
# class deliberately (app/slots/greeting is a self-contained package;
# see chassis-program-CONSTITUTION.md §2). Operators who need a different
# provider/model can override via the two module-level names below.
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4o-mini"
_LLM_MAX_TOKENS = 40  # a greeting is short; keep the opt-in call cheap and fast

# FR-MCPCLIENT-7 — bounds the discover→advertise→invoke→loop cycle so a
# misbehaving MCP tool or LLM can never spin the request forever. Reaching
# the cap is not an error; the loop simply returns the last response.
_MCP_MAX_TOOL_ITERATIONS = 3


@dataclass(frozen=True)
class TranslationResult:
    text: str
    locale_used: str
    fallback: bool
    source: Literal["static", "llm"]
    # Qualified `<connection-name>.<tool-name>` entries actually invoked
    # while producing this result. Always empty on the static path, and
    # empty on the LLM path whenever no MCP tool was called (including
    # every case where the org has zero enabled connections).
    tools_used: tuple[str, ...] = ()


def _static_greeting(name: str, locale: str) -> str:
    template = _STATIC_GREETINGS[locale]
    return template.format(name=name)


async def _run_tool_calling_loop(
    session: AsyncSession,
    *,
    org_id: int,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    first_response: dict[str, Any],
) -> tuple[str | None, tuple[str, ...]]:
    """Drives the OpenAI-shaped tool-calling loop (FR-MCPCLIENT-7):
    for each `tool_calls` entry the LLM's response carries, invoke it via
    `app.mcp.service.invoke_tool` (which never raises for a normal
    operational failure — a failed call still round-trips as a
    `{"error": ...}` tool-result message, per FR-MCPCLIENT-10/11), append
    the result, and re-call `complete()`. Stops on the first response with
    no `tool_calls`, or after `_MCP_MAX_TOOL_ITERATIONS` rounds.
    """
    response = first_response
    tools_used: list[str] = []
    for _ in range(_MCP_MAX_TOOL_ITERATIONS):
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            content = message.get("content")
            return (content.strip() if content else None), tuple(tools_used)

        messages.append(message)
        for call in tool_calls:
            function = call.get("function", {})
            qualified_name = function.get("name", "")
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            result = await invoke_tool(session, org_id, qualified_name, arguments)
            tools_used.append(qualified_name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result),
                }
            )

        response = await complete(
            session,
            provider=LLM_PROVIDER,
            model=LLM_MODEL,
            messages=messages,
            org_id=org_id,
            max_tokens=_LLM_MAX_TOKENS,
            temperature=0.2,
            tools=tools,
        )

    # Cap reached — not an error (FR-MCPCLIENT-7): return the last response
    # as-is rather than looping further.
    message = response["choices"][0]["message"]
    content = message.get("content")
    return (content.strip() if content else None), tuple(tools_used)


async def _try_llm_translate(
    session: AsyncSession, *, name: str, locale: str, org_id: int
) -> tuple[str, tuple[str, ...]] | None:
    """Best-effort LLM greeting in `locale`. Returns None on any failure —
    callers fall through to the static path; this never raises.

    When the org has one or more enabled MCP connections, their tools are
    discovered and offered to the LLM (e.g. a regional-greeting-convention
    lookup) before the final text is produced; see `_run_tool_calling_loop`.
    An org with zero enabled connections adds no `tools` kwarg at all.
    """
    prompt = (
        f"Translate the following greeting into the language and regional "
        f"conventions of locale '{locale}'. If a tool is available for "
        f"looking up a regional greeting convention, you may call it first "
        f"to inform your translation. Reply with ONLY the greeting text, "
        f"no explanation, no quotes: Hello, {name}!"
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    # discover_tools() itself never raises (FR-MCPCLIENT-9); the broad catch
    # here is a last-resort safety net so a defect in that contract degrades
    # to the static fallback path rather than a 500.
    try:
        tools = await discover_tools(session, org_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("greeting.mcp_discover_unexpected_error", error=str(exc))
        tools = []

    extra: dict[str, Any] = {"tools": tools} if tools else {}
    try:
        result = await complete(
            session,
            provider=LLM_PROVIDER,
            model=LLM_MODEL,
            messages=messages,
            org_id=org_id,
            max_tokens=_LLM_MAX_TOKENS,
            temperature=0.2,
            **extra,
        )
        if tools:
            text, tools_used = await _run_tool_calling_loop(
                session,
                org_id=org_id,
                messages=messages,
                tools=tools,
                first_response=result,
            )
        else:
            content = result["choices"][0]["message"]["content"]
            text = content.strip() if content else None
            tools_used = ()
        return (text, tools_used) if text else None
    except (LLMKeyUnavailable, LLMError, KeyError, IndexError, TypeError) as exc:
        log.info("greeting.llm_translate_fallback", locale=locale, error=str(exc))
        return None


async def translate(
    session: AsyncSession,
    *,
    name: str,
    locale: str,
    tenant_default_locale: str,
    org_id: int,
    use_llm: bool = False,
) -> TranslationResult:
    """The sole entry point. Decides whether `locale` is supported, tries
    the LLM extension when asked to and needed, and falls back to the
    tenant default otherwise (FR-002)."""
    if locale in _STATIC_GREETINGS:
        return TranslationResult(
            text=_static_greeting(name, locale),
            locale_used=locale,
            fallback=False,
            source="static",
        )

    if use_llm:
        llm_result = await _try_llm_translate(session, name=name, locale=locale, org_id=org_id)
        if llm_result is not None:
            llm_text, tools_used = llm_result
            return TranslationResult(
                text=llm_text,
                locale_used=locale,
                fallback=False,
                source="llm",
                tools_used=tools_used,
            )

    # FR-002 — unsupported locale (and no usable LLM result): fall back to
    # the tenant's own default locale, never a service-wide default.
    fallback_locale = (
        tenant_default_locale if tenant_default_locale in _STATIC_GREETINGS else "en-US"
    )
    return TranslationResult(
        text=_static_greeting(name, fallback_locale),
        locale_used=fallback_locale,
        fallback=True,
        source="static",
    )
