"""K.8 — Standard error messages (chassis v0.6.3).

Verifies the canonical chassis error messages stay consistent so
slot authors, support docs, and end-user training can depend on the
strings being stable across releases.

Why centralized vs. inlined:
  - One source of truth — string drift between routes is a real bug
    in the legacy v0.5.x chassis (we had at least 3 different 401
    phrasings depending on which deps function fired).
  - Tone gate — every entry is reviewed by the policy team for
    plain-English voice, length, accessibility.
  - i18n stepping stone — pivoting to gettext later only requires
    editing this module, not every raise site.
"""

from __future__ import annotations

import pytest

from app.error_messages import (
    ERR_BAD_REQUEST,
    ERR_CONFLICT,
    ERR_FORBIDDEN,
    ERR_INTERNAL,
    ERR_NOT_FOUND,
    ERR_RATE_LIMITED,
    ERR_UNAUTHENTICATED,
    ERR_UNAVAILABLE,
    ERR_VALIDATION,
    STANDARD_MESSAGES,
    message_for_status,
)

# ─── Table integrity ──────────────────────────────────────────────────


def test_table_covers_all_common_status_codes() -> None:
    """The canonical table MUST cover every HTTP status the chassis
    routinely returns. If a new condition is added (e.g. 451 legal
    reasons in a future release) the test reminds us to populate it.
    """
    required = {400, 401, 403, 404, 409, 422, 429, 500, 503}
    missing = required - set(STANDARD_MESSAGES.keys())
    assert not missing, f"canonical message table missing: {missing}"


def test_messages_are_short() -> None:
    """Per the style guide, each canonical message must be ≤ 80 chars.
    Long messages break responsive layouts on mobile and screen readers.
    """
    too_long = {
        code: msg
        for code, msg in STANDARD_MESSAGES.items()
        if len(msg) > 80
    }
    assert not too_long, (
        f"canonical messages exceed 80-char limit: "
        f"{ {c: len(m) for c, m in too_long.items()} }"
    )


def test_messages_end_with_period() -> None:
    """Consistent terminating punctuation matters for screen readers
    that pause at sentence ends.
    """
    no_period = {
        code: msg
        for code, msg in STANDARD_MESSAGES.items()
        if not msg.endswith(".")
    }
    assert not no_period, (
        f"canonical messages must end with a period: {no_period}"
    )


def test_messages_avoid_user_blame() -> None:
    """Style guide forbids second-person accusatory voice. Permission
    rejection messages are allowed an exception (the user IS the agent
    being told no), but generic 4xx errors should use first-person
    plural ("We couldn't…").
    """
    # The 403 message intentionally uses "you don't have permission" —
    # that's a statement of fact, not blame for an error.
    allowed_second_person = {403}
    blamed = []
    for code, msg in STANDARD_MESSAGES.items():
        if code in allowed_second_person:
            continue
        # "You did/you've/your" patterns are the blame red-flag.
        for blame_token in ("You did", "You've", "Your fault", "You broke"):
            if blame_token in msg:
                blamed.append((code, msg))
                break
    assert not blamed, (
        f"canonical messages use blaming voice: {blamed}"
    )


# ─── Convenience aliases match the table ───────────────────────────────


@pytest.mark.parametrize(
    "alias,code",
    [
        (ERR_BAD_REQUEST, 400),
        (ERR_UNAUTHENTICATED, 401),
        (ERR_FORBIDDEN, 403),
        (ERR_NOT_FOUND, 404),
        (ERR_CONFLICT, 409),
        (ERR_VALIDATION, 422),
        (ERR_RATE_LIMITED, 429),
        (ERR_INTERNAL, 500),
        (ERR_UNAVAILABLE, 503),
    ],
)
def test_convenience_aliases_match_table(alias: str, code: int) -> None:
    """Slot code that imports the convenience aliases (e.g. ERR_FORBIDDEN)
    must get the same string as message_for_status(403). Drift between
    the table and the aliases would silently regress consistency.
    """
    assert alias == STANDARD_MESSAGES[code]


# ─── message_for_status fallbacks ──────────────────────────────────────


def test_message_for_status_known_code() -> None:
    assert message_for_status(404) == STANDARD_MESSAGES[404]


def test_message_for_status_uses_explicit_fallback() -> None:
    """An unknown code with an explicit fallback returns the fallback."""
    assert (
        message_for_status(418, fallback="I'm a teapot.")
        == "I'm a teapot."
    )


def test_message_for_status_implicit_4xx_fallback() -> None:
    """An unknown 4xx code with no fallback falls back to the generic
    400 message (rather than crashing or returning empty).
    """
    assert message_for_status(451) == STANDARD_MESSAGES[400]


def test_message_for_status_implicit_5xx_fallback() -> None:
    """An unknown 5xx code with no fallback falls back to the generic
    500 message.
    """
    assert message_for_status(599) == STANDARD_MESSAGES[500]
