"""Transactional email via FastAPI-Mail.

v0.1.0 ships two backends:
  - console (default in dev) — prints messages to stdout via structlog
  - smtp — uses fastapi-mail to talk to a real SMTP server in prod

Switch via env var: MAIL_BACKEND=smtp.

Public API:
    from app.mail import send_email
    await send_email(to=["alice@example.com"], subject="Hi", body="Hello")
"""

from app.mail.service import send_email

__all__ = ["send_email"]
