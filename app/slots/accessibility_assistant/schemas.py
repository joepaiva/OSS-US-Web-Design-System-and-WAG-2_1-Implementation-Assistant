# ─────────────────────────────────────────────────────────────────
# Control Annotations — NIST 800-53 (chassis v0.6)
# ─────────────────────────────────────────────────────────────────
# SI-10: Pydantic v2 field validation gates all inputs before ORM writes
# PT-1:  InteractionLog schemas handle PII fields (user_id, question_text)
# ─────────────────────────────────────────────────────────────────
"""Pydantic v2 schemas for the Accessibility Assistant slot.

Scope: v0.1 — FR-001 through FR-006, SR-001 through SR-004.

Schema groups:
  QuestionCategory — Read (browsing, FR-003)
  FAQ              — Read (browsing, FR-003, FR-004)
  Citation         — embedded in FAQ and InteractionLog responses
  AskQuestion      — Create (submit a question, FR-002, FR-004, FR-005)
  RateInteraction  — Update (thumbs up/down, FR-006)
  InteractionLog   — Read (FR-006, SR-003)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ────────────────────────────────────────────────────────────────────────
# Citation (embedded value object)
# ────────────────────────────────────────────────────────────────────────


class Citation(BaseModel):
    """A single source citation with a display name and hyperlink (FR-004)."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    hyperlink: str


# ────────────────────────────────────────────────────────────────────────
# QuestionCategory
# ────────────────────────────────────────────────────────────────────────


class QuestionCategoryRead(BaseModel):
    """QuestionCategory representation in responses (FR-003)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    org_id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


# ────────────────────────────────────────────────────────────────────────
# FAQ
# ────────────────────────────────────────────────────────────────────────


class FAQRead(BaseModel):
    """FAQ representation in responses (FR-003, FR-004).

    `citations` is deserialised from `citations_json` by the service layer
    before returning; this schema receives the parsed list.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    org_id: int
    question_category_id: int | None
    question: str
    answer: str
    reasoning: str
    citations: list[Citation]
    created_at: datetime
    updated_at: datetime


# ────────────────────────────────────────────────────────────────────────
# Ask a question (FR-002, FR-004, FR-005)
# ────────────────────────────────────────────────────────────────────────


class AskQuestionCreate(BaseModel):
    """Body for POST /assistant/ask.

    FR-002: question_text is required and limited to 200 characters.
    FR-005: session_id groups multi-turn conversation turns.
    FR-003: question_category_id is optional (user may browse or free-type).

    SR-002: PII / source-code detection is performed in the service layer
            before any LLM call; this schema only enforces structural
            constraints.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_text: str = Field(
        min_length=1,
        max_length=200,
        description="The user's question. Max 200 characters (FR-002).",
    )
    question_category_id: int | None = Field(
        default=None,
        description="Optional category the user browsed to (FR-003).",
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Caller-supplied session identifier for multi-turn context (FR-005).",
    )


# ────────────────────────────────────────────────────────────────────────
# Rate an interaction (FR-006, FR-004)
# ────────────────────────────────────────────────────────────────────────


class RateInteractionUpdate(BaseModel):
    """Body for PATCH /assistant/interactions/{id}/rate.

    FR-006: rating is nullable — True=thumbs-up, False=thumbs-down.
    Sending null explicitly clears a previously submitted rating.
    """

    model_config = ConfigDict(extra="forbid")

    rating: bool | None = Field(
        description="True = thumbs up, False = thumbs down, null = clear rating."
    )


# ────────────────────────────────────────────────────────────────────────
# InteractionLog (FR-006, SR-003)
# ────────────────────────────────────────────────────────────────────────


class InteractionLogRead(BaseModel):
    """Interaction log record in responses (FR-006, SR-003).

    PT-1: contains PII (user_id, question_text). Access is restricted
    by RBAC in routes.py — end users see only their own records;
    org admins see org-scoped records; platform admins see all.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    org_id: int
    user_id: int
    question_category_id: int | None
    session_id: str | None
    question_text: str
    response_text: str
    reasoning: str
    sources: list[Citation]
    rating: bool | None
    created_at: datetime


# ────────────────────────────────────────────────────────────────────────
# Response to a submitted question (FR-004)
# ────────────────────────────────────────────────────────────────────────


class QuestionResponse(BaseModel):
    """Structured response returned to the end user after asking a question.

    FR-004: must contain (1) expository response text, (2) reasoning,
    (3) citations with hyperlinks, (4) a rating control (represented
    here by the interaction_log_id so the client can submit a rating).
    """

    model_config = ConfigDict(extra="forbid")

    interaction_log_id: int
    response_text: str
    reasoning: str
    citations: list[Citation]
    # Indicates whether any citations were found (FR-004 AC: no broken links)
    has_citations: bool
