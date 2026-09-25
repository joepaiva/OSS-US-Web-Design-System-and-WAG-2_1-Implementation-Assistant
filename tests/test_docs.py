"""In-app documentation page tests (chassis v0.8).

Covers the admin-gated docs index + single-doc view, the unknown-slug 404,
and the safe Markdown renderer (HTML escaping, headings, lists, tables).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.admin.docs_service import get_doc, list_docs, load_doc_html, render_markdown
from tests.conftest import make_org, make_user


@pytest.mark.asyncio
async def test_unauthenticated_redirects_to_login(client: AsyncClient) -> None:
    resp = await client.get("/admin/docs")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_regular_user_is_forbidden(client: AsyncClient) -> None:
    u = await make_user(client, email="reg-docs@example.com")
    resp = await client.get("/admin/docs", headers=u["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_sees_docs_index(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-docs@example.com")
    await make_org(client, u["headers"], name="DocOrg", slug="docorg")
    resp = await client.get("/admin/docs", headers=u["headers"])
    assert resp.status_code == 200
    assert "Documentation" in resp.text
    assert "Security Self-Audit" in resp.text
    assert "User Manual" in resp.text


@pytest.mark.asyncio
async def test_admin_views_security_self_audit(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-sa@example.com")
    await make_org(client, u["headers"], name="SaOrg", slug="saorg")
    resp = await client.get("/admin/docs/security-self-audit", headers=u["headers"])
    assert resp.status_code == 200
    # Rendered Markdown → HTML headings present.
    assert "<h1>" in resp.text
    assert "FISMA Moderate" in resp.text
    # A known control row from the audit table.
    assert "AC-7" in resp.text


@pytest.mark.asyncio
async def test_unknown_doc_slug_returns_404(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-404@example.com")
    await make_org(client, u["headers"], name="NfOrg", slug="nforg")
    resp = await client.get("/admin/docs/../../etc/passwd", headers=u["headers"])
    # The client normalizes `../../` so this never reaches the docs route as a
    # traversal; either way the response is a 404 and no file contents leak.
    assert resp.status_code in (404, 405)
    assert "root:" not in resp.text  # /etc/passwd contents never served


@pytest.mark.asyncio
async def test_unknown_simple_slug_returns_404(client: AsyncClient) -> None:
    u = await make_user(client, email="orgadmin-nope@example.com")
    await make_org(client, u["headers"], name="NopeOrg", slug="nopeorg")
    resp = await client.get("/admin/docs/nonexistent", headers=u["headers"])
    assert resp.status_code == 404
    assert "does not exist" in resp.text


# ─── Registry + loader unit tests ───────────────────────────────────────────


def test_registry_has_four_docs() -> None:
    slugs = {d.slug for d in list_docs()}
    assert slugs == {"how-it-works", "user-manual", "security-self-audit", "readme"}


def test_load_doc_html_renders_each_doc() -> None:
    for entry in list_docs():
        html = load_doc_html(entry)
        assert html  # non-empty
        assert "<h1>" in html or "<h2>" in html


def test_get_doc_unknown_returns_none() -> None:
    assert get_doc("../secrets") is None
    assert get_doc("unknown") is None


# ─── Markdown renderer unit tests ───────────────────────────────────────────


def test_renderer_escapes_html() -> None:
    out = render_markdown("Hello <script>alert(1)</script> world")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_renderer_headings_and_inline() -> None:
    out = render_markdown("# Title\n\nSome **bold** and `code` and *italic*.")
    assert "<h1>Title</h1>" in out
    assert "<strong>bold</strong>" in out
    assert "<code>code</code>" in out
    assert "<em>italic</em>" in out


def test_renderer_lists() -> None:
    out = render_markdown("- one\n- two\n\n1. first\n2. second")
    assert "<ul>" in out and "<li>one</li>" in out
    assert "<ol>" in out and "<li>first</li>" in out


def test_renderer_table() -> None:
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    out = render_markdown(md)
    assert "<table" in out
    assert "<th scope=\"col\">A</th>" in out
    assert "<td>1</td>" in out


def test_renderer_code_fence_preserves_content() -> None:
    md = "```\nx = 1 < 2\n```"
    out = render_markdown(md)
    assert "<pre><code>" in out
    assert "x = 1 &lt; 2" in out


def test_renderer_link_only_safe_schemes() -> None:
    safe = render_markdown("[ok](https://example.com)")
    assert '<a href="https://example.com">ok</a>' in safe
    unsafe = render_markdown("[x](javascript:alert(1))")
    assert "<a" not in unsafe  # rendered as plain label
    assert "x" in unsafe
