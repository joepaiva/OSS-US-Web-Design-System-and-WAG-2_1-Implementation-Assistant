"""AC-8 system use notification banner tests (chassis v0.6).

NIST 800-53 AC-8 + FedRAMP Moderate require a system use notification
displayed before granting access. The chassis ships an optional banner
controllable via Settings.system_use_notification; an empty value (the
default) suppresses the banner so non-government applications aren't
required to display one.

Tests:
  - Empty notification → no banner div in login page
  - Non-empty notification → banner div rendered with the text
  - Newlines in notification preserved via CSS white-space: pre-line
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


def _make_app_with_banner(monkeypatch: Any, banner: str) -> Any:
    """Build a chassis app whose Settings has the given banner text."""
    settings = Settings(
        database_url="postgresql+psycopg://chassis:chassis@localhost:5532/chassis",
        secret_key="test-secret-key-32-bytes-of-random-padding",
        env="test",
        debug=False,
        cors_origins="",
        system_use_notification=banner,
    )

    # Patch the get_settings call inside frontend so the login page sees
    # our banner text.
    from app import frontend

    monkeypatch.setattr(frontend, "get_settings", lambda: settings)

    return create_app(settings)


@pytest_asyncio.fixture
async def app_no_banner(monkeypatch: Any) -> AsyncIterator[AsyncClient]:
    app = _make_app_with_banner(monkeypatch, "")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:  # type: ignore[arg-type]
        yield c


@pytest_asyncio.fixture
async def app_with_banner(monkeypatch: Any) -> AsyncIterator[AsyncClient]:
    text = "WARNING: This is a U.S. Government system. Unauthorized use is prohibited."
    app = _make_app_with_banner(monkeypatch, text)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:  # type: ignore[arg-type]
        yield c


@pytest.mark.asyncio
async def test_login_page_omits_banner_when_setting_empty(
    app_no_banner: AsyncClient,
) -> None:
    resp = await app_no_banner.get("/auth/login")
    assert resp.status_code == 200
    assert "System Use Notification" not in resp.text
    assert 'role="alert"' not in resp.text or "Sign in" in resp.text


@pytest.mark.asyncio
async def test_login_page_renders_banner_when_setting_non_empty(
    app_with_banner: AsyncClient,
) -> None:
    resp = await app_with_banner.get("/auth/login")
    assert resp.status_code == 200
    assert "System Use Notification" in resp.text
    assert "WARNING: This is a U.S. Government system." in resp.text
    # Banner must be a proper ARIA alert for screen readers.
    assert 'role="alert"' in resp.text


@pytest.mark.asyncio
async def test_banner_preserves_multi_line_content(monkeypatch: Any) -> None:
    """Operators commonly set multi-line banners via \\n in env vars.
    Verify whitespace: pre-line CSS is in the template so newlines render."""
    multi = "Line 1\nLine 2\nLine 3"
    app = _make_app_with_banner(monkeypatch, multi)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:  # type: ignore[arg-type]
        resp = await c.get("/auth/login")
    assert resp.status_code == 200
    # All three lines must appear in body; pre-line preserves \n visually.
    assert "Line 1" in resp.text
    assert "Line 2" in resp.text
    assert "Line 3" in resp.text
    assert "white-space: pre-line" in resp.text
