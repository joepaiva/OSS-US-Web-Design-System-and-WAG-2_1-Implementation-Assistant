"""LLM transport — routes completions through an OpenAI-compatible endpoint.

Rule-7 parity: the chassis never talks to a provider SDK directly. Every
completion is an OpenAI-format `POST {base}/chat/completions` to the
configured LiteLLM proxy, with the per-request resolved API key injected
BOTH as a Bearer header AND in the request body (LiteLLM's
`configurable_clientside_auth_params: ['api_key']`), so the same proxy can
serve many tenants with different keys.

The transport is abstracted behind `LLMTransport` so tests inject a fake and
a future in-process `litellm`-SDK transport can drop in without touching
callers. `get_transport()` returns a process singleton; tests override it
via `set_transport()`.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.logging import get_logger

log = get_logger("llm.transport")


class LLMError(Exception):
    """Raised when an LLM completion call fails (network, auth, 5xx)."""


class LLMTransport(Protocol):
    """Pluggable completion transport."""

    async def chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Return the raw OpenAI-format response dict. Raises LLMError."""
        ...


class HTTPTransport:
    """Default transport: HTTP POST to an OpenAI-compatible proxy."""

    async def chat(
        self,
        *,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        settings = get_settings()
        url = settings.llm_proxy_url.rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            # LiteLLM clientside auth param — the proxy forwards this key to
            # the upstream provider instead of using a server-side key.
            "api_key": api_key,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(extra)

        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=settings.llm_request_timeout_seconds
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except httpx.HTTPStatusError as exc:
            log.warning(
                "llm.transport.http_error",
                status=exc.response.status_code,
                model=model,
            )
            raise LLMError(
                f"LLM endpoint returned {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("llm.transport.network_error", error=str(exc), model=model)
            raise LLMError(f"LLM endpoint unreachable: {exc}") from exc


_transport: LLMTransport | None = None


def get_transport() -> LLMTransport:
    """Return the process-singleton transport (default: HTTPTransport)."""
    global _transport
    if _transport is None:
        _transport = HTTPTransport()
    return _transport


def set_transport(transport: LLMTransport | None) -> None:
    """Override (or reset, with None) the transport. For tests + future DI."""
    global _transport
    _transport = transport
