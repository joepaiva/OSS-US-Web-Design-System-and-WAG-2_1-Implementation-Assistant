"""Greeting-translation × MCP tool-calling integration tests (chassis
v1.1.0, FR-MCPCLIENT, DESIGN.md §6.14). TS-MCP-INTEGRATION / TS-MCP-DEMO
(specs/TEST-SCENARIOS.md).

Reuses `greeting_admin_token` from the slot's own conftest.py, and the
same `_FakeLLMTransport`-at-the-transport-layer pattern
`test_routes.py::test_llm_translation_used_when_opted_in_and_key_configured`
already established for this slot — only the actual HTTP call to the LLM
proxy is faked; `app.llm.service.complete()` and this module's real
`discover_tools`/`invoke_tool` both run for real, against the real
fixture MCP server (tests/fixtures/mcp_fixture_server.py) for the
positive-path cases.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import service as llm_service
from app.llm.transport import set_transport
from app.mcp import service as mcp_service
from tests.fixtures.mcp_fixture_server import run_fixture_server


class _RecordingLLMTransport:
    """Records every `.chat()` call's kwargs (so a test can assert `tools`
    is present/absent) and returns canned responses in order, repeating
    the last one once exhausted. Never a live third party."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self, *, api_key: str, model: str, messages: list[dict[str, str]], **extra: Any
    ) -> dict[str, Any]:
        self.calls.append({"messages": messages, **extra})
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


@pytest.fixture(autouse=True)
def _reset_llm_transport() -> Any:
    yield
    set_transport(None)


def _final_response(text: str) -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def _tool_call_response(*, call_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ]
    }


# ─── Negative control: zero connections adds no `tools` kwarg ──────────


@pytest.mark.asyncio
async def test_zero_connections_adds_no_tools_kwarg(
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

    fake = _RecordingLLMTransport([_final_response("Hallo, Ada!")])
    set_transport(fake)

    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings",
        json={"name": "Ada", "locale": "de-DE", "use_llm": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["translation_source"] == "llm"
    assert data["tools_used"] == []

    # The negative control: proving absence, not just "not mentioned".
    assert len(fake.calls) == 1
    assert "tools" not in fake.calls[0]


@pytest.mark.asyncio
async def test_disabled_connection_also_adds_no_tools_kwarg(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    async with run_fixture_server(port=8851) as url:
        # Registered but never enabled.
        await mcp_service.create_connection(
            session,
            org_id=org_id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await session.commit()

        fake = _RecordingLLMTransport([_final_response("Hallo, Ada!")])
        set_transport(fake)

        headers = cast(dict[str, str], greeting_admin_token["headers"])
        resp = await client.post(
            "/api/greetings",
            json={"name": "Ada", "locale": "de-DE", "use_llm": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tools_used"] == []
        assert "tools" not in fake.calls[0]


# ─── Positive path: discovered tools drive a real tool-calling loop ────


@pytest.mark.asyncio
async def test_enabled_connection_tools_offered_to_llm(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    async with run_fixture_server(port=8852) as url:
        conn = await mcp_service.create_connection(
            session,
            org_id=org_id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await mcp_service.enable_connection(session, conn)
        await session.commit()

        # No tool call requested — the LLM just answers directly. Still
        # proves the tools kwarg WAS offered (positive counterpart to the
        # negative control above).
        fake = _RecordingLLMTransport([_final_response("Hallo, Ada!")])
        set_transport(fake)

        headers = cast(dict[str, str], greeting_admin_token["headers"])
        resp = await client.post(
            "/api/greetings",
            json={"name": "Ada", "locale": "de-DE", "use_llm": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tools_used"] == []
        assert "tools" in fake.calls[0]
        offered_names = {t["function"]["name"] for t in fake.calls[0]["tools"]}
        assert offered_names == {"fixture.echo", "fixture.lookup"}


@pytest.mark.asyncio
async def test_tool_call_loop_invokes_real_fixture_and_folds_result_in(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    """The LLM's first response requests the fixture's `lookup` tool; the
    loop must call it for real, append the real result, and re-invoke
    `complete()` — driving the fixture's actual answer into the final
    greeting text."""
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    async with run_fixture_server(port=8853) as url:
        conn = await mcp_service.create_connection(
            session,
            org_id=org_id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await mcp_service.enable_connection(session, conn)
        await session.commit()

        fake = _RecordingLLMTransport(
            [
                _tool_call_response(
                    call_id="call_1",
                    tool_name="fixture.lookup",
                    arguments={"key": "greeting_style"},
                ),
                _final_response("Guten Tag, Ada! (formal)"),
            ]
        )
        set_transport(fake)

        headers = cast(dict[str, str], greeting_admin_token["headers"])
        resp = await client.post(
            "/api/greetings",
            json={"name": "Ada", "locale": "de-DE", "use_llm": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["greeting"] == "Guten Tag, Ada! (formal)"
        assert data["tools_used"] == ["fixture.lookup"]

        # Two complete() calls: the tool-call round, then the follow-up.
        assert len(fake.calls) == 2
        # The second call's message list carries the REAL fixture result
        # ("formal", from LOOKUP_TABLE["greeting_style"]) as a tool-role
        # message -- not a mock/stub value, proving the loop actually
        # invoked the fixture server rather than fabricating a result.
        second_call_messages = fake.calls[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "call_1"
        tool_payload = json.loads(tool_messages[0]["content"])
        assert tool_payload == {"result": "formal"}


@pytest.mark.asyncio
async def test_tool_calling_loop_is_bounded(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    """A response that keeps requesting tool calls forever must stop at
    the fixed iteration cap rather than looping unboundedly."""
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    async with run_fixture_server(port=8854) as url:
        conn = await mcp_service.create_connection(
            session,
            org_id=org_id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await mcp_service.enable_connection(session, conn)
        await session.commit()

        # Every response keeps requesting the same tool call — never a
        # final answer. The loop must give up, not hang.
        endless = [
            _tool_call_response(
                call_id=f"call_{i}", tool_name="fixture.echo", arguments={"text": "x"}
            )
            for i in range(10)
        ]
        fake = _RecordingLLMTransport(endless)
        set_transport(fake)

        headers = cast(dict[str, str], greeting_admin_token["headers"])
        resp = await client.post(
            "/api/greetings",
            json={"name": "Ada", "locale": "de-DE", "use_llm": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # Never a hang / 5xx / timeout. Falls back to static because the
        # LLM path never produced a usable final text within the cap.
        data = resp.json()
        assert data["translation_source"] == "static"
        # Bounded: the initial complete() call, plus one more per
        # _MCP_MAX_TOOL_ITERATIONS (3) tool-calling round that found a
        # tool_calls entry to act on -- 1 + 3 = 4 total, never unbounded.
        assert len(fake.calls) == 4


# ─── Demo visibility ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_meta_line_shows_tools_used_when_mcp_enabled(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    async with run_fixture_server(port=8855) as url:
        conn = await mcp_service.create_connection(
            session,
            org_id=org_id,
            name="fixture",
            url=url,
            credential=None,
            created_by_user_id=None,
        )
        await mcp_service.enable_connection(session, conn)
        await session.commit()

        fake = _RecordingLLMTransport(
            [
                _tool_call_response(
                    call_id="call_1",
                    tool_name="fixture.lookup",
                    arguments={"key": "greeting_style"},
                ),
                _final_response("Guten Tag, Ada!"),
            ]
        )
        set_transport(fake)

        headers = cast(dict[str, str], greeting_admin_token["headers"])
        resp = await client.post(
            "/api/greetings",
            json={"name": "Ada", "locale": "de-DE", "use_llm": True},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tools_used"] == ["fixture.lookup"]


@pytest.mark.asyncio
async def test_demo_tools_used_empty_when_mcp_disabled(
    client: AsyncClient,
    greeting_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    """Same request shape, no MCP connection at all — GreetingResponse
    carries an explicitly empty tools_used, distinguishing "MCP off" from
    "MCP on but nothing was called"."""
    org = cast(dict[str, object], greeting_admin_token["org"])
    org_id = cast(int, org["id"])
    await llm_service.set_key(
        session, provider="openai", plaintext="fake-key", org_id=org_id, created_by_user_id=None
    )
    await session.commit()
    set_transport(_RecordingLLMTransport([_final_response("Hallo, Ada!")]))

    headers = cast(dict[str, str], greeting_admin_token["headers"])
    resp = await client.post(
        "/api/greetings",
        json={"name": "Ada", "locale": "de-DE", "use_llm": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tools_used"] == []
    assert data["translation_source"] == "llm"
