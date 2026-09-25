"""Greeting slot — the chassis-program reference/demo app.

Adapted from `Chassis App/greeting-service-*.md` (The SD-Agile Project's
teaching-exemplar Build Package) per `chassis-program-DESIGN.md` §3, for
the `python-fastapi-mt-fisma-moderate-llm` pilot package. Two adaptations
beyond the draft: (1) FR-004's MFA gate is real, wired to the chassis's
actual TOTP MFA (app/auth/mfa.py); (2) an opt-in LLM-backed translation
path is added alongside the draft's static TranslationProvider, so the
LLM-vs-non-LLM chassis variants are visibly demonstrable side by side.

Registers slot permissions at import time, mirroring app/slots/example.
"""

from app.rbac.permissions import register

GREETINGS_WRITE = "greetings:write"
GREETINGS_HISTORY_READ = "greetings:history:read"

register(GREETINGS_WRITE, "Request a greeting")
register(GREETINGS_HISTORY_READ, "Read greeting history for the organization (admin + MFA)")
