"""Email sending — console backend for dev, fastapi-mail for prod.

The console backend logs the email content via structlog. The SMTP backend
uses fastapi-mail's FastMail.send_message under the hood. The chassis
prefers the console backend for tests so we never accidentally send real
mail during a CI run.
"""

from __future__ import annotations

from typing import Any

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import SecretStr, TypeAdapter
from pydantic.networks import NameEmail

from app.config import Settings, get_settings
from app.logging import get_logger

log = get_logger("mail")

_fastmail: FastMail | None = None
_recipients_adapter = TypeAdapter(list[NameEmail])


def _get_fastmail(settings: Settings) -> FastMail:
    """Lazy-init the fastapi-mail singleton for the SMTP backend."""
    global _fastmail
    if _fastmail is None:
        config = ConnectionConfig(
            MAIL_USERNAME=settings.mail_username,
            MAIL_PASSWORD=SecretStr(settings.mail_password),
            MAIL_FROM=settings.mail_from,
            MAIL_PORT=settings.mail_port,
            MAIL_SERVER=settings.mail_server,
            MAIL_STARTTLS=settings.mail_starttls,
            MAIL_SSL_TLS=settings.mail_ssl_tls,
            USE_CREDENTIALS=bool(settings.mail_username),
        )
        _fastmail = FastMail(config)
    return _fastmail


async def send_email(
    to: list[str],
    subject: str,
    body: str,
    *,
    html: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Send (or log) an email. Returns a dict with delivery metadata.

    For the `console` backend, no network call happens — the message is
    structured-logged via structlog. For the `smtp` backend, fastapi-mail
    actually delivers. Returns include the chosen backend + recipient list.
    """
    s = settings or get_settings()

    if s.mail_backend == "console":
        log.info(
            "mail.console_delivery",
            to=to,
            subject=subject,
            body_preview=body[:200],
            backend="console",
        )
        return {"backend": "console", "to": to, "subject": subject, "delivered": True}

    message = MessageSchema(
        subject=subject,
        # fastapi-mail's newer MessageSchema types recipients as
        # list[NameEmail] (pydantic), not list[str] -- explicit conversion
        # keeps this both mypy-correct and behaviorally identical to
        # passing bare address strings (pydantic parses "user@x.com" into
        # NameEmail(name="user", email="user@x.com") either way).
        recipients=_recipients_adapter.validate_python(to),
        body=body,
        subtype=MessageType.html if html else MessageType.plain,
    )
    fm = _get_fastmail(s)
    await fm.send_message(message)
    log.info("mail.smtp_delivery", to=to, subject=subject)
    return {"backend": "smtp", "to": to, "subject": subject, "delivered": True}
