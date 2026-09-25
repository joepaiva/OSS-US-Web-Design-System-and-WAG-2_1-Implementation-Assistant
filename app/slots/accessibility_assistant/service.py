# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# AC-3: service functions are called only from routes gated by requires()
# AC-6: user_id scoping on interaction log reads enforces least-privilege
# AU-2: @audited decorator on every state-mutating function below
# AU-12: audit records include actor, org, entity type+id, and details
# SI-10: AskQuestionCreate schema validated before reaching service layer
# PT-1: interaction logs contain PII; user_id filter enforced on end-user reads
# SC-28: no plaintext credentials stored or returned in this module
# ─────────────────────────────────────────────────────────────────
"""Accessibility Assistant service layer — async, no FastAPI imports.

Scope: v0.1 — FR-001 through FR-006, SR-001 through SR-004.

Key design decisions:
  - TenantScoped auto-filter handles org_id isolation; no manual WHERE org_id.
  - @audited on all state-mutating functions.
  - PII/source-code detection (SR-002) is a lightweight heuristic filter;
    it blocks submissions before any LLM call.
  - LLM calls use the chassis app.llm.service.complete() — never a direct
    provider SDK import (CON-001).
  - Interaction logs are append-only; no UPDATE/DELETE service functions
    are exposed for log records (SR-003).
  - Rating is the ONLY mutable field on an interaction log (FR-006).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.auth.models import User
from app.db import get_current_org_id, set_current_org_id
from app.logging import get_logger
from app.orgs.models import Membership
from app.rbac.models import Permission, Role, role_permissions
from app.slots.accessibility_assistant import (
    ASSISTANT_ASK,
    ASSISTANT_READ,
    CONTENT_MANAGER_PERMISSIONS,
)
from app.slots.accessibility_assistant.crypto import CredentialEncryptionService
from app.slots.accessibility_assistant.models import (
    FAQ,
    FAQGenerationCandidate,
    FAQGenerationCandidateStatus,
    FAQGenerationSession,
    FAQGenerationStatus,
    FAQQuestionCategory,
    FAQSource,
    FAQSourceCategory,
    InformationSource,
    InformationSourceCategory,
    InformationSourceTestStatus,
    InformationSourceType,
    InteractionLog,
    LLMFallbackConfig,
    QuestionAlert,
    QuestionCategory,
)
from app.slots.accessibility_assistant.schemas import (
    AskQuestionCreate,
    Citation,
    DocumentFolderSourceCreate,
    FAQCreate,
    FAQGenerationApprovedCandidate,
    FAQGenerationCandidateOut,
    FAQGenerationCandidateRead,
    FAQGenerationFromSourceResponse,
    FAQRead,
    GitHubOnlineRepoSourceCreate,
    InformationSourceCategoryRead,
    InformationSourceCreate,
    InformationSourceRead,
    InteractionLogRead,
    LocalCodeRepoSourceCreate,
    MCPCredentials,
    MCPServerSourceCreate,
    QuestionAlertRead,
    QuestionCategoryRead,
    QuestionResponse,
    RateInteractionUpdate,
)

log = get_logger("slots.accessibility_assistant")

# The four information source types supported by the platform (FR-011),
# with the form-variant hint the client uses to render the right form.
SOURCE_TYPES: list[dict[str, str]] = [
    {
        "source_type": InformationSourceType.LOCAL_CODE_REPO.value,
        "label": "Local Code Repo",
        "form_variant": "folder_picker",
    },
    {
        "source_type": InformationSourceType.GITHUB_ONLINE_REPO.value,
        "label": "GitHub/Online Repo",
        "form_variant": "url_and_credential",
    },
    {
        "source_type": InformationSourceType.DOCUMENT_FOLDER.value,
        "label": "Document Folder",
        "form_variant": "folder_picker",
    },
    {
        "source_type": InformationSourceType.MCP_SERVER.value,
        "label": "MCP Server",
        "form_variant": "server_address_and_credential",
    },
]


# ────────────────────────────────────────────────────────────────────────
# Custom exceptions
# ────────────────────────────────────────────────────────────────────────


class CategoryNotFound(Exception):
    pass


class FAQNotFound(Exception):
    pass


class InteractionLogNotFound(Exception):
    pass


class InteractionLogAccessDenied(Exception):
    """Raised when a user attempts to access another user's interaction log (SR-003)."""
    pass


class ContentBlocked(Exception):
    """Raised when SR-002 PII or source-code detection blocks a submission."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# ────────────────────────────────────────────────────────────────────────
# v0.2 custom exceptions (FR-007 through FR-017)
# ────────────────────────────────────────────────────────────────────────


class DuplicateCategoryName(Exception):
    """Raised when a category name already exists within the org scope."""


class InformationSourceCategoryNotFound(Exception):
    pass


class InformationSourceNotFound(Exception):
    pass


class SourceTestFailed(Exception):
    """Raised when a connectivity/read-access test fails (FR-012..FR-014)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class FAQValidationError(Exception):
    """Raised when an FAQ submission references an unresolvable id, or is
    otherwise structurally invalid (T-006)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class QuestionAlertNotFound(Exception):
    pass


class LLMFallbackConfigNotFound(Exception):
    pass


class NotAnOrgMember(Exception):
    """Raised when a Content Manager designation targets a user who is not
    a member of the current org."""


# ────────────────────────────────────────────────────────────────────────
# v0.3 custom exceptions (FR-017 through FR-022, SR-005..SR-007, NFR-001)
# ────────────────────────────────────────────────────────────────────────


class RatingAlreadySubmitted(Exception):
    """Raised when a second helpfulness rating is attempted for the same
    interaction log record (FR-019 — ratings are immutable once set)."""


class PlatformShareDenied(Exception):
    """Raised when a non-Platform-Administrator (user.is_superuser is
    False) attempts to designate a resource platform-level shared
    (FR-020)."""


class FAQGenerationSessionNotFound(Exception):
    pass


# ────────────────────────────────────────────────────────────────────────
# SR-002: PII and source-code detection
# ────────────────────────────────────────────────────────────────────────

# Patterns that suggest PII presence (heuristic — errs on side of caution)
_PII_PATTERNS: list[re.Pattern[str]] = [
    # Email addresses
    re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    # US SSN
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # US phone numbers
    re.compile(r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    # Credit card numbers (basic pattern)
    re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    # Names preceded by common PII labels
    re.compile(r"\b(?:my name is|i am|i'm)\s+[A-Z][a-z]+\s+[A-Z][a-z]+", re.IGNORECASE),
]

# Patterns that suggest source code presence
_CODE_PATTERNS: list[re.Pattern[str]] = [
    # Function/method definitions
    re.compile(r"\bdef\s+\w+\s*\("),
    re.compile(r"\bfunction\s+\w+\s*\("),
    re.compile(r"\bclass\s+\w+\s*[:{(]"),
    # Import statements
    re.compile(r"^\s*import\s+\w", re.MULTILINE),
    re.compile(r"^\s*from\s+\w+\s+import", re.MULTILINE),
    re.compile(r'^\s*#include\s*[<"]', re.MULTILINE),
    # Common code constructs
    re.compile(r"\bif\s*\(.+\)\s*\{"),
    re.compile(r"\bfor\s*\(.+;.+;.+\)"),
    re.compile(r"\bwhile\s*\(.+\)\s*\{"),
    # Variable assignments with operators
    re.compile(r"\w+\s*[+\-*/]=\s*\w+"),
    # Code block delimiters
    re.compile(r"```[\w]*\n"),
    # SQL
    re.compile(r"\bSELECT\s+.+\s+FROM\s+", re.IGNORECASE),
]


def _check_content(text: str) -> None:
    """SR-002: raise ContentBlocked if text contains PII or source code.

    Errs on the side of caution — ambiguous content is blocked.
    No LLM call is made before this check passes.
    """
    for pattern in _PII_PATTERNS:
        if pattern.search(text):
            raise ContentBlocked("pii")
    for pattern in _CODE_PATTERNS:
        if pattern.search(text):
            raise ContentBlocked("code")


# ────────────────────────────────────────────────────────────────────────
# SR-006: LLM payload sanitization for external API calls
# ────────────────────────────────────────────────────────────────────────
#
# A mandatory step before EVERY Tier-2 LLM fallback call (_call_llm_tiered)
# and EVERY automated-FAQ-generation LLM call (T-007/T-008 below) — never
# bypassed, and never applied inside the chassis's own single LLM egress
# point (app.llm.service.complete). Distinct from SR-002's _check_content
# above: SR-002 blocks a USER'S OWN submitted question at intake; SR-006
# sanitizes the OUTBOUND payload the system itself assembles (which may
# include interaction-log text or connected-source content the end user
# never directly typed).
#
# Policy (a deliberate, disclosed design choice — SR-006's own wording is
# ambiguous about strip-vs-block): PII is STRIPPED (redacted) and the call
# proceeds with the cleaned text; source code is BLOCKED outright (the call
# never happens), mirroring SR-002's own existing precedent of blocking
# code rather than trying to redact it. Every category recognized by
# `_PII_PATTERNS` is reused here, plus a UUID-shaped-id pattern named
# explicitly in T-006/SR-006's implementation notes.

_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Named PII categories -> pattern, so a block/strip event can be logged
# with a category name instead of an offending raw match (never log the
# match itself).
_PII_PATTERN_CATEGORIES: dict[str, re.Pattern[str]] = {
    "email": _PII_PATTERNS[0],
    "ssn": _PII_PATTERNS[1],
    "phone": _PII_PATTERNS[2],
    "credit_card": _PII_PATTERNS[3],
    "display_name": _PII_PATTERNS[4],
    "uuid": _UUID_PATTERN,
}


@dataclass(frozen=True)
class SanitizedPayload:
    """SR-006: the outcome when no source code was found. `text` has any
    detected PII redacted; `redactions` names which categories were hit
    (empty if the text was already clean)."""

    text: str
    redactions: list[str]


@dataclass(frozen=True)
class SanitizationBlocked:
    """SR-006: the outcome when source code was found — the caller MUST NOT
    dispatch the LLM call with this content, in any form."""

    reason: str


class LLMPayloadSanitizer:
    """SR-006: mandatory sanitization gate. Returns a typed result callers
    must branch on — there is no implicit pass-through. Never logs the
    offending text itself, only the category/reason (SR-006 AC: "sufficient
    context to audit the event without logging the offending content
    itself")."""

    @staticmethod
    def sanitize(text: str) -> SanitizedPayload | SanitizationBlocked:
        for pattern in _CODE_PATTERNS:
            if pattern.search(text):
                log.warning("llm_sanitizer.blocked", reason="source_code")
                return SanitizationBlocked(reason="source_code")

        redactions: list[str] = []
        sanitized = text
        for category, pattern in _PII_PATTERN_CATEGORIES.items():
            if pattern.search(sanitized):
                sanitized = pattern.sub("[REDACTED]", sanitized)
                redactions.append(category)

        if redactions:
            log.warning("llm_sanitizer.pii_stripped", categories=redactions)
        return SanitizedPayload(text=sanitized, redactions=redactions)


# ────────────────────────────────────────────────────────────────────────
# FR-020: platform-level shared resource visibility
# ────────────────────────────────────────────────────────────────────────
#
# Once a resource is designated platform-level shared, it must be visible
# to EVERY org's Organization Administrators/Content Managers (FR-020), not
# just the owning org. The chassis's automatic TenantScoped filter (app/db.py)
# ANDs `org_id = current_org_id` onto every SELECT unconditionally while a
# current org is bound, so an ordinary `WHERE org_id = X OR is_platform_shared`
# query would still be silently narrowed back to org X only. The only way to
# see rows from other orgs is to temporarily unbind the current-org context
# var (the same escape hatch app/db.py itself documents), issue an EXPLICIT
# `org_id = X OR is_platform_shared` predicate ourselves, and restore the
# context var immediately after — this is the one, narrowly-scoped, clearly
# commented deviation from automatic tenant isolation FR-020 requires.


async def _select_own_org_or_shared(
    session: AsyncSession, model: type[Any], org_id: int, *extra_where: Any
) -> Sequence[Any]:
    """Return every row of `model` that is either owned by `org_id` or
    flagged `is_platform_shared` (any org), matching `*extra_where` too.
    Bypasses the TenantScoped auto-filter for the duration of this one query."""
    saved_org_id = get_current_org_id()
    set_current_org_id(None)
    try:
        stmt = select(model).where(
            or_(model.org_id == org_id, model.is_platform_shared.is_(True)), *extra_where
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    finally:
        set_current_org_id(saved_org_id)


async def _get_own_org_or_shared_one(
    session: AsyncSession, model: type[Any], org_id: int, resource_id: int
) -> Any | None:
    """Single-row variant of `_select_own_org_or_shared`, by primary key."""
    rows = await _select_own_org_or_shared(session, model, org_id, model.id == resource_id)
    return rows[0] if rows else None


# ────────────────────────────────────────────────────────────────────────
# Citation helpers
# ────────────────────────────────────────────────────────────────────────


def _parse_citations(json_str: str) -> list[Citation]:
    """Deserialise citations_json / sources_json into Citation objects."""
    try:
        raw: list[dict[str, Any]] = json.loads(json_str)
        return [Citation(source_name=c["source_name"], hyperlink=c["hyperlink"]) for c in raw]
    except Exception:
        return []


def _serialise_citations(citations: list[Citation]) -> str:
    """Serialise a list of Citation objects to a JSON string."""
    return json.dumps([{"source_name": c.source_name, "hyperlink": c.hyperlink} for c in citations])


# ────────────────────────────────────────────────────────────────────────
# QuestionCategory reads (FR-003)
# ────────────────────────────────────────────────────────────────────────


async def list_question_categories(
    session: AsyncSession,
) -> list[QuestionCategoryRead]:
    """Return all question categories visible to the current org (FR-003)."""
    result = await session.execute(
        select(QuestionCategory).order_by(QuestionCategory.name)
    )
    categories = result.scalars().all()
    return [QuestionCategoryRead.model_validate(c) for c in categories]


async def get_question_category(
    session: AsyncSession, category_id: int
) -> QuestionCategory:
    """Look up one category by id. Raises CategoryNotFound."""
    result = await session.execute(
        select(QuestionCategory).where(QuestionCategory.id == category_id)
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        raise CategoryNotFound(category_id)
    return cat


# ────────────────────────────────────────────────────────────────────────
# FAQ reads (FR-003, FR-004)
# ────────────────────────────────────────────────────────────────────────


async def list_faqs_by_category(
    session: AsyncSession, category_id: int
) -> list[FAQRead]:
    """Return FAQs in a given category (FR-003).

    Returns an empty list if the category exists but has no FAQs.
    The caller is responsible for verifying the category exists first
    (to distinguish 'no FAQs' from 'category not found').
    """
    result = await session.execute(
        select(FAQ)
        .where(FAQ.question_category_id == category_id)
        .order_by(FAQ.id)
    )
    faqs = result.scalars().all()
    # v0.2: delegates to to_faq_read (defined later in this module) so
    # every FAQ read surface — v0.1's category-scoped browse and v0.2's
    # direct create/get — reports the same full multi-select associations.
    return [await to_faq_read(session, f) for f in faqs]


async def get_faq(session: AsyncSession, faq_id: int, org_id: int) -> FAQRead:
    """Look up one FAQ by id. Raises FAQNotFound.

    v0.3 (FR-020): also resolves a platform-level shared FAQ belonging to a
    DIFFERENT org (read-only) — see `_get_own_org_or_shared_one`.
    """
    faq = await _get_own_org_or_shared_one(session, FAQ, org_id, faq_id)
    if faq is None:
        raise FAQNotFound(faq_id)
    return await to_faq_read(session, faq)


# ────────────────────────────────────────────────────────────────────────
# Ask a question (FR-002, FR-004, FR-005, FR-006, SR-002)
# ────────────────────────────────────────────────────────────────────────


async def _get_conversation_history(
    session: AsyncSession, session_id: str, user_id: int
) -> list[dict[str, str]]:
    """Retrieve prior turns in this session for multi-turn context (FR-005)."""
    result = await session.execute(
        select(InteractionLog)
        .where(
            InteractionLog.session_id == session_id,
            InteractionLog.user_id == user_id,
        )
        .order_by(InteractionLog.created_at)
    )
    turns = result.scalars().all()
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.question_text})
        if turn.response_text:
            messages.append({"role": "assistant", "content": turn.response_text})
    return messages


@audited(
    "assistant.question_asked",
    entity_type="interaction_log",
    capture_details=lambda log_entry: {
        "session_id": log_entry.session_id,
        "question_category_id": log_entry.question_category_id,
    },
)
async def ask_question(
    session: AsyncSession,
    user: User,
    payload: AskQuestionCreate,
    org_id: int,
) -> QuestionResponse:
    """Process a user question and return a structured response.

    Steps:
      1. SR-002: check for PII / source code — raise ContentBlocked if found.
      2. FR-005: retrieve prior conversation turns for multi-turn context.
      3. FR-003/FR-004: attempt deterministic FAQ match.
      4. If no FAQ match, call LLM via chassis app.llm.service.complete().
      5. FR-006: persist the interaction log record.
      6. Return QuestionResponse with response text, reasoning, citations.

    The @audited decorator records the interaction on success.
    """
    # Step 1: SR-002 content check
    _check_content(payload.question_text)

    # Step 2: FR-005 multi-turn history
    history: list[dict[str, str]] = []
    if payload.session_id:
        history = await _get_conversation_history(
            session, payload.session_id, user.id
        )

    # Step 3: deterministic FAQ lookup
    response_text = ""
    reasoning = ""
    citations: list[Citation] = []
    faq_matched = False

    if payload.question_category_id is not None:
        # Try to find a matching FAQ in the selected category
        faq_result = await session.execute(
            select(FAQ).where(
                FAQ.question_category_id == payload.question_category_id
            )
        )
        faqs = faq_result.scalars().all()
        # Simple keyword match — find the FAQ whose question best overlaps
        question_lower = payload.question_text.lower()
        best_faq: FAQ | None = None
        best_score = 0
        for faq in faqs:
            faq_words = set(faq.question.lower().split())
            question_words = set(question_lower.split())
            score = len(faq_words & question_words)
            if score > best_score:
                best_score = score
                best_faq = faq
        if best_faq is not None and best_score > 0:
            response_text = best_faq.answer
            reasoning = best_faq.reasoning
            citations = _parse_citations(best_faq.citations_json)
            faq_matched = True

    # Step 4: LLM fallback if no FAQ match
    if not faq_matched:
        response_text, reasoning, citations = await _call_llm(
            session=session,
            question=payload.question_text,
            history=history,
            org_id=org_id,
        )

    # Step 5: persist interaction log (FR-006)
    log_entry = InteractionLog(
        user_id=user.id,
        question_category_id=payload.question_category_id,
        session_id=payload.session_id,
        question_text=payload.question_text,
        response_text=response_text,
        reasoning=reasoning,
        sources_json=_serialise_citations(citations),
        rating=None,  # FR-006: null until user submits rating
    )
    session.add(log_entry)
    await session.flush()

    # Step 6: return structured response (FR-004)
    return QuestionResponse(
        interaction_log_id=log_entry.id,
        response_text=response_text,
        reasoning=reasoning,
        citations=citations,
        has_citations=len(citations) > 0,
    )


async def _call_llm(
    session: AsyncSession,
    question: str,
    history: list[dict[str, str]],
    org_id: int,
) -> tuple[str, str, list[Citation]]:
    """Call the chassis LLM service and parse the response.

    Returns (response_text, reasoning, citations).
    Falls back to a graceful no-LLM response if the key is unavailable.
    CON-001: uses app.llm.service.complete() — never a direct provider SDK.
    """
    try:
        from app.llm.service import LLMKeyUnavailable, complete  # noqa: PLC0415

        system_prompt = (
            "You are an accessibility assistant. Answer the user's question about "
            "accessibility clearly and helpfully. Provide: "
            "1) An expository response, "
            "2) Your reasoning, "
            "3) Any relevant source citations in JSON format. "
            "Format your response as JSON with keys: "
            '"response", "reasoning", "citations" (array of {"source_name", "hyperlink"}).'
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": question})

        result = await complete(
            session=session,
            provider="openai",
            model="gpt-4o-mini",
            messages=messages,
            org_id=org_id,
        )
        content = result["choices"][0]["message"]["content"]
        # Parse structured JSON response
        try:
            parsed = json.loads(content)
            response_text = str(parsed.get("response", content))
            reasoning = str(parsed.get("reasoning", ""))
            raw_citations = parsed.get("citations", [])
            citations = [
                Citation(
                    source_name=str(c.get("source_name", "")),
                    hyperlink=str(c.get("hyperlink", "")),
                )
                for c in raw_citations
                if isinstance(c, dict)
            ]
        except (json.JSONDecodeError, KeyError):
            response_text = content
            reasoning = ""
            citations = []
        return response_text, reasoning, citations

    except LLMKeyUnavailable:
        log.warning("llm.key_unavailable", org_id=org_id)
        return (
            "I was unable to retrieve an answer at this time. Please try again later "
            "or browse the FAQ categories for relevant information.",
            "LLM service unavailable — no API key configured for this organization.",
            [],
        )
    except Exception as exc:
        log.error("llm.call_failed", error=str(exc), org_id=org_id)
        return (
            "I encountered an error while processing your question. Please try again.",
            "",
            [],
        )


# ────────────────────────────────────────────────────────────────────────
# Rate an interaction (FR-006)
# ────────────────────────────────────────────────────────────────────────


@audited(
    "assistant.interaction_rated",
    entity_type="interaction_log",
    capture_details=lambda log_entry: {
        "interaction_log_id": log_entry.id,
        "rating": log_entry.rating,
    },
)
async def rate_interaction(
    session: AsyncSession,
    user: User,
    interaction_id: int,
    payload: RateInteractionUpdate,
) -> InteractionLogRead:
    """Submit or update a thumbs-up/down rating for an interaction (FR-006).

    SR-003: only the owning user may rate their own interaction.
    Rating is the ONLY mutable field on an interaction log.
    """
    result = await session.execute(
        select(InteractionLog).where(InteractionLog.id == interaction_id)
    )
    log_entry = result.scalar_one_or_none()
    if log_entry is None:
        raise InteractionLogNotFound(interaction_id)
    # SR-003: enforce user ownership
    if log_entry.user_id != user.id:
        raise InteractionLogAccessDenied(interaction_id)

    log_entry.rating = payload.rating
    await session.flush()
    return _to_interaction_log_read(log_entry)


# ────────────────────────────────────────────────────────────────────────
# Interaction log reads (FR-006, SR-003)
# ────────────────────────────────────────────────────────────────────────


def _to_interaction_log_read(entry: InteractionLog) -> InteractionLogRead:
    """Convert an InteractionLog ORM row to the read schema."""
    return InteractionLogRead(
        id=entry.id,
        org_id=entry.org_id,
        user_id=entry.user_id,
        question_category_id=entry.question_category_id,
        session_id=entry.session_id,
        question_text=entry.question_text,
        response_text=entry.response_text,
        reasoning=entry.reasoning,
        sources=_parse_citations(entry.sources_json),
        rating=entry.rating,
        created_at=entry.created_at,
    )


async def list_my_interactions(
    session: AsyncSession, user: User
) -> list[InteractionLogRead]:
    """Return the calling user's own interaction logs (SR-003 — own records only)."""
    result = await session.execute(
        select(InteractionLog)
        .where(InteractionLog.user_id == user.id)
        .order_by(InteractionLog.created_at.desc())
    )
    entries = result.scalars().all()
    return [_to_interaction_log_read(e) for e in entries]


async def get_interaction(
    session: AsyncSession, user: User, interaction_id: int, is_admin: bool = False
) -> InteractionLogRead:
    """Fetch a single interaction log record.

    SR-003:
      - End users may only access their own records.
      - Admins (is_admin=True) may access any record in the org.
      - Raises InteractionLogAccessDenied if a non-admin accesses another
        user's record (triggers in-app alert in the route layer).
    """
    result = await session.execute(
        select(InteractionLog).where(InteractionLog.id == interaction_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise InteractionLogNotFound(interaction_id)
    if not is_admin and entry.user_id != user.id:
        raise InteractionLogAccessDenied(interaction_id)
    return _to_interaction_log_read(entry)


async def list_org_interactions(
    session: AsyncSession,
) -> list[InteractionLogRead]:
    """Return all interaction logs in the current org (admin view, SR-003).

    TenantScoped auto-filter restricts to the current org automatically.
    """
    result = await session.execute(
        select(InteractionLog).order_by(InteractionLog.created_at.desc())
    )
    entries = result.scalars().all()
    return [_to_interaction_log_read(e) for e in entries]


# ═════════════════════════════════════════════════════════════════════════
# v0.2 increment — FR-007 through FR-017
# ═════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────────
# Content Manager role provisioning (supporting infrastructure)
#
# The chassis ships exactly two roles ("admin", "user" — app/rbac/service.py
# seed_chassis_rbac) and app/admin/routes.py's own role picker is hardcoded
# to {"user", "admin"}. Both are chassis-owned and immutable (CONSTITUTION
# Extension Model). REQUIREMENTS.md's "Content Manager" persona (FR-011,
# FR-013, FR-014, FR-016, FR-017) needs an intermediate permission tier that
# neither chassis role provides. Role/Permission/role_permissions are plain,
# slot-writable data tables (the whole point of the permission REGISTRY
# extension point), so this slot provisions its own "content_manager" role
# directly against them — no chassis code is modified.
# ────────────────────────────────────────────────────────────────────────


async def ensure_content_manager_role(session: AsyncSession) -> Role:
    """Get-or-create the "content_manager" role and keep its permission
    grants in sync with CONTENT_MANAGER_PERMISSIONS. Idempotent — safe to
    call on every use (mirrors app.rbac.service.seed_chassis_rbac's own
    idempotent get-or-create pattern)."""
    result = await session.execute(select(Role).where(Role.name == "content_manager"))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(
            name="content_manager",
            description="Accessibility Assistant Content Manager (slot-provisioned).",
        )
        session.add(role)
        await session.flush()

    perm_result = await session.execute(
        select(Permission).where(Permission.name.in_(CONTENT_MANAGER_PERMISSIONS))
    )
    perms = perm_result.scalars().all()
    for perm in perms:
        existing = await session.execute(
            select(role_permissions.c.role_id).where(
                role_permissions.c.role_id == role.id,
                role_permissions.c.permission_id == perm.id,
            )
        )
        if existing.scalar_one_or_none() is None:
            await session.execute(
                role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
            )
    await session.flush()
    return role


@audited(
    "assistant.content_manager_assigned",
    entity_type="membership",
    capture_details=lambda membership: {
        "user_id": membership.user_id,
        "org_id": membership.org_id,
    },
)
async def assign_content_manager(
    session: AsyncSession, org_id: int, target_user_id: int
) -> Membership:
    """Designate `target_user_id` as a Content Manager within `org_id`.

    Raises NotAnOrgMember if the target user has no membership in this org.
    """
    result = await session.execute(
        select(Membership).where(
            Membership.org_id == org_id, Membership.user_id == target_user_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotAnOrgMember(target_user_id)

    role = await ensure_content_manager_role(session)
    membership.role_id = role.id
    await session.flush()
    return membership


async def _ensure_baseline_role_grants(session: AsyncSession) -> None:
    """Grant assistant:read/assistant:ask to the chassis "user" role.

    PRE-EXISTING GAP found while building v0.2: app.rbac.service.seed_chassis_rbac
    (chassis-owned, immutable) only grants USERS_READ/ORGS_READ to the "user"
    role by default. Without this, a genuine non-admin end user (chassis role
    "user" — the only non-admin role the platform ships) could never use the
    self-service assistant at all, which contradicts FR-001's own stated
    purpose. There is no chassis extension point for additional default-role
    grants, so this slot performs the grant itself, idempotently, against the
    same plain Role/Permission/role_permissions tables used above.

    Deliberately NOT cached behind a "run once per process" flag: an earlier
    version of this function short-circuited after its first successful run,
    which is unsafe here because `role_permissions` can be reset independently
    of the process (the chassis test suite's `clean_db` fixture TRUNCATEs and
    re-seeds it before every test; an operator could analogously reset roles
    in production) — a stale "already ensured" flag would then silently skip
    re-granting against the fresh, empty table. Each call is 1-2 cheap
    indexed SELECTs plus conditional inserts — negligible next to the rest of
    a request's cost, and correctness matters more here than the micro-
    optimization.

    ACKNOWLEDGED LIMITATION: this call happens inside the tiered-answering
    service functions, which only run AFTER the route's `requires(ASSISTANT_ASK)`
    dependency has already checked the permission. So the very first
    assistant:ask/answer request ever made by a genuinely non-admin "user"-role
    member (before any admin-role user in the org has ever asked a question,
    which is what actually triggers this grant) would still 403. There is no
    slot extension point that runs before the chassis's own permission
    dependency, so closing that first-request edge case is out of this
    increment's reach without a chassis change.
    """
    result = await session.execute(select(Role).where(Role.name == "user"))
    user_role = result.scalar_one_or_none()
    if user_role is not None:
        perm_result = await session.execute(
            select(Permission).where(Permission.name.in_([ASSISTANT_READ, ASSISTANT_ASK]))
        )
        for perm in perm_result.scalars().all():
            existing = await session.execute(
                select(role_permissions.c.role_id).where(
                    role_permissions.c.role_id == user_role.id,
                    role_permissions.c.permission_id == perm.id,
                )
            )
            if existing.scalar_one_or_none() is None:
                await session.execute(
                    role_permissions.insert().values(
                        role_id=user_role.id, permission_id=perm.id
                    )
                )
        await session.flush()


# ────────────────────────────────────────────────────────────────────────
# Information Source Categories (FR-010, T-002)
# ────────────────────────────────────────────────────────────────────────


@audited(
    "assistant.information_source_category_created",
    entity_type="information_source_category",
    capture_details=lambda c: {"id": c.id, "name": c.name},
)
async def create_information_source_category(
    session: AsyncSession, user: User, name: str, description: str | None
) -> InformationSourceCategory:
    """Create an information source category (FR-010).

    Raises DuplicateCategoryName if a category with this name already
    exists in the current org. The uniqueness check is performed before
    any database write (T-002 acceptance criteria).
    """
    existing = await session.execute(
        select(InformationSourceCategory).where(InformationSourceCategory.name == name)
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateCategoryName(name)

    category = InformationSourceCategory(
        name=name, description=description, created_by_user_id=user.id
    )
    session.add(category)
    await session.flush()
    return category


async def list_information_source_categories(
    session: AsyncSession, org_id: int
) -> list[InformationSourceCategoryRead]:
    """Return all information source categories in the current org, plus any
    platform-level shared categories from other orgs (FR-010, FR-020)."""
    categories = await _select_own_org_or_shared(session, InformationSourceCategory, org_id)
    categories = sorted(categories, key=lambda c: c.name)
    return [InformationSourceCategoryRead.model_validate(c) for c in categories]


async def get_information_source_category(
    session: AsyncSession, category_id: int
) -> InformationSourceCategory:
    result = await session.execute(
        select(InformationSourceCategory).where(InformationSourceCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise InformationSourceCategoryNotFound(category_id)
    return category


# ────────────────────────────────────────────────────────────────────────
# Information Sources (FR-011..FR-014, T-003)
# ────────────────────────────────────────────────────────────────────────


def list_source_types() -> list[dict[str, str]]:
    """Return the four supported information source types (FR-011)."""
    return list(SOURCE_TYPES)


def test_local_folder_access(folder_path: str) -> bool:
    """Test read access to a local folder WITHOUT executing anything found
    inside it (FR-012's no-execute rule). Only `Path`/`os.access` calls —
    no subprocess, exec, or eval.
    """
    path = Path(folder_path)
    return path.is_dir() and os.access(path, os.R_OK)


async def test_github_access(github_url: str, access_token: str | None) -> bool:
    """Test read access to a GitHub/online repo (FR-013's no-execute rule).

    Performs a single read-only HTTP GET against the repo's API endpoint —
    never clones, executes, or evaluates any repository content.
    Network/parse failures are treated as a failed test (never raised).
    """
    api_url = _github_api_url(github_url)
    if api_url is None:
        return False
    headers = {"Authorization": f"token {access_token}"} if access_token else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url, headers=headers)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _github_api_url(github_url: str) -> str | None:
    """Convert a GitHub repo URL into its REST API equivalent, e.g.
    https://github.com/owner/repo -> https://api.github.com/repos/owner/repo.
    Returns None if the URL is not a recognizable GitHub repo URL.
    """
    cleaned = github_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    marker = "github.com/"
    idx = cleaned.find(marker)
    if idx == -1:
        return None
    path = cleaned[idx + len(marker) :]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    return f"https://api.github.com/repos/{owner}/{repo}"


async def test_mcp_connectivity(
    mcp_server_address: str, credentials: MCPCredentials | None
) -> bool:
    """Test connectivity to an MCP server via the chassis MCP client
    (app.mcp.client — the same SDK wrapper app/mcp/service.py uses),
    rather than re-implementing the MCP protocol in this slot.
    """
    credential = None
    if credentials is not None:
        credential = credentials.api_key or credentials.password
    try:
        from app.mcp.client import MCPClientError  # noqa: PLC0415
        from app.mcp.client import list_tools as _mcp_list_tools  # noqa: PLC0415

        await _mcp_list_tools(
            url=mcp_server_address, credential=credential, timeout_seconds=10.0
        )
        return True
    except MCPClientError:
        return False
    except Exception:  # pragma: no cover - defensive: never let a test crash a route
        log.error("assistant.mcp_test_unexpected_error", address=mcp_server_address)
        return False


async def _run_connectivity_test(payload: InformationSourceCreate) -> bool:
    """Dispatch to the right connectivity test for `payload`'s source_type."""
    if isinstance(payload, LocalCodeRepoSourceCreate):
        return test_local_folder_access(payload.folder_path)
    if isinstance(payload, MCPServerSourceCreate):
        return await test_mcp_connectivity(payload.mcp_server_address, payload.credentials)
    if isinstance(payload, GitHubOnlineRepoSourceCreate):
        return await test_github_access(payload.github_url, payload.access_token)
    # DocumentFolderSourceCreate
    return test_local_folder_access(payload.folder_path)


@audited(
    "assistant.information_source_created",
    entity_type="information_source",
    capture_details=lambda s: {"id": s.id, "name": s.name, "source_type": s.source_type},
)
async def create_information_source(
    session: AsyncSession, user: User, payload: InformationSourceCreate
) -> InformationSource:
    """Create an information source (FR-011..FR-014).

    The connectivity/read-access test runs synchronously as part of this
    call — the source is only persisted if the test succeeds (FR-012's
    "on failure ... the source is not saved until a successful test", and
    FR-014's "requires successful Test MCP before save"). Raises
    InformationSourceCategoryNotFound if category_id doesn't resolve in
    this org, or SourceTestFailed if the connectivity test fails.
    """
    await get_information_source_category(session, payload.category_id)

    ok = await _run_connectivity_test(payload)
    if not ok:
        raise SourceTestFailed(
            f"Connectivity/read-access test failed for source type {payload.source_type!r}."
        )

    credentials_encrypted: str | None = None
    folder_path: str | None = None
    github_url: str | None = None
    mcp_server_address: str | None = None

    if isinstance(payload, LocalCodeRepoSourceCreate | DocumentFolderSourceCreate):
        folder_path = payload.folder_path
    elif isinstance(payload, GitHubOnlineRepoSourceCreate):
        github_url = payload.github_url
        if payload.access_token:
            credentials_encrypted = CredentialEncryptionService.encrypt(
                {"access_token": payload.access_token}
            )
    else:
        mcp_server_address = payload.mcp_server_address
        if payload.credentials is not None:
            creds_dict = payload.credentials.model_dump(exclude_none=True)
            if creds_dict:
                credentials_encrypted = CredentialEncryptionService.encrypt(creds_dict)

    source = InformationSource(
        category_id=payload.category_id,
        name=payload.name,
        source_type=payload.source_type,
        folder_path=folder_path,
        github_url=github_url,
        mcp_server_address=mcp_server_address,
        credentials_encrypted=credentials_encrypted,
        test_status=InformationSourceTestStatus.SUCCESS.value,
        last_tested_at=datetime.now(UTC),
        created_by_user_id=user.id,
    )
    session.add(source)
    await session.flush()
    return source


def to_information_source_read(source: InformationSource) -> InformationSourceRead:
    return InformationSourceRead(
        id=source.id,
        org_id=source.org_id,
        category_id=source.category_id,
        name=source.name,
        source_type=source.source_type,
        folder_path=source.folder_path,
        github_url=source.github_url,
        mcp_server_address=source.mcp_server_address,
        credential_set=source.credentials_encrypted is not None,
        test_status=source.test_status,
        last_tested_at=source.last_tested_at,
        created_by_user_id=source.created_by_user_id,
        is_platform_shared=source.is_platform_shared,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


async def list_information_sources(
    session: AsyncSession, org_id: int
) -> list[InformationSourceRead]:
    """Return all information sources in the current org, plus any
    platform-level shared sources from other orgs (FR-011, FR-020)."""
    sources = await _select_own_org_or_shared(session, InformationSource, org_id)
    sources = sorted(sources, key=lambda s: s.name)
    return [to_information_source_read(s) for s in sources]


async def get_information_source(session: AsyncSession, source_id: int) -> InformationSource:
    result = await session.execute(
        select(InformationSource).where(InformationSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise InformationSourceNotFound(source_id)
    return source


# ────────────────────────────────────────────────────────────────────────
# Question Categories — creation (FR-015, T-005)
# ────────────────────────────────────────────────────────────────────────


@audited(
    "assistant.question_category_created",
    entity_type="question_category",
    capture_details=lambda c: {"id": c.id, "name": c.name},
)
async def create_question_category(
    session: AsyncSession, user: User, name: str, description: str | None
) -> QuestionCategory:
    """Create a question category (FR-015).

    Uniqueness is case-insensitive within the current org (T-005
    implementation notes), checked before any database write.
    """
    existing = await session.execute(
        select(QuestionCategory).where(func.lower(QuestionCategory.name) == name.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateCategoryName(name)

    category = QuestionCategory(name=name, description=description, created_by_user_id=user.id)
    session.add(category)
    await session.flush()
    return category


# ────────────────────────────────────────────────────────────────────────
# FAQ — manual creation (FR-016, T-006)
# ────────────────────────────────────────────────────────────────────────


async def _resolve_ids_in_org(
    session: AsyncSession, model: type[Any], ids: list[int], label: str
) -> None:
    """Raise FAQValidationError naming `label` if any of `ids` doesn't
    resolve to a row visible in the current org (TenantScoped auto-filter
    handles the org scoping)."""
    if not ids:
        raise FAQValidationError(f"at least one {label} is required")
    result = await session.execute(select(model.id).where(model.id.in_(ids)))
    found = {row[0] for row in result.all()}
    missing = set(ids) - found
    if missing:
        raise FAQValidationError(f"unknown {label} id(s): {sorted(missing)}")


@audited(
    "assistant.faq_created",
    entity_type="faq",
    capture_details=lambda f: {"id": f.id, "question": f.question[:80]},
)
async def create_faq(session: AsyncSession, user: User, payload: FAQCreate) -> FAQ:
    """Manually create an FAQ with multi-select category/source associations
    (FR-016). Raises FAQValidationError if any referenced id is unresolvable
    within the current org. All writes happen in a single transaction.
    """
    await _resolve_ids_in_org(
        session, QuestionCategory, payload.question_category_ids, "question category"
    )
    await _resolve_ids_in_org(
        session,
        InformationSourceCategory,
        payload.source_category_ids,
        "source category",
    )
    await _resolve_ids_in_org(session, InformationSource, payload.source_ids, "source")

    faq = FAQ(
        # Backward-compatible single FK — set to the first selected category
        # so v0.1's category-scoped FAQ matching keeps working unmodified.
        question_category_id=payload.question_category_ids[0],
        question=payload.question,
        answer=payload.answer,
        created_by_user_id=user.id,
    )
    session.add(faq)
    await session.flush()

    session.add_all(
        FAQQuestionCategory(faq_id=faq.id, question_category_id=qc_id)
        for qc_id in payload.question_category_ids
    )
    session.add_all(
        FAQSourceCategory(faq_id=faq.id, source_category_id=sc_id)
        for sc_id in payload.source_category_ids
    )
    session.add_all(
        FAQSource(faq_id=faq.id, source_id=s_id) for s_id in payload.source_ids
    )
    await session.flush()
    return faq


async def _faq_associated_ids(
    session: AsyncSession, faq_id: int, junction: type[Any], column_name: str
) -> list[int]:
    column = getattr(junction, column_name)
    result = await session.execute(select(column).where(junction.faq_id == faq_id))
    return [row[0] for row in result.all()]


async def to_faq_read(session: AsyncSession, faq: FAQ) -> FAQRead:
    """Build the full FAQRead for `faq`, including v0.2's multi-select
    association lists (falls back gracefully for pre-v0.2 rows)."""
    question_category_ids = await _faq_associated_ids(
        session, faq.id, FAQQuestionCategory, "question_category_id"
    )
    if not question_category_ids and faq.question_category_id is not None:
        question_category_ids = [faq.question_category_id]
    source_category_ids = await _faq_associated_ids(
        session, faq.id, FAQSourceCategory, "source_category_id"
    )
    source_ids = await _faq_associated_ids(session, faq.id, FAQSource, "source_id")

    return FAQRead(
        id=faq.id,
        org_id=faq.org_id,
        question_category_id=faq.question_category_id,
        question=faq.question,
        answer=faq.answer,
        reasoning=faq.reasoning,
        citations=_parse_citations(faq.citations_json),
        created_at=faq.created_at,
        updated_at=faq.updated_at,
        question_category_ids=question_category_ids,
        source_category_ids=source_category_ids,
        source_ids=source_ids,
        is_platform_shared=faq.is_platform_shared,
    )


# ────────────────────────────────────────────────────────────────────────
# Tiered question answering (FR-007, FR-008, T-015, T-016)
# ────────────────────────────────────────────────────────────────────────


def _normalize_for_slug(text: str) -> str:
    """Lowercase + strip everything but alphanumerics, for exact-slug
    comparison (FR-007's "exact-match slug" tier)."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


async def _faq_match_tiered(
    session: AsyncSession, question_text: str
) -> tuple[FAQ, str] | None:
    """Attempt to match `question_text` against every FAQ in the current
    org, in FR-007's stated priority order: exact-match slug -> keyword
    set -> regex pattern. Returns (faq, match_kind) or None.
    """
    result = await session.execute(select(FAQ))
    faqs = result.scalars().all()
    if not faqs:
        return None

    # Tier 1: exact-match slug.
    target_slug = _normalize_for_slug(question_text)
    for faq in faqs:
        if _normalize_for_slug(faq.question) == target_slug:
            return faq, "exact_slug"

    # Tier 2: keyword-set overlap (best score wins; score must be > 0).
    question_words = set(question_text.lower().split())
    best_faq: FAQ | None = None
    best_score = 0
    for faq in faqs:
        score = len(set(faq.question.lower().split()) & question_words)
        if score > best_score:
            best_score = score
            best_faq = faq
    if best_faq is not None and best_score > 0:
        return best_faq, "keyword_set"

    # Tier 3: regex pattern (only FAQs with an explicit match_pattern).
    for faq in faqs:
        if not faq.match_pattern:
            continue
        try:
            if re.search(faq.match_pattern, question_text, re.IGNORECASE):
                return faq, "regex"
        except re.error:
            continue

    return None


def _script_tier_lookup() -> None:
    """The "applicable Python scripts executed against configured
    information sources" tier described in T-015.

    DELIBERATELY A NO-OP. DESIGN.md/REQUIREMENTS.md never define a script
    storage or authoring mechanism for information sources, and FR-012/
    FR-013's own "Critical Security Control" states a STRICT no-execute
    rule: code in a connected source is NEVER executed by the system. Per
    CLAUDE.md, the CONSTITUTION's security invariants are supreme over a
    requirement's literal wording when the two conflict — building real
    arbitrary script execution against customer-configured sources would
    violate that invariant with no safe design specified anywhere in the
    Build Package. This function preserves the THREE-TIER PIPELINE SHAPE
    (FAQ -> script -> LLM) and its observable behavior (no script tier is
    ever "applicable" because none can be safely authored in this
    increment) without executing anything. Flagged explicitly here and in
    the v0.2 completion report as a spec self-contradiction resolved in
    favor of the security invariant.
    """
    return None


@audited(
    "assistant.question_resolved",
    entity_type="interaction_log",
    capture_details=lambda result: {
        "tier": result["tier"],
        "interaction_log_id": result["interaction_log_id"],
        "alert_sent": result["alert_sent"],
    },
)
async def resolve_question_tiered(
    session: AsyncSession,
    user: User,
    org_id: int,
    question_text: str,
    question_category_id: int | None,
    session_id: str | None,
    *,
    dispatch_alert_on_unanswerable: bool,
) -> dict[str, Any]:
    """Shared tiered-resolution pipeline backing both T-015 and T-016's
    endpoints: deterministic FAQ match -> (inert) script tier -> LLM
    fallback (mode selected via LLMFallbackConfig) -> unanswerable.

    Returns a dict with keys: tier, response_text, reasoning, citations,
    llm_invoked, alert_sent, interaction_log_id. Always persists an
    InteractionLog row (FR-006) regardless of which tier resolved it.
    """
    _check_content(question_text)
    await _ensure_baseline_role_grants(session)

    history: list[dict[str, str]] = []
    if session_id:
        history = await _get_conversation_history(session, session_id, user.id)

    tier = "unanswerable"
    response_text = ""
    reasoning = ""
    citations: list[Citation] = []
    llm_invoked = False
    alert_sent = False

    # Tier 1: deterministic FAQ match (FR-007).
    match = await _faq_match_tiered(session, question_text)
    if match is not None:
        faq, _match_kind = match
        response_text = faq.answer
        reasoning = faq.reasoning
        citations = _parse_citations(faq.citations_json)
        tier = "faq"
    else:
        # Tier 2: script execution against configured sources — inert (see
        # _script_tier_lookup's docstring).
        _script_tier_lookup()

        # Tier 3: LLM fallback (FR-008), mode selected via FR-009 config.
        mode = await _resolve_llm_fallback_mode(session, question_category_id)
        llm_invoked = True
        try:
            response_text, reasoning, citations = await _call_llm_tiered(
                session=session,
                question=question_text,
                history=history,
                org_id=org_id,
                mode=mode,
            )
            tier = "llm_retrieval_augmented" if mode == "retrieval_augmented" else "llm_frontier"
        except _UnanswerableError:
            tier = "unanswerable"
            llm_invoked = False

    if tier == "unanswerable" and dispatch_alert_on_unanswerable:
        await dispatch_unanswerable_alert(session, org_id, user, question_text)
        alert_sent = True

    log_entry = InteractionLog(
        user_id=user.id,
        question_category_id=question_category_id,
        session_id=session_id,
        question_text=question_text,
        response_text=response_text,
        reasoning=reasoning,
        sources_json=_serialise_citations(citations),
        rating=None,
    )
    session.add(log_entry)
    await session.flush()

    return {
        "tier": tier,
        "response_text": response_text,
        "reasoning": reasoning,
        "citations": citations,
        "llm_invoked": llm_invoked,
        "alert_sent": alert_sent,
        "interaction_log_id": log_entry.id,
    }


class _UnanswerableError(Exception):
    """Internal signal: the LLM fallback tier could not produce a sufficient
    response (LLM unavailable or a transport failure)."""


async def _resolve_llm_fallback_mode(
    session: AsyncSession, question_category_id: int | None
) -> str:
    """Resolve the LLM fallback mode for this question (FR-009).

    The request carries only a question_category_id (no source_category_id
    — DESIGN.md's question-submission contract doesn't include one), so
    when a question category is given this looks up ANY configured
    LLMFallbackConfig row for that question category in the current org
    (first match wins if more than one source category has been
    configured for it). Falls back to "frontier_general_knowledge" — the
    mode that needs no information-source grounding — when nothing is
    configured or no category was given.
    """
    if question_category_id is None:
        return "frontier_general_knowledge"
    result = await session.execute(
        select(LLMFallbackConfig)
        .where(LLMFallbackConfig.question_category_id == question_category_id)
        .order_by(LLMFallbackConfig.id)
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if config is None:
        return "frontier_general_knowledge"
    return config.mode


async def _call_llm_tiered(
    session: AsyncSession,
    question: str,
    history: list[dict[str, str]],
    org_id: int,
    mode: str,
) -> tuple[str, str, list[Citation]]:
    """Call the chassis LLM service, grounded against configured
    information sources when mode == "retrieval_augmented" (FR-009).

    Raises _UnanswerableError if the LLM tier cannot produce a response
    (no key configured, or a transport failure) — the caller treats that
    as "both tiers exhausted" (FR-008).

    SR-006: the question and grounding context are run through
    LLMPayloadSanitizer before the payload is ever assembled. A block (source
    code detected) is treated identically to "no LLM tier available" —
    _UnanswerableError — so the call is never dispatched (FR-008's existing
    unanswerable/alert path handles the rest).
    """
    from app.llm.service import LLMKeyUnavailable, complete  # noqa: PLC0415
    from app.llm.transport import LLMError  # noqa: PLC0415

    grounding = ""
    if mode == "retrieval_augmented":
        grounding = await _build_grounding_context(session)

    question_result = LLMPayloadSanitizer.sanitize(question)
    if isinstance(question_result, SanitizationBlocked):
        raise _UnanswerableError("question payload blocked by SR-006 sanitizer")
    sanitized_question = question_result.text

    sanitized_grounding = ""
    if grounding:
        grounding_result = LLMPayloadSanitizer.sanitize(grounding)
        if isinstance(grounding_result, SanitizationBlocked):
            raise _UnanswerableError("grounding payload blocked by SR-006 sanitizer")
        sanitized_grounding = grounding_result.text

    system_prompt = (
        "You are an accessibility assistant. Answer the user's question about "
        "accessibility clearly and helpfully. Provide: "
        "1) An expository response, "
        "2) Your reasoning, "
        "3) Any relevant source citations in JSON format. "
        "Format your response as JSON with keys: "
        '"response", "reasoning", "citations" (array of {"source_name", "hyperlink"}).'
    )
    if sanitized_grounding:
        system_prompt += (
            "\n\nGround your answer in the following configured information "
            f"sources when relevant:\n{sanitized_grounding}"
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": sanitized_question})

    try:
        result = await complete(
            session=session,
            provider="openai",
            model="gpt-4o-mini",
            messages=messages,
            org_id=org_id,
        )
    except LLMKeyUnavailable as exc:
        log.warning("llm.key_unavailable", org_id=org_id)
        raise _UnanswerableError("no LLM key configured") from exc
    except LLMError as exc:
        log.error("llm.call_failed", error=str(exc), org_id=org_id)
        raise _UnanswerableError("LLM transport failure") from exc

    content = result["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
        response_text = str(parsed.get("response", content))
        reasoning = str(parsed.get("reasoning", ""))
        raw_citations = parsed.get("citations", [])
        citations = [
            Citation(
                source_name=str(c.get("source_name", "")),
                hyperlink=str(c.get("hyperlink", "")),
            )
            for c in raw_citations
            if isinstance(c, dict)
        ]
    except (json.JSONDecodeError, KeyError, AttributeError):
        response_text = content
        reasoning = ""
        citations = []
    return response_text, reasoning, citations


async def _build_grounding_context(session: AsyncSession) -> str:
    """Build a short textual summary of configured information sources for
    the retrieval-augmented prompt (FR-009). This chassis ships no vector
    store / content-indexing pipeline, so "grounding" here is limited to
    naming the org's configured sources and categories rather than
    retrieving indexed source content — a bounded, honest interpretation
    given what the Build Package actually specifies.
    """
    result = await session.execute(select(InformationSource).order_by(InformationSource.name))
    sources = result.scalars().all()
    if not sources:
        return ""
    lines = [f"- {s.name} ({s.source_type})" for s in sources]
    return "\n".join(lines)


async def answer_question_deterministic_first(
    session: AsyncSession, user: User, payload: AskQuestionCreate, org_id: int
) -> dict[str, Any]:
    """T-015 (FR-007): deterministic-first question answering."""
    result = await resolve_question_tiered(
        session,
        user,
        org_id,
        payload.question_text,
        payload.question_category_id,
        payload.session_id,
        dispatch_alert_on_unanswerable=False,
    )
    # Simplify the 5-way tier into T-015's 3-way "source" field.
    source = "faq" if result["tier"] == "faq" else ("llm" if result["llm_invoked"] else "script")
    result["source"] = source
    return result


async def answer_question_with_fallback(
    session: AsyncSession, user: User, payload: AskQuestionCreate, org_id: int
) -> dict[str, Any]:
    """T-016 (FR-008): full tiered fallback with unanswerable alerting."""
    return await resolve_question_tiered(
        session,
        user,
        org_id,
        payload.question_text,
        payload.question_category_id,
        payload.session_id,
        dispatch_alert_on_unanswerable=True,
    )


# ────────────────────────────────────────────────────────────────────────
# Unanswerable-question alerts (FR-008)
# ────────────────────────────────────────────────────────────────────────


async def _resolve_alert_recipients(session: AsyncSession, org_id: int) -> list[User]:
    """Return the org's Organization Administrators and Content Managers
    (FR-008's stated alert recipients) — i.e. every member whose per-org
    role is "admin" or "content_manager"."""
    result = await session.execute(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.org_id == org_id, Role.name.in_(["admin", "content_manager"]))
    )
    return list(result.scalars().all())


async def dispatch_unanswerable_alert(
    session: AsyncSession, org_id: int, user: User, question_text: str
) -> QuestionAlert:
    """Create a QuestionAlert row and notify every Organization
    Administrator / Content Manager in the org (FR-008)."""
    from app.notifications.service import notify  # noqa: PLC0415

    alert = QuestionAlert(
        alert_type="unanswerable_question",
        question_text=question_text,
        submitting_user_id=user.id,
        submitting_user_name=user.full_name or user.email,
    )
    session.add(alert)
    await session.flush()

    recipients = await _resolve_alert_recipients(session, org_id)
    for recipient in recipients:
        try:
            await notify(
                session=session,
                user_id=recipient.id,
                title="No answer available for a submitted question",
                body=(
                    f"{alert.submitting_user_name} asked a question that could not "
                    f"be answered: {question_text}"
                ),
                level="warning",
                org_id=org_id,
            )
        except Exception:  # pragma: no cover - notification failure must not break the flow
            log.error("assistant.alert_notify_failed", recipient_id=recipient.id)
    return alert


def _to_alert_read(alert: QuestionAlert) -> QuestionAlertRead:
    return QuestionAlertRead(
        id=alert.id,
        org_id=alert.org_id,
        alert_type=alert.alert_type,
        question_text=alert.question_text,
        submitting_user_name=alert.submitting_user_name,
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )


async def list_question_alerts(session: AsyncSession) -> list[QuestionAlertRead]:
    """Return unanswerable-question alerts for the current org (FR-008)."""
    result = await session.execute(select(QuestionAlert).order_by(QuestionAlert.created_at.desc()))
    alerts = result.scalars().all()
    return [_to_alert_read(a) for a in alerts]


@audited(
    "assistant.question_alert_acknowledged",
    entity_type="question_alert",
    capture_details=lambda a: {"id": a.id},
)
async def acknowledge_question_alert(
    session: AsyncSession, user: User, alert_id: int
) -> QuestionAlert:
    """Mark an alert acknowledged (FR-008). Raises QuestionAlertNotFound."""
    result = await session.execute(select(QuestionAlert).where(QuestionAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise QuestionAlertNotFound(alert_id)
    alert.acknowledged = True
    alert.acknowledged_by_user_id = user.id
    alert.acknowledged_at = datetime.now(UTC)
    await session.flush()
    return alert


# ────────────────────────────────────────────────────────────────────────
# LLM Fallback Configuration (FR-009, T-017)
# ────────────────────────────────────────────────────────────────────────


async def list_llm_fallback_configs(session: AsyncSession) -> list[LLMFallbackConfig]:
    """Return all LLM fallback configs for the current org (FR-009)."""
    result = await session.execute(select(LLMFallbackConfig).order_by(LLMFallbackConfig.id))
    return list(result.scalars().all())


async def get_llm_fallback_config(
    session: AsyncSession, source_category_id: int, question_category_id: int
) -> LLMFallbackConfig:
    result = await session.execute(
        select(LLMFallbackConfig).where(
            LLMFallbackConfig.source_category_id == source_category_id,
            LLMFallbackConfig.question_category_id == question_category_id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise LLMFallbackConfigNotFound((source_category_id, question_category_id))
    return config


@audited(
    "assistant.llm_fallback_config_upserted",
    entity_type="llm_fallback_config",
    capture_details=lambda c: {
        "source_category_id": c.source_category_id,
        "question_category_id": c.question_category_id,
        "mode": c.mode,
    },
)
async def upsert_llm_fallback_config(
    session: AsyncSession,
    source_category_id: int,
    question_category_id: int,
    mode: str,
) -> LLMFallbackConfig:
    """Create or update the fallback mode for (source_category_id,
    question_category_id) (FR-009). Raises InformationSourceCategoryNotFound
    or CategoryNotFound if either id doesn't resolve in the current org.
    """
    await get_information_source_category(session, source_category_id)
    await get_question_category(session, question_category_id)

    try:
        config = await get_llm_fallback_config(
            session, source_category_id, question_category_id
        )
        config.mode = mode
    except LLMFallbackConfigNotFound:
        config = LLMFallbackConfig(
            source_category_id=source_category_id,
            question_category_id=question_category_id,
            mode=mode,
        )
        session.add(config)
    await session.flush()
    return config


async def delete_llm_fallback_config(
    session: AsyncSession, source_category_id: int, question_category_id: int
) -> None:
    """Delete a fallback config (FR-009). Raises LLMFallbackConfigNotFound."""
    config = await get_llm_fallback_config(session, source_category_id, question_category_id)
    await session.delete(config)
    await session.flush()


# ═════════════════════════════════════════════════════════════════════════
# v0.3 increment — FR-017 through FR-022, SR-005 through SR-007, NFR-001
# ═════════════════════════════════════════════════════════════════════════


# ────────────────────────────────────────────────────────────────────────
# Response Helpfulness Rating (FR-019, T-019)
# ────────────────────────────────────────────────────────────────────────


@audited(
    "interaction_log.rate",
    entity_type="interaction_log",
    capture_details=lambda entry: {
        "interaction_log_id": entry.id,
        "helpfulness_rating": entry.helpfulness_rating,
    },
)
async def submit_helpfulness_rating(
    session: AsyncSession, user: User, log_id: int, rating: str
) -> InteractionLog:
    """Submit a write-once helpfulness rating for an interaction log (FR-019).

    Distinct from the legacy v0.1 `rate_interaction`/`rating` mechanism (see
    InteractionLog's class docstring) — this field, once set, can never be
    changed: a second attempt raises RatingAlreadySubmitted (-> 409). Only
    the owning end user may rate their own interaction (mirrors SR-003's
    existing `rate_interaction` precedent); a different user's record in the
    SAME org raises InteractionLogAccessDenied (-> 403). A record in a
    DIFFERENT org is never found at all (TenantScoped auto-filter -> 404).
    """
    result = await session.execute(select(InteractionLog).where(InteractionLog.id == log_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise InteractionLogNotFound(log_id)
    if entry.user_id != user.id:
        raise InteractionLogAccessDenied(log_id)
    if entry.helpfulness_rating is not None:
        raise RatingAlreadySubmitted(log_id)

    entry.helpfulness_rating = rating
    await session.flush()
    return entry


# ────────────────────────────────────────────────────────────────────────
# Platform-Level Resource Sharing (FR-020, T-020)
# ────────────────────────────────────────────────────────────────────────
#
# FR-020's "Platform Administrator" is NOT expressible as an RBAC permission
# in this chassis: every registered permission (including
# assistant:platform_share) is auto-granted to the single chassis "admin"
# Role, held both chassis-wide (true superusers) AND per-org (ordinary org
# creators) — see __init__.py's own note. So the route-level `requires(...)`
# gate alone cannot distinguish the two; `_share_resource` adds the missing
# check explicitly against `user.is_superuser`, matching the same pattern
# app/rbac/service.py's own `is_privileged_user` already establishes for
# this exact distinction.


async def _share_resource(
    session: AsyncSession, model: type[Any], resource_id: int, is_shared: bool, user: User
) -> Any:
    """Shared implementation behind share_information_source_category /
    share_information_source / share_faq. Raises PlatformShareDenied unless
    `user.is_superuser`. A genuine Platform Administrator may act on ANY
    org's resource by id (not just their own current org) — the lookup
    explicitly bypasses the TenantScoped auto-filter for this one query,
    the only permitted deviation from automatic tenant isolation for this
    feature (mirrors T-020's own implementation note)."""
    if not user.is_superuser:
        raise PlatformShareDenied()

    saved_org_id = get_current_org_id()
    set_current_org_id(None)
    try:
        result = await session.execute(select(model).where(model.id == resource_id))
        resource = result.scalar_one_or_none()
    finally:
        set_current_org_id(saved_org_id)

    if resource is None:
        return None

    resource.is_platform_shared = is_shared
    await session.flush()
    return resource


@audited(
    "assistant.information_source_category_shared",
    entity_type="information_source_category",
    capture_details=lambda c: {"id": c.id, "is_platform_shared": c.is_platform_shared},
)
async def share_information_source_category(
    session: AsyncSession, user: User, category_id: int, is_shared: bool
) -> InformationSourceCategory:
    """Designate an information source category platform-level shared
    (FR-020). Raises PlatformShareDenied or InformationSourceCategoryNotFound."""
    category = await _share_resource(session, InformationSourceCategory, category_id, is_shared, user)
    if category is None:
        raise InformationSourceCategoryNotFound(category_id)
    return cast(InformationSourceCategory, category)


@audited(
    "assistant.information_source_shared",
    entity_type="information_source",
    capture_details=lambda s: {"id": s.id, "is_platform_shared": s.is_platform_shared},
)
async def share_information_source(
    session: AsyncSession, user: User, source_id: int, is_shared: bool
) -> InformationSource:
    """Designate an information source platform-level shared (FR-020).
    Raises PlatformShareDenied or InformationSourceNotFound."""
    source = await _share_resource(session, InformationSource, source_id, is_shared, user)
    if source is None:
        raise InformationSourceNotFound(source_id)
    return cast(InformationSource, source)


@audited(
    "assistant.faq_shared",
    entity_type="faq",
    capture_details=lambda f: {"id": f.id, "is_platform_shared": f.is_platform_shared},
)
async def share_faq(session: AsyncSession, user: User, faq_id: int, is_shared: bool) -> FAQ:
    """Designate an FAQ platform-level shared (FR-020). Raises
    PlatformShareDenied or FAQNotFound."""
    faq = await _share_resource(session, FAQ, faq_id, is_shared, user)
    if faq is None:
        raise FAQNotFound(faq_id)
    return cast(FAQ, faq)


# ────────────────────────────────────────────────────────────────────────
# Administrator Interaction Log View (FR-021, SR-007, T-021)
# ────────────────────────────────────────────────────────────────────────


async def list_interaction_logs_admin(
    session: AsyncSession, user: User
) -> list[InteractionLogRead]:
    """Return interaction logs for the administrator view (FR-021).

    A genuine Platform Administrator (`user.is_superuser`) sees logs across
    EVERY organization; an Organization Administrator sees only the current
    org's logs (the ordinary TenantScoped-filtered query). Read-only — no
    mutation path exists on this or any interaction-log route (SR-007).
    """
    if user.is_superuser:
        saved_org_id = get_current_org_id()
        set_current_org_id(None)
        try:
            result = await session.execute(
                select(InteractionLog).order_by(InteractionLog.created_at.desc())
            )
            entries = result.scalars().all()
        finally:
            set_current_org_id(saved_org_id)
    else:
        result = await session.execute(
            select(InteractionLog).order_by(InteractionLog.created_at.desc())
        )
        entries = result.scalars().all()
    return [_to_interaction_log_read(e) for e in entries]


# ────────────────────────────────────────────────────────────────────────
# No-Execute Invariant for Connected Source Content (SR-005, T-005x)
# ────────────────────────────────────────────────────────────────────────
#
# `read_source_content_readonly` is the ONLY place in this slot that reads
# raw connected-source bytes (T-008's FAQ-generation-from-source flow).
# Content is ALWAYS returned as an inert plain-text string, regardless of
# what it contains — no subprocess/exec/eval/os.system/os.popen/shell=True
# appears anywhere in this module (see tests/test_v0_3.py's dedicated static
# scan, which is written so it can genuinely fail).

# Patterns suggesting connected-source content is attempting to trigger
# execution via injection (SR-005's own acceptance-criteria vectors: shell
# commands, eval expressions, script tags, prompt injections). Detection
# only — matching content is still returned as plain text; a match instead
# feeds FR-022's alert+audit trail (see _record_no_execute_violation).
_NO_EXECUTE_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bsubprocess\.\w+\s*\("),
    re.compile(r"\bos\.popen\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"<script[\s>]", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r";\s*(DROP|DELETE)\s+", re.IGNORECASE),
    re.compile(r"\bignore\s+(all\s+|any\s+)?(previous|prior)\s+instructions\b", re.IGNORECASE),
]


def _detect_no_execute_violation(text: str) -> str | None:
    """SR-005: detect (never execute) content resembling an
    execution/injection attempt. Returns the matched pattern's source, or
    None. `read_source_content_readonly`'s own return value is NEVER
    altered by this — detection only feeds the FR-022 alert path."""
    for pattern in _NO_EXECUTE_INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def _read_folder_text_readonly(folder_path: str, max_bytes: int) -> str:
    """Read up to `max_bytes` of plain text from a local folder's files
    (local_code_repo / document_folder), never executing anything found.
    Only `Path`/`os.access` + `Path.read_text` are used — no subprocess,
    exec, or eval. Files that fail to decode as text (binary) or otherwise
    raise are skipped, never crashing the caller."""
    root = Path(folder_path)
    if not root.is_dir():
        return ""

    chunks: list[str] = []
    total = 0
    file_count = 0
    for path in sorted(root.rglob("*")):
        if file_count >= 20 or total >= max_bytes:
            break
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        remaining = max_bytes - total
        snippet = text[:remaining]
        chunks.append(f"--- {path.name} ---\n{snippet}")
        total += len(snippet)
        file_count += 1
    return "\n\n".join(chunks)


async def _read_github_text_readonly(github_url: str, access_token: str | None) -> str:
    """Read a GitHub/online repo's README via one read-only HTTP GET
    (github_online_repo) — never clones, executes, or evaluates repository
    content. Network/parse failures return "" (never raised)."""
    api_url = _github_api_url(github_url)
    if api_url is None:
        return ""
    headers = {"Accept": "application/vnd.github.raw"}
    if access_token:
        headers["Authorization"] = f"token {access_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{api_url}/readme", headers=headers)
        if resp.status_code == 200:
            return resp.text
    except httpx.HTTPError:
        pass
    return ""


async def _read_mcp_text_readonly(
    mcp_server_address: str, credentials: dict[str, Any] | None
) -> str:
    """Read a bounded, honest text summary of an MCP server's advertised
    tools (mcp_server) — this chassis ships no vector store / content-
    indexing pipeline, so, mirroring `_build_grounding_context`'s own
    established precedent, "content" here is the tool catalog rather than
    retrieved tool output. Never invokes a tool."""
    credential = None
    if credentials:
        credential = credentials.get("api_key") or credentials.get("password")
    try:
        from app.mcp.client import MCPClientError  # noqa: PLC0415
        from app.mcp.client import list_tools as _mcp_list_tools  # noqa: PLC0415

        tools = await _mcp_list_tools(
            url=mcp_server_address, credential=credential, timeout_seconds=10.0
        )
        return "\n".join(f"{t.name}: {t.description}" for t in tools)
    except MCPClientError:
        return ""
    except Exception:  # pragma: no cover - defensive: never let this crash a caller
        log.error("assistant.mcp_read_unexpected_error", address=mcp_server_address)
        return ""


async def read_source_content_readonly(source: InformationSource, max_bytes: int) -> str:
    """SR-005: read a connected information source's content as PLAIN TEXT
    ONLY, regardless of source type or content. Never executes, interprets,
    or evaluates anything — dispatches to a per-type read-only reader."""
    if source.source_type in (
        InformationSourceType.LOCAL_CODE_REPO.value,
        InformationSourceType.DOCUMENT_FOLDER.value,
    ):
        return _read_folder_text_readonly(source.folder_path or "", max_bytes)
    if source.source_type == InformationSourceType.GITHUB_ONLINE_REPO.value:
        access_token: str | None = None
        if source.credentials_encrypted:
            try:
                creds = CredentialEncryptionService.decrypt(source.credentials_encrypted)
                access_token = creds.get("access_token")
            except Exception:  # pragma: no cover - defensive
                access_token = None
        return await _read_github_text_readonly(source.github_url or "", access_token)
    # mcp_server
    credentials: dict[str, Any] | None = None
    if source.credentials_encrypted:
        try:
            credentials = CredentialEncryptionService.decrypt(source.credentials_encrypted)
        except Exception:  # pragma: no cover - defensive
            credentials = None
    return await _read_mcp_text_readonly(source.mcp_server_address or "", credentials)


# ────────────────────────────────────────────────────────────────────────
# No-Execute Violation Alerting and Audit (FR-022)
# ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NoExecuteViolationRecord:
    """Return value of `_record_no_execute_violation`, shaped so the
    @audited decorator can pick up `entity_id` (via `.id`) without this
    slot ever writing an AuditLog row by hand (CONSTITUTION: "Do not write
    audit rows by hand")."""

    id: int
    violation_kind: str
    source_type: str


@audited(
    "assistant.no_execute_violation_detected",
    entity_type="information_source",
    capture_details=lambda r: {"violation_kind": r.violation_kind, "source_type": r.source_type},
)
async def _record_no_execute_violation(
    session: AsyncSession, org_id: int, source: InformationSource, violation_kind: str
) -> NoExecuteViolationRecord:
    """FR-022: fan out a persistent, non-expiring in-app alert to EVERY
    Platform Administrator (is_superuser accounts — distinct from FR-008's
    org-scoped admin/content_manager alert recipients) and write the
    append-only audit row (via @audited above). One failed notification
    never blocks the others (mirrors dispatch_unanswerable_alert's own
    defensive pattern)."""
    from app.notifications.service import notify  # noqa: PLC0415

    result = await session.execute(select(User).where(User.is_superuser.is_(True)))
    platform_admins = result.scalars().all()
    for admin in platform_admins:
        try:
            await notify(
                session=session,
                user_id=admin.id,
                title="Security: no-execute rule violation detected",
                body=(
                    f"Connected source '{source.name}' contained content that would "
                    f"trigger execution. No code was executed."
                ),
                level="error",
                org_id=org_id,
            )
        except Exception:  # pragma: no cover - notification failure must not break the flow
            log.error("assistant.no_execute_alert_failed", admin_id=admin.id)

    return NoExecuteViolationRecord(
        id=source.id, violation_kind=violation_kind, source_type=source.source_type
    )


# ────────────────────────────────────────────────────────────────────────
# Automated FAQ Generation from Interaction Logs (FR-017, NFR-001, T-007)
# ────────────────────────────────────────────────────────────────────────


async def _faq_generation_context(session: AsyncSession, org_id: int) -> str:
    """Build the "available categories/sources" context block shared by
    both T-007's and T-008's LLM prompts, so the model can recommend real
    ids the org actually has configured."""
    qcats = await list_question_categories(session)
    scats = await _select_own_org_or_shared(session, InformationSourceCategory, org_id)
    srcs = await _select_own_org_or_shared(session, InformationSource, org_id)
    lines = [
        "Available question categories (id:name): "
        + ", ".join(f"{c.id}:{c.name}" for c in qcats),
        "Available source categories (id:name): "
        + ", ".join(f"{c.id}:{c.name}" for c in scats),
        "Available sources (id:name): " + ", ".join(f"{s.id}:{s.name}" for s in srcs),
    ]
    return "\n".join(lines)


def _parse_faq_candidate_json(raw: list[Any]) -> list[dict[str, Any]]:
    """Parse the LLM's `{"candidates": [...]}` array into a normalized list
    of dicts. Any malformed entry is skipped, never raised."""
    candidates: list[dict[str, Any]] = []
    for c in raw:
        if not isinstance(c, dict) or not c.get("question"):
            continue
        candidates.append(
            {
                "question": str(c.get("question", "")),
                "answer": str(c.get("answer", "")),
                "question_category_ids": [
                    int(i) for i in c.get("question_category_ids", []) if isinstance(i, int | str)
                ],
                "source_category_ids": [
                    int(i) for i in c.get("source_category_ids", []) if isinstance(i, int | str)
                ],
                "source_ids": [
                    int(i) for i in c.get("source_ids", []) if isinstance(i, int | str)
                ],
            }
        )
    return candidates


async def _generate_faq_candidates_from_logs(
    session: AsyncSession, org_id: int, logs: list[InteractionLog]
) -> list[dict[str, Any]]:
    """FR-017: cluster/summarise `logs` into FAQ candidates via the chassis
    LLM. SR-006: each log's question/response text is sanitized first — a
    log whose content is blocked (source code detected) is EXCLUDED from
    the batch rather than aborting the whole generation. Best-effort: any
    LLM failure (no key, parse error) returns an empty candidate list rather
    than raising (mirrors _call_llm's own graceful-degradation precedent).
    """
    if not logs:
        return []

    lines: list[str] = []
    for entry in logs:
        q_result = LLMPayloadSanitizer.sanitize(entry.question_text)
        if isinstance(q_result, SanitizationBlocked):
            continue
        lines.append(f"Q: {q_result.text}")
        if entry.response_text:
            r_result = LLMPayloadSanitizer.sanitize(entry.response_text)
            if isinstance(r_result, SanitizedPayload):
                lines.append(f"A: {r_result.text}")
    if not lines:
        return []

    context = await _faq_generation_context(session, org_id)
    system_prompt = (
        "You are reviewing a set of user questions and answers from an accessibility "
        "assistant's interaction logs. Cluster semantically similar questions and propose "
        "FAQ candidates. Recommend ids ONLY from the lists provided — never invent an id. "
        f"{context}\n\n"
        "Respond as JSON: {\"candidates\": [{\"question\": \"...\", \"answer\": \"...\", "
        '"question_category_ids": [...], "source_category_ids": [...], "source_ids": [...]}]}. '
        "Do not include any names, emails, or other personal information in your response."
    )

    try:
        from app.llm.service import LLMKeyUnavailable, complete  # noqa: PLC0415

        result = await complete(
            session=session,
            provider="openai",
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(lines)},
            ],
            org_id=org_id,
        )
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return _parse_faq_candidate_json(parsed.get("candidates", []))
    except LLMKeyUnavailable:
        log.warning("assistant.faq_generation_no_llm_key", org_id=org_id)
        return []
    except Exception as exc:  # noqa: BLE001 - best-effort generation, never crash the endpoint
        log.error("assistant.faq_generation_failed", error=str(exc), org_id=org_id)
        return []


@audited(
    "assistant.faq_generation_session_created",
    entity_type="faq_generation_session",
    capture_details=lambda pair: {
        "session_id": pair[0].id,
        "candidate_count": len(pair[1]),
    },
)
async def create_faq_generation_session_from_logs(
    session: AsyncSession, user: User, org_id: int, max_logs: int
) -> tuple[FAQGenerationSession, list[FAQGenerationCandidate]]:
    """Initiate LLM review of interaction logs and stage the resulting
    candidates in `pending_review` status (FR-017). No FAQ row is written
    here — see confirm_faq_generation_session (NFR-001's approval gate)."""
    result = await session.execute(
        select(InteractionLog).order_by(InteractionLog.created_at.desc()).limit(max_logs)
    )
    logs = list(result.scalars().all())

    raw_candidates = await _generate_faq_candidates_from_logs(session, org_id, logs)

    gen_session = FAQGenerationSession(
        source_type="interaction_logs",
        status=FAQGenerationStatus.PENDING_REVIEW.value,
        created_by_user_id=user.id,
    )
    session.add(gen_session)
    await session.flush()

    candidates: list[FAQGenerationCandidate] = []
    for c in raw_candidates:
        candidate = FAQGenerationCandidate(
            session_id=gen_session.id,
            question=c["question"],
            answer=c["answer"],
            recommended_question_category_ids_json=json.dumps(c["question_category_ids"]),
            recommended_source_category_ids_json=json.dumps(c["source_category_ids"]),
            recommended_source_ids_json=json.dumps(c["source_ids"]),
            status=FAQGenerationCandidateStatus.PENDING_REVIEW.value,
        )
        session.add(candidate)
        candidates.append(candidate)
    await session.flush()
    return gen_session, candidates


async def _get_faq_generation_session(
    session: AsyncSession, session_id: int
) -> FAQGenerationSession:
    result = await session.execute(
        select(FAQGenerationSession).where(FAQGenerationSession.id == session_id)
    )
    gen_session = result.scalar_one_or_none()
    if gen_session is None:
        raise FAQGenerationSessionNotFound(session_id)
    return gen_session


def _to_faq_generation_candidate_read(
    candidate: FAQGenerationCandidate,
) -> FAQGenerationCandidateRead:
    return FAQGenerationCandidateRead(
        id=candidate.id,
        question=candidate.question,
        answer=candidate.answer,
        question_category_ids=json.loads(candidate.recommended_question_category_ids_json),
        source_category_ids=json.loads(candidate.recommended_source_category_ids_json),
        source_ids=json.loads(candidate.recommended_source_ids_json),
        status=candidate.status,
    )


async def list_faq_generation_candidates(
    session: AsyncSession, session_id: int
) -> list[FAQGenerationCandidateRead]:
    """Return the staged candidates for a session, for human review
    (FR-017). Raises FAQGenerationSessionNotFound (TenantScoped -> a
    cross-org session id naturally 404s)."""
    await _get_faq_generation_session(session, session_id)
    result = await session.execute(
        select(FAQGenerationCandidate)
        .where(FAQGenerationCandidate.session_id == session_id)
        .order_by(FAQGenerationCandidate.id)
    )
    return [_to_faq_generation_candidate_read(c) for c in result.scalars().all()]


@audited(
    "assistant.faq_generation_confirmed",
    entity_type="faq_generation_session",
    capture_details=lambda triple: {
        "session_id": triple[0],
        "created_faq_ids": triple[1],
        "discarded_candidate_ids": triple[2],
    },
)
async def confirm_faq_generation_session(
    session: AsyncSession,
    user: User,
    session_id: int,
    approved: list[FAQGenerationApprovedCandidate],
) -> tuple[int, list[int], list[int]]:
    """Persist ONLY the approved candidates to `aa_faqs` (FR-017, NFR-001).

    Atomic: every approved candidate's category/source ids are validated
    (via the existing _resolve_ids_in_org) BEFORE any FAQ row is inserted —
    either all approved candidates are created, or none are (a validation
    failure raises before any `session.add(FAQ(...))` call). Every
    candidate belonging to this session is then marked 'approved' or
    'rejected' and the session is closed ('confirmed') — an empty
    `approved` list is a valid, explicit "save nothing" confirmation
    (NFR-001: a missing confirmation is always treated as rejection).
    """
    gen_session = await _get_faq_generation_session(session, session_id)

    for item in approved:
        await _resolve_ids_in_org(
            session, QuestionCategory, item.question_category_ids, "question category"
        )
        await _resolve_ids_in_org(
            session, InformationSourceCategory, item.source_category_ids, "source category"
        )
        await _resolve_ids_in_org(session, InformationSource, item.source_ids, "source")

    created_faq_ids: list[int] = []
    for item in approved:
        faq = FAQ(
            question_category_id=item.question_category_ids[0],
            question=item.question,
            answer=item.answer,
            created_by_user_id=user.id,
        )
        session.add(faq)
        await session.flush()
        session.add_all(
            FAQQuestionCategory(faq_id=faq.id, question_category_id=qc_id)
            for qc_id in item.question_category_ids
        )
        session.add_all(
            FAQSourceCategory(faq_id=faq.id, source_category_id=sc_id)
            for sc_id in item.source_category_ids
        )
        session.add_all(
            FAQSource(faq_id=faq.id, source_id=s_id) for s_id in item.source_ids
        )
        created_faq_ids.append(faq.id)

    approved_candidate_ids = {c.candidate_id for c in approved}
    cand_result = await session.execute(
        select(FAQGenerationCandidate).where(FAQGenerationCandidate.session_id == session_id)
    )
    discarded_candidate_ids: list[int] = []
    for candidate in cand_result.scalars().all():
        if candidate.id in approved_candidate_ids:
            candidate.status = FAQGenerationCandidateStatus.APPROVED.value
        else:
            candidate.status = FAQGenerationCandidateStatus.REJECTED.value
            discarded_candidate_ids.append(candidate.id)

    gen_session.status = FAQGenerationStatus.CONFIRMED.value
    await session.flush()
    return session_id, created_faq_ids, discarded_candidate_ids


# ────────────────────────────────────────────────────────────────────────
# Automated FAQ Generation from Information Source (FR-018, NFR-001, T-008)
# ────────────────────────────────────────────────────────────────────────


async def generate_faq_candidates_from_source(
    session: AsyncSession, user: User, org_id: int, source_id: int, max_content_bytes: int
) -> FAQGenerationFromSourceResponse:
    """Generate in-memory FAQ candidates from a connected information
    source's content (FR-018). No staging table — see FAQGenerationSession's
    own docstring for why.

    SR-005: content is always read via read_source_content_readonly (never
    executed). A detected no-execute/injection pattern fires FR-022's alert
    + audit trail AND blocks the generation (the content must not reach the
    LLM either way). SR-006: independently of that, the sanitizer's own
    source-code detector also blocks generation — this is the documented
    resolution of FR-018 (generate from ANY source, including a
    Local Code Repo) vs. SR-006 (no source code in an FAQ-generation LLM
    payload): security wins, and a Local Code Repo source's raw code is
    legitimately never sent to the LLM.
    """
    source = await get_information_source(session, source_id)
    content = await read_source_content_readonly(source, max_content_bytes)

    violation_kind = _detect_no_execute_violation(content)
    if violation_kind is not None:
        await _record_no_execute_violation(session, org_id, source, violation_kind)
        return FAQGenerationFromSourceResponse(
            source_id=source_id,
            candidates=[],
            blocked=True,
            blocked_reason="source content matched a no-execute/injection pattern",
        )

    if not content.strip():
        return FAQGenerationFromSourceResponse(source_id=source_id, candidates=[])

    sanitized = LLMPayloadSanitizer.sanitize(content)
    if isinstance(sanitized, SanitizationBlocked):
        return FAQGenerationFromSourceResponse(
            source_id=source_id,
            candidates=[],
            blocked=True,
            blocked_reason="source content contains source code and was not sent to the LLM",
        )

    context = await _faq_generation_context(session, org_id)
    system_prompt = (
        f"You are reviewing the content of a connected information source ('{source.name}') "
        "for an accessibility assistant. Generate FAQ candidates that a user could plausibly "
        "ask about this content. Recommend ids ONLY from the lists provided — never invent "
        f"an id. {context}\n\n"
        "Respond as JSON: {\"candidates\": [{\"question\": \"...\", \"answer\": \"...\", "
        '"question_category_ids": [...], "source_category_ids": [...], "source_ids": [...]}]}.'
    )

    try:
        from app.llm.service import LLMKeyUnavailable, complete  # noqa: PLC0415

        result = await complete(
            session=session,
            provider="openai",
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": sanitized.text},
            ],
            org_id=org_id,
        )
        content_json = result["choices"][0]["message"]["content"]
        parsed = json.loads(content_json)
        raw_candidates = _parse_faq_candidate_json(parsed.get("candidates", []))
    except LLMKeyUnavailable:
        log.warning("assistant.faq_generation_no_llm_key", org_id=org_id, source_id=source_id)
        raw_candidates = []
    except Exception as exc:  # noqa: BLE001 - best-effort generation, never crash the endpoint
        log.error("assistant.faq_generation_failed", error=str(exc), source_id=source_id)
        raw_candidates = []

    return FAQGenerationFromSourceResponse(
        source_id=source_id,
        candidates=[
            FAQGenerationCandidateOut(
                question=c["question"],
                answer=c["answer"],
                question_category_ids=c["question_category_ids"],
                source_category_ids=c["source_category_ids"],
                source_ids=c["source_ids"],
            )
            for c in raw_candidates
        ],
    )


async def confirm_faq_generation_from_source(
    session: AsyncSession, user: User, candidates: list[FAQCreate]
) -> list[int]:
    """Persist the (client-approved, possibly edited) candidates from
    FR-018's in-memory generation flow (NFR-001's approval gate). Atomic:
    every candidate is validated before any is persisted. Reuses the
    existing, already-`@audited` create_faq() per item — one audit row per
    FAQ created is the right granularity here (no outer wrapper), since
    unlike T-007 there is no session object to name in a single "confirmed"
    audit event.
    """
    for item in candidates:
        await _resolve_ids_in_org(
            session, QuestionCategory, item.question_category_ids, "question category"
        )
        await _resolve_ids_in_org(
            session, InformationSourceCategory, item.source_category_ids, "source category"
        )
        await _resolve_ids_in_org(session, InformationSource, item.source_ids, "source")

    created_ids: list[int] = []
    for item in candidates:
        faq = await create_faq(session, user, item)
        created_ids.append(faq.id)
    return created_ids
