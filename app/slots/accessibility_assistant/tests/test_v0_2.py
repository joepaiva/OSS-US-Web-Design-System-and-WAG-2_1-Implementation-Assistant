"""Accessibility Assistant v0.2 route tests.

Covers T-002, T-003, T-005, T-006, T-015, T-016, T-017
(FR-007 through FR-017). Every test cites the TS-NNN scenario it covers
from TEST-SCENARIOS.md, per the FR-357 compliance gate requirement.

Test categories per capability: happy path, 401 (auth), 403 (permission),
404/409/422 (validation/conflict), and cross-tenant isolation.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _admin_headers(org_with_roles: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], cast(dict[str, object], org_with_roles["admin"])["headers"])


def _end_user_headers(org_with_roles: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], cast(dict[str, object], org_with_roles["end_user"])["headers"])


def _cm_headers(org_with_roles: dict[str, object]) -> dict[str, str]:
    return cast(
        dict[str, str], cast(dict[str, object], org_with_roles["content_manager"])["headers"]
    )


# ────────────────────────────────────────────────────────────────────────
# T-002 / FR-010: Information Source Category Creation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_source_category_happy_path(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR010-1: authorized admin creates a category with unique name
    resp = await client.post(
        "/api/information-source-categories/",
        json={"name": "Code Repos", "description": "All source repos"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Code Repos"
    assert data["description"] == "All source repos"


@pytest.mark.asyncio
async def test_create_source_category_duplicate_name(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR010-2: duplicate category name is rejected
    headers = _admin_headers(org_with_roles)
    payload = {"name": "Docs", "description": None}
    resp1 = await client.post(
        "/api/information-source-categories/", json=payload, headers=headers
    )
    assert resp1.status_code == 201, resp1.text
    resp2 = await client.post(
        "/api/information-source-categories/", json=payload, headers=headers
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_source_category_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR010-3: End User denied access to information source category creation
    resp = await client.post(
        "/api/information-source-categories/",
        json={"name": "Denied Category"},
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_source_category_content_manager_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # FR-010: "An End User or Content Manager attempts to create ... denied"
    resp = await client.post(
        "/api/information-source-categories/",
        json={"name": "Denied Category 2"},
        headers=_cm_headers(org_with_roles),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_source_category_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/information-source-categories/", json={"name": "No Auth"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_source_category_missing_name_422(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.post(
        "/api/information-source-categories/",
        json={"description": "no name"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_source_category_cross_org_isolation(
    client: AsyncClient,
    other_user_token: dict[str, object],
    seeded_source_category: dict[str, object],
) -> None:
    other_headers = cast(dict[str, str], other_user_token["headers"])
    resp = await client.get(
        "/api/information-source-categories/", headers=other_headers
    )
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert seeded_source_category["id"] not in ids


# ────────────────────────────────────────────────────────────────────────
# T-003 / FR-011..FR-014: Information Source Configuration
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_source_types(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR011-1: all four source types appear in the selector
    # TS-FR011-2: each source type carries the correct form-variant hint
    resp = await client.get(
        "/api/information-sources/source-types", headers=_admin_headers(org_with_roles)
    )
    assert resp.status_code == 200
    types = {t["source_type"]: t["form_variant"] for t in resp.json()}
    assert set(types) == {
        "local_code_repo",
        "github_online_repo",
        "document_folder",
        "mcp_server",
    }
    assert types["local_code_repo"] == "folder_picker"
    assert types["document_folder"] == "folder_picker"
    assert types["github_online_repo"] == "url_and_credential"
    assert types["mcp_server"] == "server_address_and_credential"


@pytest.mark.asyncio
async def test_information_sources_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # FR-011: "An End User is authenticated ... denies access"
    resp = await client.get(
        "/api/information-sources/source-types", headers=_end_user_headers(org_with_roles)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_local_source_happy_path(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    tmp_path: Any,
) -> None:
    # TS-FR012-2: successful read access test saves source and closes window
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "local_code_repo",
            "name": "My Local Repo",
            "category_id": seeded_source_category["id"],
            "folder_path": str(tmp_path),
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "active"
    assert data["source_type"] == "local_code_repo"


@pytest.mark.asyncio
async def test_create_local_source_failed_access(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
) -> None:
    # TS-FR012-3: failed read access test prompts user to correct credentials
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "local_code_repo",
            "name": "Missing Folder",
            "category_id": seeded_source_category["id"],
            "folder_path": "/definitely/does/not/exist/anywhere",
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 503
    # Not persisted (FR-012: "the source is not saved until a successful test").
    list_resp = await client.get(
        "/api/information-sources/", headers=_admin_headers(org_with_roles)
    )
    assert all(s["name"] != "Missing Folder" for s in list_resp.json())


@pytest.mark.asyncio
async def test_create_local_source_never_executes_contents(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    tmp_path: Any,
) -> None:
    # TS-FR012-4: executable code in a connected source is never executed
    # during the access test. A script that would raise/exit if executed is
    # placed in the folder; the test only proves read-access, so creation
    # must succeed and the process must still be alive to assert on it.
    script = tmp_path / "dangerous.py"
    script.write_text("import sys; sys.exit(1)  # would kill the test runner if executed\n")
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "local_code_repo",
            "name": "Repo With Script",
            "category_id": seeded_source_category["id"],
            "folder_path": str(tmp_path),
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_create_github_source_happy_path(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR013-2: successful read access test saves GitHub source
    async def fake_test_github_access(github_url: str, access_token: str | None) -> bool:
        return True

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.test_github_access",
        fake_test_github_access,
    )
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "github_online_repo",
            "name": "GH Repo",
            "category_id": seeded_source_category["id"],
            "github_url": "https://github.com/example/repo",
            "access_token": "ghp_supersecrettoken",
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # SR-001: no plaintext credential is ever returned in API responses.
    assert "ghp_supersecrettoken" not in resp.text
    assert "access_token" not in body


@pytest.mark.asyncio
async def test_create_github_source_failed(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR013-3: failed read access test prompts user to correct credentials
    async def fake_test_github_access(github_url: str, access_token: str | None) -> bool:
        return False

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.test_github_access",
        fake_test_github_access,
    )
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "github_online_repo",
            "name": "Bad GH Repo",
            "category_id": seeded_source_category["id"],
            "github_url": "https://github.com/example/does-not-exist",
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_create_mcp_source_happy_path(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR014-2: successful MCP connectivity test saves source
    async def fake_test_mcp(address: str, credentials: Any) -> bool:
        return True

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.test_mcp_connectivity", fake_test_mcp
    )
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "mcp_server",
            "name": "MCP Source",
            "category_id": seeded_source_category["id"],
            "mcp_server_address": "https://mcp.example.com",
            "credentials": {"api_key": "secret-key"},
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    assert "secret-key" not in resp.text


@pytest.mark.asyncio
async def test_create_mcp_source_failed_cannot_save(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR014-3: failed connectivity test prompts user to correct credentials
    # TS-FR014-4: MCP source cannot be saved without a passing test
    async def fake_test_mcp(address: str, credentials: Any) -> bool:
        return False

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.test_mcp_connectivity", fake_test_mcp
    )
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "mcp_server",
            "name": "Bad MCP",
            "category_id": seeded_source_category["id"],
            "mcp_server_address": "https://mcp.example.com/unreachable",
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 503
    list_resp = await client.get(
        "/api/information-sources/", headers=_admin_headers(org_with_roles)
    )
    assert all(s["name"] != "Bad MCP" for s in list_resp.json())


@pytest.mark.asyncio
async def test_standalone_connectivity_tests_do_not_persist(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The standalone validate/verify/test endpoints never create a row."""
    headers = _admin_headers(org_with_roles)

    resp1 = await client.post(
        "/api/information-sources/local/validate-access",
        json={"folder_path": str(tmp_path)},
        headers=headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"

    async def fake_github(url: str, token: str | None) -> bool:
        return True

    # NOTE: routes.py imports these functions BY NAME (`from ...service import
    # test_github_access`), so the patch target is the name as bound in
    # routes.py's own namespace, not service.py's (a `from x import y`
    # import binds a separate reference — patching the source module's
    # attribute later does not affect an already-imported name elsewhere).
    monkeypatch.setattr(
        "app.slots.accessibility_assistant.routes.test_github_access", fake_github
    )
    resp2 = await client.post(
        "/api/information-sources/github/verify",
        json={"github_url": "https://github.com/example/repo"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "success"

    async def fake_mcp(address: str, credentials: Any) -> bool:
        return False

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.routes.test_mcp_connectivity", fake_mcp
    )
    resp3 = await client.post(
        "/api/information-sources/mcp/test",
        json={"mcp_server_address": "https://mcp.example.com"},
        headers=headers,
    )
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "failed"

    list_resp = await client.get("/api/information-sources/", headers=headers)
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_create_source_unknown_category_404(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.post(
        "/api/information-sources/",
        json={
            "source_type": "document_folder",
            "name": "Orphan Source",
            "category_id": 999999,
            "folder_path": "/tmp",
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────
# T-005 / FR-015: Question Category Configuration
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_question_category_happy_path(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR015-1: authorized admin creates a question category
    resp = await client.post(
        "/api/question-categories/",
        json={"name": "Billing", "description": "Billing questions"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Billing"


@pytest.mark.asyncio
async def test_create_question_category_duplicate_case_insensitive(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR015-2: duplicate question category name is rejected (case-insensitive)
    headers = _admin_headers(org_with_roles)
    resp1 = await client.post(
        "/api/question-categories/", json={"name": "Support"}, headers=headers
    )
    assert resp1.status_code == 201, resp1.text
    resp2 = await client.post(
        "/api/question-categories/", json={"name": "support"}, headers=headers
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_question_category_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR015-3: End User denied access to question category creation
    resp = await client.post(
        "/api/question-categories/",
        json={"name": "Denied"},
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_question_category_content_manager_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # FR-015: "An End User or Content Manager attempts to create ... denied"
    resp = await client.post(
        "/api/question-categories/",
        json={"name": "Denied CM"},
        headers=_cm_headers(org_with_roles),
    )
    assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# T-006 / FR-016: Manual FAQ Creation
# ────────────────────────────────────────────────────────────────────────


async def _make_question_category(
    client: AsyncClient, headers: dict[str, str], name: str
) -> int:
    resp = await client.post("/api/question-categories/", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


@pytest.mark.asyncio
async def test_create_faq_happy_path(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
) -> None:
    # TS-FR016-1 / TS-FR016-happy: authorized user creates FAQ with all
    # required fields — FAQ saved and appears in list
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "General")

    resp = await client.post(
        "/api/faqs/",
        json={
            "question": "How do I request an accommodation?",
            "answer": "Submit a request via the accessibility portal.",
            "question_category_ids": [qcat_id],
            "source_category_ids": [seeded_source_category["id"]],
            "source_ids": [seeded_information_source["id"]],
        },
        headers=_cm_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["question_category_ids"] == [qcat_id]
    assert data["source_category_ids"] == [seeded_source_category["id"]]
    assert data["source_ids"] == [seeded_information_source["id"]]

    # Appears in the v0.1 category-scoped browse list too.
    list_resp = await client.get(
        f"/assistant/categories/{qcat_id}/faqs", headers=admin_headers
    )
    assert list_resp.status_code == 200
    assert any(f["id"] == data["id"] for f in list_resp.json())


@pytest.mark.asyncio
async def test_create_faq_admin_allowed(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
) -> None:
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "Admin Category")
    resp = await client.post(
        "/api/faqs/",
        json={
            "question": "Admin-created question?",
            "answer": "Admin answer.",
            "question_category_ids": [qcat_id],
            "source_category_ids": [seeded_source_category["id"]],
            "source_ids": [seeded_information_source["id"]],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_create_faq_missing_fields_422(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR016-2 / TS-FR016-missing-fields: missing required fields rejected
    resp = await client.post(
        "/api/faqs/",
        json={"question": "Q?", "answer": "A."},
        headers=_cm_headers(org_with_roles),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_faq_unknown_reference_422(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
) -> None:
    resp = await client.post(
        "/api/faqs/",
        json={
            "question": "Q?",
            "answer": "A.",
            "question_category_ids": [999999],
            "source_category_ids": [seeded_source_category["id"]],
            "source_ids": [seeded_information_source["id"]],
        },
        headers=_cm_headers(org_with_roles),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_faq_end_user_denied(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
) -> None:
    # TS-FR016-3 / TS-FR016-end-user-blocked
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "End User Denied Cat")
    resp = await client.post(
        "/api/faqs/",
        json={
            "question": "Q?",
            "answer": "A.",
            "question_category_ids": [qcat_id],
            "source_category_ids": [seeded_source_category["id"]],
            "source_ids": [seeded_information_source["id"]],
        },
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# T-015 / FR-007: Deterministic-First Question Answering
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tiered_ask_faq_match(
    client: AsyncClient, org_with_roles: dict[str, object], session: AsyncSession
) -> None:
    # TS-FR007-1: deterministic tier returns FAQ answer without invoking LLM
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import FAQ

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    set_current_org_id(org_id)
    faq = FAQ(
        org_id=org_id,
        question="What is WCAG conformance?",
        answer="WCAG conformance means meeting the success criteria at a level.",
        reasoning="Definitional.",
    )
    session.add(faq)
    await session.flush()
    await session.commit()

    resp = await client.post(
        "/api/questions/",
        json={"question_text": "What is WCAG conformance?"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source"] == "faq"
    assert data["llm_invoked"] is False
    assert "conformance" in data["response_text"].lower()


@pytest.mark.asyncio
async def test_tiered_ask_falls_through_to_llm(
    client: AsyncClient, org_with_roles: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    # TS-FR007-2: no matching FAQ — system falls through to the LLM fallback tier
    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"response": "Use alt text.", "reasoning": "Accessibility '
                            'best practice.", "citations": []}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/questions/",
        json={"question_text": "How do I make images accessible for screen readers?"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source"] == "llm"
    assert data["llm_invoked"] is True
    assert "alt text" in data["response_text"].lower()


@pytest.mark.asyncio
async def test_tiered_ask_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/questions/", json={"question_text": "Hello?"})
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# T-016 / FR-008: Tiered Answer Fallback with Unanswerable Alert
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_answer_llm_success(
    client: AsyncClient, org_with_roles: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    # TS-FR008-1: LLM fallback produces a response with reasoning + citations
    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"response": "Add captions.", "reasoning": "Improves access.", '
                            '"citations": [{"source_name": "WCAG", "hyperlink": '
                            '"https://www.w3.org/WAI/WCAG21/"}]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/questions/answer",
        json={"question_text": "How do I make video content accessible?"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tier"] == "llm_frontier"
    assert data["status"] is None
    assert len(data["citations"]) == 1


@pytest.mark.asyncio
async def test_answer_unanswerable_dispatches_alert(
    client: AsyncClient, org_with_roles: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    # TS-FR008-2: both tiers exhausted — user informed, alert sent to
    # Org Admin and Content Manager
    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        from app.llm.service import LLMKeyUnavailable

        raise LLMKeyUnavailable("no key configured for this org")

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/questions/answer",
        json={"question_text": "What is the meaning of accessible design?"},
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tier"] == "unanswerable"
    assert data["status"] == "no_answer_available"
    assert data["alert_sent"] is True

    # Admin can list + acknowledge the alert.
    admin_headers = _admin_headers(org_with_roles)
    alerts_resp = await client.get("/api/questions/alerts", headers=admin_headers)
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert len(alerts) == 1
    assert alerts[0]["acknowledged"] is False

    ack_resp = await client.patch(
        f"/api/questions/alerts/{alerts[0]['id']}/acknowledge", headers=admin_headers
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["acknowledged"] is True


@pytest.mark.asyncio
async def test_answer_alerts_admin_only(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.get(
        "/api/questions/alerts", headers=_end_user_headers(org_with_roles)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_answer_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/questions/answer", json={"question_text": "Hello?"})
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# T-017 / FR-009: LLM Fallback Mode Configuration
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_fallback_config_upsert_and_get(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
) -> None:
    # TS-FR009-1: administrator configures the LLM fallback grounding mode
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "Fallback Category")
    src_cat_id = seeded_source_category["id"]

    put_resp = await client.put(
        f"/api/llm-fallback-config/{src_cat_id}/{qcat_id}",
        json={"mode": "retrieval_augmented"},
        headers=admin_headers,
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["mode"] == "retrieval_augmented"

    get_resp = await client.get(
        f"/api/llm-fallback-config/{src_cat_id}/{qcat_id}", headers=admin_headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["mode"] == "retrieval_augmented"

    list_resp = await client.get("/api/llm-fallback-config/", headers=admin_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    delete_resp = await client.delete(
        f"/api/llm-fallback-config/{src_cat_id}/{qcat_id}", headers=admin_headers
    )
    assert delete_resp.status_code == 204

    get_after_delete = await client.get(
        f"/api/llm-fallback-config/{src_cat_id}/{qcat_id}", headers=admin_headers
    )
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_llm_fallback_config_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR009-2: End User denied access to LLM fallback configuration
    resp = await client.get(
        "/api/llm-fallback-config/", headers=_end_user_headers(org_with_roles)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_llm_fallback_config_content_manager_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # FR-009's Linked Personas are Platform/Organization Administrator only.
    resp = await client.get(
        "/api/llm-fallback-config/", headers=_cm_headers(org_with_roles)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_llm_fallback_config_unknown_category_404(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.put(
        "/api/llm-fallback-config/999999/999999",
        json={"mode": "frontier_general_knowledge"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_llm_fallback_config_drives_retrieval_augmented_mode(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "RAG Category")
    await client.put(
        f"/api/llm-fallback-config/{seeded_source_category['id']}/{qcat_id}",
        json={"mode": "retrieval_augmented"},
        headers=admin_headers,
    )

    captured: dict[str, Any] = {}

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        captured["messages"] = kwargs["messages"]
        return {
            "choices": [
                {"message": {"content": '{"response": "Grounded answer.", "reasoning": "", "citations": []}'}}
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/questions/answer",
        json={
            "question_text": "What repositories are configured for this category?",
            "question_category_id": qcat_id,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tier"] == "llm_retrieval_augmented"
    system_message = captured["messages"][0]["content"]
    assert seeded_information_source["name"] in system_message
