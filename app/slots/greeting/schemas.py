"""Pydantic v2 schemas for the Greeting slot — NFR-004's closed error-code
set, plus request/response shapes for both endpoints (DESIGN.md §7).

`locale` is validated as a string here only, per TASK-APP-001's explicit
acceptance criterion — matching it against the supported six is
TranslationProvider's job (Constitution §3), never a schema validator.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ErrorCode(enum.StrEnum):
    """NFR-004's closed set. No endpoint in this slot returns any other value."""

    VALIDATION_FAILED = "VALIDATION_FAILED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"


TranslationSource = Literal["static", "llm"]


class GreetingRequest(BaseModel):
    """Body for POST /api/greetings — FR-001.

    Deliberately NO Pydantic length constraints on `name`/`locale`: FastAPI
    would turn a violation into an automatic 422, but the draft's
    Acceptance Criteria require 400 `VALIDATION_FAILED` for an
    empty/too-long name (NFR-004's closed error-code set). The route
    handler performs that check explicitly and raises the closed-set 400
    itself — see routes.py.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    locale: str
    # LLM-delta addition. Defaults False so FR-001..003's contract is
    # unchanged unless the caller explicitly opts in (never a silent
    # default — see providers/translation.py).
    use_llm: bool = False


class GreetingResponse(BaseModel):
    """200 body for POST /api/greetings."""

    model_config = ConfigDict(extra="forbid")

    greeting: str
    locale: str
    locale_fallback: bool
    translation_source: TranslationSource
    # FR-MCPCLIENT (chassis v1.1.0) — qualified `<connection-name>.<tool-name>`
    # entries actually invoked while producing this greeting. Empty on the
    # static path and empty on the LLM path whenever no MCP tool was called
    # (including every org with zero enabled MCP connections).
    tools_used: list[str] = []


class GreetingHistoryEntry(BaseModel):
    """One row in the history page — DESIGN.md §4 fields, minus org_id
    (implicit — history is always the caller's own org)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    locale_used: str
    locale_requested: str
    locale_fallback: bool
    translation_source: TranslationSource
    name_supplied: str
    created_at: datetime


class GreetingHistoryResponse(BaseModel):
    """200 body for GET /api/greetings/history — FR-004/005."""

    model_config = ConfigDict(extra="forbid")

    entries: list[GreetingHistoryEntry]
    page: int
    total: int


class ErrorResponse(BaseModel):
    """Uniform error body. `error_code` is always one of the closed set."""

    model_config = ConfigDict(extra="forbid")

    error_code: ErrorCode
    message: str
