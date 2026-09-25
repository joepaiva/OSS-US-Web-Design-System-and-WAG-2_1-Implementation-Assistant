"""Canonical user-facing error messages — K.8 (chassis v0.6.3).

Single source of truth for the strings that the chassis returns to
end-users when something goes wrong. Slot code MAY override any of these
on a per-route basis by raising HTTPException with a custom `detail`,
but the chassis-side defaults below are the recommended baseline for
every common error condition.

Why centralized:
  - Consistency: every chassis-deployed app says the same thing for the
    same condition, so docs / support / training don't drift.
  - Tone: messages here are reviewed for clarity + non-blaming voice.
    No "you did something wrong" — always "we couldn't process this."
  - Accessibility: kept short, plain-English, screen-reader friendly.
  - i18n-ready: future versions can pivot to gettext keys without
    touching every raise site.

Used by:
  - app/error_handlers.py (500 / generic exception)
  - app/deps.py (401, 403, 400 raise sites)
  - slot code that wants the chassis-canonical phrasing
    (`from app.error_messages import STANDARD_MESSAGES`)

Override mechanism (per RESPONSIVE-DESIGN.md §"How to override" pattern):
  Slot authors who need a custom message for a specific status code on
  a specific route MAY raise HTTPException(detail="custom...") directly.
  Override SHOULD be annotated with `# CHASSIS-OVERRIDE: error-messages`
  and a reference to the FR-ID for traceability.
"""

from __future__ import annotations

from typing import Final

# Canonical user-facing strings, keyed by HTTP status code.
#
# Style guide for adding new entries:
#   - First-person plural voice ("We couldn't…"), NOT second-person
#     accusatory ("You did X wrong").
#   - One sentence, ≤ 80 characters. Screen readers prefer concise.
#   - No technical jargon ("token", "JWT", "401") — those belong in the
#     internal log line, not the user-facing string.
#   - Always end with a period.
STANDARD_MESSAGES: Final[dict[int, str]] = {
    400: "We couldn't process this request. Please check the form and try again.",
    401: "Please sign in to continue.",
    403: "You don't have permission to perform this action.",
    404: "The page you're looking for doesn't exist.",
    409: "This change conflicts with the current state. Please refresh and try again.",
    410: "This resource is no longer available.",
    413: "The file or request is too large.",
    415: "We don't support that file or content type.",
    422: "Some of the information you provided is invalid.",
    423: "This resource is currently locked by another action.",
    429: "Too many requests. Please slow down and try again in a moment.",
    500: "Something went wrong on our side. Please try again or contact support.",
    501: "This feature isn't available in this version of the application.",
    502: "We couldn't reach a service we depend on. Please try again shortly.",
    503: "The service is temporarily unavailable. Please try again in a few minutes.",
    504: "A service we depend on took too long to respond. Please try again.",
}


def message_for_status(status_code: int, fallback: str | None = None) -> str:
    """Return the canonical chassis message for an HTTP status code.

    If `status_code` is not in the table, returns `fallback` (or a
    generic message if `fallback` is None). Slot code MAY call this
    directly to get the chassis-canonical phrasing for a custom raise:

        from fastapi import HTTPException
        from app.error_messages import message_for_status
        raise HTTPException(403, detail=message_for_status(403))
    """
    if status_code in STANDARD_MESSAGES:
        return STANDARD_MESSAGES[status_code]
    if fallback is not None:
        return fallback
    if 400 <= status_code < 500:
        return STANDARD_MESSAGES[400]
    if status_code >= 500:
        return STANDARD_MESSAGES[500]
    return "Unexpected response."


# Convenience aliases for the most-common raises so slot code can do
#   raise HTTPException(403, detail=ERR_FORBIDDEN)
# without importing the function.
ERR_BAD_REQUEST: Final[str] = STANDARD_MESSAGES[400]
ERR_UNAUTHENTICATED: Final[str] = STANDARD_MESSAGES[401]
ERR_FORBIDDEN: Final[str] = STANDARD_MESSAGES[403]
ERR_NOT_FOUND: Final[str] = STANDARD_MESSAGES[404]
ERR_CONFLICT: Final[str] = STANDARD_MESSAGES[409]
ERR_VALIDATION: Final[str] = STANDARD_MESSAGES[422]
ERR_RATE_LIMITED: Final[str] = STANDARD_MESSAGES[429]
ERR_INTERNAL: Final[str] = STANDARD_MESSAGES[500]
ERR_UNAVAILABLE: Final[str] = STANDARD_MESSAGES[503]
