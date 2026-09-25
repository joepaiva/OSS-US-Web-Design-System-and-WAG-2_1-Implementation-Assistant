"""Email send tests — console backend only.

We never exercise the SMTP backend in tests (it would try to open a real
TCP connection). The chassis default in dev is `console`, which we test
exhaustively.
"""

from __future__ import annotations

from app.mail import send_email


async def test_send_email_console_backend_returns_delivered() -> None:
    result = await send_email(
        to=["alice@example.com"],
        subject="Hello",
        body="This is a test.",
    )
    assert result["backend"] == "console"
    assert result["delivered"] is True
    assert result["to"] == ["alice@example.com"]
    assert result["subject"] == "Hello"


async def test_send_email_console_backend_handles_multiple_recipients() -> None:
    result = await send_email(
        to=["a@example.com", "b@example.com"],
        subject="Multi",
        body="Hello you both.",
    )
    assert result["delivered"] is True
    assert len(result["to"]) == 2  # type: ignore[arg-type]


async def test_send_email_console_backend_handles_long_body() -> None:
    long_body = "a" * 5000
    result = await send_email(
        to=["x@example.com"],
        subject="Long",
        body=long_body,
    )
    # Console backend only previews the first 200 chars in logs; doesn't truncate the body.
    assert result["delivered"] is True
