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
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.auth.models import User
from app.logging import get_logger
from app.slots.accessibility_assistant.models import (
    FAQ,
    InteractionLog,
    QuestionCategory,
)
from app.slots.accessibility_assistant.schemas import (
    AskQuestionCreate,
    Citation,
    FAQRead,
    InteractionLogRead,
    QuestionCategoryRead,
    QuestionResponse,
    RateInteractionUpdate,
)

log = get_logger("slots.accessibility_assistant")


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
    return [
        FAQRead(
            id=f.id,
            org_id=f.org_id,
            question_category_id=f.question_category_id,
            question=f.question,
            answer=f.answer,
            reasoning=f.reasoning,
            citations=_parse_citations(f.citations_json),
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in faqs
    ]


async def get_faq(session: AsyncSession, faq_id: int) -> FAQRead:
    """Look up one FAQ by id. Raises FAQNotFound."""
    result = await session.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = result.scalar_one_or_none()
    if faq is None:
        raise FAQNotFound(faq_id)
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
    )


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
