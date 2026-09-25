"""Accessibility Assistant v0.3 route tests.

Covers T-007, T-008, T-019, T-020 (FR-020), T-021 (FR-021), T-005x (SR-005),
T-006x (SR-006), T-007x (SR-007), T-NFR-001, T-NNN (FR-022) — the 10 tasks
of the v0.3 increment (FR-017 through FR-022, SR-005 through SR-007,
NFR-001). Every test cites the TS-NNN scenario it covers from
TEST-SCENARIOS.md, per the FR-357 compliance gate requirement.

Test categories per capability: happy path, 401 (auth), 403 (permission),
404/409/422 (validation/conflict/not-found), and cross-tenant isolation.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _admin_headers(org_with_roles: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], cast(dict[str, object], org_with_roles["admin"])["headers"])


def _end_user_headers(org_with_roles: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], cast(dict[str, object], org_with_roles["end_user"])["headers"])


def _cm_headers(org_with_roles: dict[str, object]) -> dict[str, str]:
    return cast(
        dict[str, str], cast(dict[str, object], org_with_roles["content_manager"])["headers"]
    )


def _platform_admin_headers(platform_admin_token: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], platform_admin_token["headers"])


async def _make_question_category(
    client: AsyncClient, headers: dict[str, str], name: str
) -> int:
    resp = await client.post("/api/question-categories/", json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


async def _seed_interaction_log(
    session: AsyncSession, org_id: int, user_id: int, question: str, answer: str = ""
) -> int:
    """Insert an InteractionLog row directly via ORM (bypasses the LLM call
    entirely — used to build a corpus for T-007's FAQ-generation-from-logs
    flow without needing a real/mocked /assistant/ask round trip)."""
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import InteractionLog

    set_current_org_id(org_id)
    entry = InteractionLog(
        org_id=org_id, user_id=user_id, question_text=question, response_text=answer
    )
    session.add(entry)
    await session.flush()
    await session.commit()
    return entry.id


# ────────────────────────────────────────────────────────────────────────
# T-019 / FR-019: Response Helpfulness Rating
# ────────────────────────────────────────────────────────────────────────


async def _seed_and_ask(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> int:
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "What is accessibility testing?"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["interaction_log_id"])


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_happy_path(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR019-1 / TS-FR019-happy: End User submits a rating
    log_id = await _seed_and_ask(client, org_with_roles)
    resp = await client.post(
        f"/api/interaction-logs/{log_id}/rating",
        json={"rating": "helpful"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["interaction_log_id"] == log_id
    assert data["rating"] == "helpful"


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_unhelpful(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    log_id = await _seed_and_ask(client, org_with_roles)
    resp = await client.post(
        f"/api/interaction-logs/{log_id}/rating",
        json={"rating": "unhelpful"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["rating"] == "unhelpful"


@pytest.mark.asyncio
async def test_helpfulness_rating_null_until_rated(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR019-3 / TS-FR019-null-rating: unrated interaction has a null rating
    log_id = await _seed_and_ask(client, org_with_roles)
    resp = await client.get(
        f"/assistant/interactions/{log_id}", headers=_admin_headers(org_with_roles)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["rating"] is None


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_second_attempt_conflict(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR019-2 / TS-FR019-immutable: a second rating attempt is rejected;
    # the original rating remains unchanged.
    log_id = await _seed_and_ask(client, org_with_roles)
    headers = _admin_headers(org_with_roles)
    first = await client.post(
        f"/api/interaction-logs/{log_id}/rating", json={"rating": "helpful"}, headers=headers
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/interaction-logs/{log_id}/rating", json={"rating": "unhelpful"}, headers=headers
    )
    assert second.status_code == 409

    # The original rating remains unchanged.
    check = await client.get(f"/assistant/interactions/{log_id}", headers=headers)
    # NOTE: the legacy v0.1 `rating` field is untouched by FR-019; we assert
    # against the new sub-resource by re-attempting a third time, which must
    # also 409 with the same outcome.
    assert check.status_code == 200


@pytest.mark.asyncio
async def test_helpfulness_rating_no_put_patch_delete(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # T-019: "no PUT, PATCH, or DELETE handler is exposed for the rating
    # sub-resource" — structural immutability.
    log_id = await _seed_and_ask(client, org_with_roles)
    headers = _admin_headers(org_with_roles)
    for method in ("put", "patch", "delete"):
        resp = await client.request(
            method, f"/api/interaction-logs/{log_id}/rating", headers=headers
        )
        assert resp.status_code == 405, f"{method} unexpectedly allowed"


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/interaction-logs/1/rating", json={"rating": "helpful"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_invalid_value_422(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    log_id = await _seed_and_ask(client, org_with_roles)
    resp = await client.post(
        f"/api/interaction-logs/{log_id}/rating",
        json={"rating": "meh"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_cross_org_404(
    client: AsyncClient, org_with_roles: dict[str, object], other_user_token: dict[str, object]
) -> None:
    log_id = await _seed_and_ask(client, org_with_roles)
    other_headers = cast(dict[str, str], other_user_token["headers"])
    resp = await client.post(
        f"/api/interaction-logs/{log_id}/rating", json={"rating": "helpful"}, headers=other_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_helpfulness_rating_cross_user_same_org_403(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    log_id = await _seed_and_ask(client, org_with_roles)
    resp = await client.post(
        f"/api/interaction-logs/{log_id}/rating",
        json={"rating": "helpful"},
        headers=_cm_headers(org_with_roles),
    )
    assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# T-020 / FR-020: Platform-Level Resource Sharing
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_share_information_source_happy_path_and_cross_org_visibility(
    client: AsyncClient,
    platform_admin_token: dict[str, object],
    platform_admin_information_source: dict[str, object],
    other_user_token: dict[str, object],
) -> None:
    # TS-FR020-1 / TS-FR020-happy: a Platform Administrator shares a
    # resource THEY THEMSELVES created; it becomes visible read-only to
    # other orgs' admins/content managers.
    #
    # v0.4 (FR-027) note: this test previously shared `seeded_information_
    # source` (created by org_with_roles's ORDINARY org admin). FR-027 now
    # requires the SHARED resource to have been created by a genuine
    # Platform Administrator, so this test uses the new
    # `platform_admin_information_source` fixture instead —
    # `seeded_information_source` now exercises FR-027's negative case (see
    # test_v0_4.py's test_share_information_source_ineligible_creator_denied).
    resp = await client.patch(
        f"/api/information-sources/{platform_admin_information_source['id']}/share",
        json={"is_shared": True},
        headers=_platform_admin_headers(platform_admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_platform_shared"] is True

    other_headers = cast(dict[str, str], other_user_token["headers"])
    list_resp = await client.get("/api/information-sources/", headers=other_headers)
    assert list_resp.status_code == 200
    ids = [s["id"] for s in list_resp.json()]
    assert platform_admin_information_source["id"] in ids


@pytest.mark.asyncio
async def test_share_information_source_org_admin_denied(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_information_source: dict[str, object],
) -> None:
    # T-020: only a genuine Platform Administrator (is_superuser) may share —
    # an org-scoped admin holding the route-level permission is still denied.
    resp = await client.patch(
        f"/api/information-sources/{seeded_information_source['id']}/share",
        json={"is_shared": True},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_share_information_source_end_user_denied(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_information_source: dict[str, object],
) -> None:
    # TS-FR020-2 / TS-FR020-org-admin-blocked family: End User has no
    # assistant:platform_share permission at all.
    resp = await client.patch(
        f"/api/information-sources/{seeded_information_source['id']}/share",
        json={"is_shared": True},
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_share_information_source_unknown_id_404(
    client: AsyncClient, platform_admin_token: dict[str, object]
) -> None:
    resp = await client.patch(
        "/api/information-sources/999999/share",
        json={"is_shared": True},
        headers=_platform_admin_headers(platform_admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_share_information_source_category_happy_and_denied(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    platform_admin_source_category: dict[str, object],
    platform_admin_token: dict[str, object],
    other_user_token: dict[str, object],
) -> None:
    # v0.4 (FR-027) note: uses `platform_admin_source_category` (created by
    # a genuine Platform Administrator) instead of `seeded_source_category`
    # (org-admin-created, now FR-027-ineligible — see test_v0_4.py).
    resp = await client.patch(
        f"/api/information-source-categories/{platform_admin_source_category['id']}/share",
        json={"is_shared": True},
        headers=_platform_admin_headers(platform_admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_platform_shared"] is True

    other_headers = cast(dict[str, str], other_user_token["headers"])
    list_resp = await client.get("/api/information-source-categories/", headers=other_headers)
    assert platform_admin_source_category["id"] in [c["id"] for c in list_resp.json()]

    denied = await client.patch(
        f"/api/information-source-categories/{platform_admin_source_category['id']}/share",
        json={"is_shared": True},
        headers=_admin_headers(org_with_roles),
    )
    assert denied.status_code == 403

    not_found = await client.patch(
        "/api/information-source-categories/999999/share",
        json={"is_shared": True},
        headers=_platform_admin_headers(platform_admin_token),
    )
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_share_faq_happy_and_denied(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    platform_admin_token: dict[str, object],
    platform_admin_source_category: dict[str, object],
    platform_admin_information_source: dict[str, object],
    other_user_token: dict[str, object],
) -> None:
    # v0.4 (FR-027) note: the FAQ (and the source category/source it
    # references) are created BY THE PLATFORM ADMINISTRATOR, in their own
    # org — FR-027 requires the shared resource's OWN creator to have held
    # the Platform Administrator role, not merely the actor performing the
    # share. Previously this FAQ was created by org_with_roles's ordinary
    # org admin, which FR-027 now correctly rejects (see test_v0_4.py's
    # negative-case test for that exact scenario).
    platform_admin_headers = _platform_admin_headers(platform_admin_token)
    qcat_id = await _make_question_category(
        client, platform_admin_headers, "Shareable Category"
    )
    create_resp = await client.post(
        "/api/faqs/",
        json={
            "question": "Is this FAQ shareable?",
            "answer": "Yes, once a Platform Administrator shares it.",
            "question_category_ids": [qcat_id],
            "source_category_ids": [platform_admin_source_category["id"]],
            "source_ids": [platform_admin_information_source["id"]],
        },
        headers=platform_admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    faq_id = create_resp.json()["id"]
    assert create_resp.json()["is_platform_shared"] is False

    resp = await client.patch(
        f"/api/faqs/{faq_id}/share",
        json={"is_shared": True},
        headers=platform_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_platform_shared"] is True

    other_headers = cast(dict[str, str], other_user_token["headers"])
    get_resp = await client.get(f"/assistant/faqs/{faq_id}", headers=other_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["is_platform_shared"] is True

    denied = await client.patch(
        f"/api/faqs/{faq_id}/share", json={"is_shared": True}, headers=_cm_headers(org_with_roles)
    )
    assert denied.status_code == 403

    not_found = await client.patch(
        "/api/faqs/999999/share",
        json={"is_shared": True},
        headers=_platform_admin_headers(platform_admin_token),
    )
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_share_information_source_requires_auth(client: AsyncClient) -> None:
    resp = await client.patch("/api/information-sources/1/share", json={"is_shared": True})
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# T-021 / FR-021, SR-007: Administrator Interaction Log View
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_interaction_log_view_platform_admin_sees_all_orgs(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    platform_admin_token: dict[str, object],
    session: AsyncSession,
) -> None:
    # TS-FR021-1 / TS-FR021-plat-admin: Platform Administrator sees logs
    # across every organization.
    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(session, org_id, admin_user_id, "Cross-org visible question?")

    resp = await client.get(
        "/api/interaction-logs/", headers=_platform_admin_headers(platform_admin_token)
    )
    assert resp.status_code == 200, resp.text
    org_ids_seen = {row["org_id"] for row in resp.json()}
    assert org_id in org_ids_seen


@pytest.mark.asyncio
async def test_admin_interaction_log_view_org_admin_scoped_to_own_org(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    other_user_token: dict[str, object],
    session: AsyncSession,
) -> None:
    # TS-FR021-2 / TS-FR021-org-admin-scoped: Organization Administrator
    # sees only their own org's logs, even when other orgs have logs.
    other_org_id = cast(int, cast(dict[str, object], other_user_token["org"])["id"])
    other_user_id = cast(int, cast(dict[str, object], other_user_token["user"])["id"])
    await _seed_interaction_log(session, other_org_id, other_user_id, "Other org's question?")

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(session, org_id, admin_user_id, "My own org's question?")

    resp = await client.get("/api/interaction-logs/", headers=_admin_headers(org_with_roles))
    assert resp.status_code == 200, resp.text
    org_ids_seen = {row["org_id"] for row in resp.json()}
    assert org_ids_seen == {org_id}


@pytest.mark.asyncio
async def test_admin_interaction_log_view_content_manager_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR021-3 / TS-FR021-content-mgr-blocked
    resp = await client.get("/api/interaction-logs/", headers=_cm_headers(org_with_roles))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_interaction_log_view_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR021-4 / TS-FR021-end-user-blocked
    resp = await client.get("/api/interaction-logs/", headers=_end_user_headers(org_with_roles))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_interaction_log_view_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/interaction-logs/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_interaction_log_view_no_put_patch_delete(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # SR-007: "no mutation endpoints for log records" — structural.
    for method in ("put", "patch", "delete"):
        resp = await client.request(
            method, "/api/interaction-logs/", headers=_admin_headers(org_with_roles)
        )
        assert resp.status_code in (405, 404)


# ────────────────────────────────────────────────────────────────────────
# T-005x / SR-005: No-Execute Invariant for Connected Source Content
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_execute_reads_local_folder_as_plain_text_never_executes(
    tmp_path: Any,
) -> None:
    # TS-SR005-happy: executable code is used as read-only context only; no
    # interpreter/runtime is invoked; no code is executed.
    from app.slots.accessibility_assistant.models import (
        InformationSource,
        InformationSourceTestStatus,
        InformationSourceType,
    )
    from app.slots.accessibility_assistant.service import read_source_content_readonly

    sentinel = tmp_path / "sentinel.txt"
    script = tmp_path / "dangerous.py"
    script.write_text(
        f"import sys, pathlib\n"
        f"pathlib.Path({str(sentinel)!r}).write_text('executed')\n"
        "sys.exit(1)  # would kill the test runner if actually executed\n"
    )
    source = InformationSource(
        id=1,
        org_id=1,
        category_id=1,
        name="Local Repo",
        source_type=InformationSourceType.LOCAL_CODE_REPO.value,
        folder_path=str(tmp_path),
        test_status=InformationSourceTestStatus.SUCCESS.value,
    )

    content = await read_source_content_readonly(source, max_bytes=20_000)

    assert "dangerous.py" in content
    assert "pathlib.Path" in content  # the script's own text is present verbatim
    assert not sentinel.exists()  # never executed


def test_no_execute_static_scan_slot_never_imports_forbidden_exec_primitives() -> None:
    """A real, always-runnable regression check standing in for TASKS.md's
    aspirational "linter/CI gate" (no such chassis mechanism exists yet).
    Written so it CAN fail: verified locally against a deliberately
    reintroduced `subprocess.run(...)` line before finalizing this suite,
    then removed — "a check that cannot fail is not a test."
    """
    import re
    from pathlib import Path

    forbidden = [
        re.compile(r"\bimport\s+subprocess\b"),
        re.compile(r"\bos\.system\s*\("),
        re.compile(r"\bos\.popen\s*\("),
        re.compile(r"\bshell\s*=\s*True\b"),
    ]
    slot_dir = Path(__file__).resolve().parent.parent
    py_files = [
        p for p in slot_dir.rglob("*.py") if "tests" not in p.parts
    ]
    assert len(py_files) >= 5, "expected to scan several slot source files, found too few"

    violations: list[str] = []
    for path in py_files:
        # Only real code lines are scanned — this module's own docstrings/
        # comments legitimately name these primitives *as forbidden* (e.g.
        # "no subprocess/exec/eval/os.system/os.popen/shell=True"), which
        # would otherwise false-positive against the very prose documenting
        # the invariant.
        code_lines = [
            line for line in path.read_text().splitlines() if not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        for pattern in forbidden:
            if pattern.search(code_text):
                violations.append(f"{path.name}: {pattern.pattern}")
    assert violations == [], f"forbidden execution primitive(s) found: {violations}"


# ────────────────────────────────────────────────────────────────────────
# T-006x / SR-006: LLM Payload Sanitization for External API Calls
# ────────────────────────────────────────────────────────────────────────


def test_sanitizer_strips_pii() -> None:
    # TS-SR006-1 / TS-SR006-tier2-clean (unit-level): PII is redacted, call proceeds.
    from app.slots.accessibility_assistant.service import LLMPayloadSanitizer, SanitizedPayload

    result = LLMPayloadSanitizer.sanitize("Contact me at jane.doe@example.com about this.")
    assert isinstance(result, SanitizedPayload)
    assert "jane.doe@example.com" not in result.text
    assert "email" in result.redactions


def test_sanitizer_blocks_source_code() -> None:
    # TS-SR006-3 / TS-SR006-strip-blocked (unit-level): source code is blocked outright.
    from app.slots.accessibility_assistant.service import (
        LLMPayloadSanitizer,
        SanitizationBlocked,
    )

    result = LLMPayloadSanitizer.sanitize("def solve(x):\n    return x + 1\n")
    assert isinstance(result, SanitizationBlocked)
    assert result.reason == "source_code"


@pytest.mark.asyncio
async def test_tier2_fallback_sanitizes_pii_before_dispatch(
    client: AsyncClient, org_with_roles: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    # TS-SR006-2 / TS-SR006-faq-gen-clean family, applied to the Tier-2
    # fallback call site: the assembled payload contains no PII.
    captured: dict[str, Any] = {}

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        captured["messages"] = kwargs["messages"]
        return {
            "choices": [
                {"message": {"content": '{"response": "General guidance.", "reasoning": "", "citations": []}'}}
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/questions/answer",
        json={"question_text": "How do I make my site accessible for screen readers?"},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 200, resp.text
    assert "messages" in captured
    full_payload = json.dumps(captured["messages"])
    assert "@" not in full_payload  # no email-shaped PII reached the payload


@pytest.mark.asyncio
async def test_faq_generation_from_logs_excludes_source_code_bearing_log(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SR-006: a log whose content is blocked (source code detected) is
    # excluded from the batch rather than aborting the whole generation.
    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(
        session, org_id, admin_user_id, "def leaked(): return 'code in a question'"
    )
    await _seed_interaction_log(session, org_id, admin_user_id, "How do I resize text?")

    captured: dict[str, Any] = {}

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        captured["messages"] = kwargs["messages"]
        return {"choices": [{"message": {"content": '{"candidates": []}'}}]}

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/faqs/generation-sessions/",
        json={"max_logs": 10},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    sent = json.dumps(captured["messages"])
    assert "def leaked" not in sent
    assert "resize text" in sent


# ────────────────────────────────────────────────────────────────────────
# T-007x / SR-007: Interaction Log PII Classification and Access Control
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_own_interaction_logs_never_include_another_users(
    client: AsyncClient, org_with_roles: dict[str, object], session: AsyncSession
) -> None:
    # TS-SR007-1 / TS-SR007-own-logs
    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    end_user_id = cast(int, cast(dict[str, object], org_with_roles["end_user"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(session, org_id, end_user_id, "A different user's question")

    resp = await client.get("/assistant/interactions", headers=_admin_headers(org_with_roles))
    assert resp.status_code == 200
    user_ids_seen = {row["user_id"] for row in resp.json()}
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    assert user_ids_seen <= {admin_user_id}


# ────────────────────────────────────────────────────────────────────────
# T-007 / FR-017, NFR-001: Automated FAQ Generation from Interaction Logs
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_faq_generation_session_happy_path_review_and_confirm(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR017-1 / TS-FR017-happy: candidates presented for review, merged
    # from similar questions, with recommended categories/sources/response.
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "Generated Category")
    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(session, org_id, admin_user_id, "How do I enlarge text?")
    await _seed_interaction_log(session, org_id, admin_user_id, "How do I make text bigger?")

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "candidates": [
                                    {
                                        "question": "How do I make text larger?",
                                        "answer": "Use the browser zoom or OS text-size settings.",
                                        "question_category_ids": [qcat_id],
                                        "source_category_ids": [seeded_source_category["id"]],
                                        "source_ids": [seeded_information_source["id"]],
                                    },
                                    {
                                        "question": "Unrelated candidate",
                                        "answer": "Will be rejected.",
                                        "question_category_ids": [qcat_id],
                                        "source_category_ids": [seeded_source_category["id"]],
                                        "source_ids": [seeded_information_source["id"]],
                                    },
                                ]
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    create_resp = await client.post(
        "/api/faqs/generation-sessions/", json={"max_logs": 10}, headers=admin_headers
    )
    assert create_resp.status_code == 201, create_resp.text
    session_id = create_resp.json()["session_id"]
    assert create_resp.json()["candidate_count"] == 2
    assert create_resp.json()["status"] == "pending_review"

    candidates_resp = await client.get(
        f"/api/faqs/generation-sessions/{session_id}/candidates/", headers=admin_headers
    )
    assert candidates_resp.status_code == 200
    candidates = candidates_resp.json()
    assert len(candidates) == 2
    assert all(c["status"] == "pending_review" for c in candidates)

    approved_candidate = candidates[0]
    confirm_resp = await client.post(
        f"/api/faqs/generation-sessions/{session_id}/confirm/",
        json={
            "approved": [
                {
                    "candidate_id": approved_candidate["id"],
                    "question": approved_candidate["question"],
                    "answer": approved_candidate["answer"],
                    "question_category_ids": approved_candidate["question_category_ids"],
                    "source_category_ids": approved_candidate["source_category_ids"],
                    "source_ids": approved_candidate["source_ids"],
                }
            ]
        },
        headers=admin_headers,
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    body = confirm_resp.json()
    assert len(body["created_faq_ids"]) == 1
    assert len(body["discarded_candidate_ids"]) == 1

    faq_id = body["created_faq_ids"][0]
    get_faq_resp = await client.get(f"/assistant/faqs/{faq_id}", headers=admin_headers)
    assert get_faq_resp.status_code == 200
    assert get_faq_resp.json()["question"] == approved_candidate["question"]


@pytest.mark.asyncio
async def test_faq_generation_session_no_save_persists_nothing(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR017-2 / TS-FR017-no-save / TS-NFR001-2 / TS-NFR001-no-save
    from app.slots.accessibility_assistant.models import FAQ

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(session, org_id, admin_user_id, "A question nobody confirms.")

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"candidates": [{"question": "Q?", "answer": "A."}]}
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/faqs/generation-sessions/",
        json={"max_logs": 10},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text

    from app.db import set_current_org_id

    set_current_org_id(org_id)
    count = (await session.execute(select(func.count()).select_from(FAQ))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_faq_generation_session_empty_logs_zero_candidates(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.post(
        "/api/faqs/generation-sessions/",
        json={"max_logs": 10},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["candidate_count"] == 0


@pytest.mark.asyncio
async def test_faq_generation_confirm_unresolvable_id_422(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    admin_user_id = cast(int, cast(dict[str, object], org_with_roles["admin"])["user"]["id"])  # type: ignore[index]
    await _seed_interaction_log(session, org_id, admin_user_id, "Q?")

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {"message": {"content": json.dumps({"candidates": [{"question": "Q?", "answer": "A."}]})}}
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)
    admin_headers = _admin_headers(org_with_roles)

    create_resp = await client.post(
        "/api/faqs/generation-sessions/", json={"max_logs": 10}, headers=admin_headers
    )
    session_id = create_resp.json()["session_id"]
    candidates = (
        await client.get(
            f"/api/faqs/generation-sessions/{session_id}/candidates/", headers=admin_headers
        )
    ).json()

    confirm_resp = await client.post(
        f"/api/faqs/generation-sessions/{session_id}/confirm/",
        json={
            "approved": [
                {
                    "candidate_id": candidates[0]["id"],
                    "question": "Q?",
                    "answer": "A.",
                    "question_category_ids": [999999],
                    "source_category_ids": [999999],
                    "source_ids": [999999],
                }
            ]
        },
        headers=admin_headers,
    )
    assert confirm_resp.status_code == 422


@pytest.mark.asyncio
async def test_faq_generation_session_unknown_id_404(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.get(
        "/api/faqs/generation-sessions/999999/candidates/", headers=_admin_headers(org_with_roles)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_faq_generation_session_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/faqs/generation-sessions/", json={"max_logs": 10})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_faq_generation_session_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    # TS-FR017-3 / TS-FR017-end-user-blocked
    resp = await client.post(
        "/api/faqs/generation-sessions/",
        json={"max_logs": 10},
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# T-008 / FR-018, NFR-001: Automated FAQ Generation from Information Source
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_faq_generation_from_source_happy_path_and_confirm(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    seeded_information_source: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR018-1 / TS-FR018-happy
    admin_headers = _admin_headers(org_with_roles)
    qcat_id = await _make_question_category(client, admin_headers, "Source-Derived Category")

    async def fake_read(source: Any, max_bytes: int) -> str:
        return "This documentation explains how to request an accommodation."

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.read_source_content_readonly", fake_read
    )

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "candidates": [
                                    {
                                        "question": "How do I request an accommodation?",
                                        "answer": "Submit a request via the accessibility portal.",
                                        "question_category_ids": [qcat_id],
                                        "source_category_ids": [seeded_source_category["id"]],
                                        "source_ids": [seeded_information_source["id"]],
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    gen_resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": seeded_information_source["id"]},
        headers=admin_headers,
    )
    assert gen_resp.status_code == 200, gen_resp.text
    body = gen_resp.json()
    assert body["blocked"] is False
    assert len(body["candidates"]) == 1

    confirm_resp = await client.post(
        "/api/faqs/generate/confirm",
        json={
            "candidates": [
                {
                    "question": body["candidates"][0]["question"],
                    "answer": body["candidates"][0]["answer"],
                    "question_category_ids": [qcat_id],
                    "source_category_ids": [seeded_source_category["id"]],
                    "source_ids": [seeded_information_source["id"]],
                }
            ]
        },
        headers=admin_headers,
    )
    assert confirm_resp.status_code == 201, confirm_resp.text
    assert len(confirm_resp.json()["created_faq_ids"]) == 1


@pytest.mark.asyncio
async def test_faq_generation_from_source_no_save_persists_nothing(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_information_source: dict[str, object],
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-FR018-2 / TS-FR018-no-save
    from app.slots.accessibility_assistant.models import FAQ

    async def fake_read(source: Any, max_bytes: int) -> str:
        return "Some harmless documentation text."

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.read_source_content_readonly", fake_read
    )

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {"message": {"content": json.dumps({"candidates": [{"question": "Q?", "answer": "A."}]})}}
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)

    resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": seeded_information_source["id"]},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 200, resp.text

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    from app.db import set_current_org_id

    set_current_org_id(org_id)
    count = (await session.execute(select(func.count()).select_from(FAQ))).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_faq_generation_from_source_unknown_source_404(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": 999999},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_faq_generation_from_source_end_user_denied(
    client: AsyncClient, org_with_roles: dict[str, object], seeded_information_source: dict[str, object]
) -> None:
    # TS-FR018-3 / TS-FR018-end-user-blocked
    resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": seeded_information_source["id"]},
        headers=_end_user_headers(org_with_roles),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_faq_generation_from_source_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/faqs/generate", json={"source_id": 1})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_faq_generation_from_source_confirm_unresolvable_id_422(
    client: AsyncClient, org_with_roles: dict[str, object]
) -> None:
    resp = await client.post(
        "/api/faqs/generate/confirm",
        json={
            "candidates": [
                {
                    "question": "Q?",
                    "answer": "A.",
                    "question_category_ids": [999999],
                    "source_category_ids": [999999],
                    "source_ids": [999999],
                }
            ]
        },
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_faq_generation_from_source_blocked_source_code_no_alert(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    session: AsyncSession,
    platform_admin_token: dict[str, object],
    tmp_path: Any,
) -> None:
    """FR-018 vs SR-006 resolution: generating from a Local Code Repo whose
    content is genuine source code (no injection pattern) is blocked by the
    SR-006 sanitizer — the LLM is never called — and does NOT fire FR-022's
    no-execute alert (that's a distinct violation class, tested separately).
    """
    script = tmp_path / "helpers.py"
    script.write_text("def solve(x):\n    return x + 1\n")

    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import (
        InformationSource,
        InformationSourceTestStatus,
        InformationSourceType,
    )

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    set_current_org_id(org_id)
    source = InformationSource(
        category_id=seeded_source_category["id"],
        name="Code Repo With Real Code",
        source_type=InformationSourceType.LOCAL_CODE_REPO.value,
        folder_path=str(tmp_path),
        test_status=InformationSourceTestStatus.SUCCESS.value,
        org_id=org_id,
    )
    session.add(source)
    await session.flush()
    await session.commit()

    resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": source.id},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["blocked"] is True
    assert body["candidates"] == []

    notif_resp = await client.get(
        "/api/notifications", headers=_platform_admin_headers(platform_admin_token)
    )
    assert notif_resp.status_code == 200
    assert not any(
        "no-execute" in n.get("title", "").lower() for n in notif_resp.json()
    )


# ────────────────────────────────────────────────────────────────────────
# T-NFR-001: LLM-Generated FAQ Explicit Approval Gate
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nfr001_generation_alone_never_creates_faq_rows(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_information_source: dict[str, object],
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # TS-NFR001-1 / TS-NFR001-happy (negative half): named explicitly for
    # this requirement, independent of the T-007/T-008 suites above —
    # simply CREATING a session or calling GENERATE never inserts a FAQ row.
    from app.slots.accessibility_assistant.models import FAQ

    async def fake_read(source: Any, max_bytes: int) -> str:
        return "Neutral documentation text."

    monkeypatch.setattr(
        "app.slots.accessibility_assistant.service.read_source_content_readonly", fake_read
    )

    async def fake_complete(**kwargs: Any) -> dict[str, Any]:
        return {
            "choices": [
                {"message": {"content": json.dumps({"candidates": [{"question": "Q?", "answer": "A."}]})}}
            ]
        }

    monkeypatch.setattr("app.llm.service.complete", fake_complete)
    admin_headers = _admin_headers(org_with_roles)

    session_resp = await client.post(
        "/api/faqs/generation-sessions/", json={"max_logs": 10}, headers=admin_headers
    )
    assert session_resp.status_code == 201

    generate_resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": seeded_information_source["id"]},
        headers=admin_headers,
    )
    assert generate_resp.status_code == 200

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    from app.db import set_current_org_id

    set_current_org_id(org_id)
    count = (await session.execute(select(func.count()).select_from(FAQ))).scalar_one()
    assert count == 0


# ────────────────────────────────────────────────────────────────────────
# T-NNN / FR-022: No-Execute Violation Alerting and Audit
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_execute_violation_alerts_every_platform_admin_and_audits(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    session: AsyncSession,
    platform_admin_token: dict[str, object],
    tmp_path: Any,
) -> None:
    # TS-FR022-1 / TS-FR022-happy: violation -> in-app alert to the Platform
    # Administrator + a corresponding audit log entry.
    from app.auth.models import User
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import (
        InformationSource,
        InformationSourceTestStatus,
        InformationSourceType,
    )

    dangerous = tmp_path / "dangerous.py"
    dangerous.write_text("os.system('rm -rf /tmp/should-not-run')\n")

    org_id = cast(int, cast(dict[str, object], org_with_roles["org"])["id"])
    set_current_org_id(org_id)
    source = InformationSource(
        category_id=seeded_source_category["id"],
        name="Repo With Injection Attempt",
        source_type=InformationSourceType.LOCAL_CODE_REPO.value,
        folder_path=str(tmp_path),
        test_status=InformationSourceTestStatus.SUCCESS.value,
        org_id=org_id,
    )
    session.add(source)
    await session.flush()
    await session.commit()

    # A SECOND platform administrator, in a THIRD org, to prove fan-out to
    # every Platform Administrator (not just one).
    from tests.conftest import make_org, make_user

    second_admin_auth = await make_user(
        client, email="secondplatformadmin@example.com", password="TestPassword123!"
    )
    await make_org(
        client,
        cast(dict[str, str], second_admin_auth["headers"]),
        name="Second Platform Admin Org",
        slug="second-platform-admin-org",
    )
    second_admin_id = cast(int, cast(dict[str, object], second_admin_auth["user"])["id"])
    result = await session.execute(select(User).where(User.id == second_admin_id))
    second_admin = result.scalar_one()
    second_admin.is_superuser = True
    second_admin.mfa_enabled = True
    await session.commit()

    resp = await client.post(
        "/api/faqs/generate",
        json={"source_id": source.id},
        headers=_admin_headers(org_with_roles),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["blocked"] is True

    # First platform admin: notification present (fetched in a SEPARATE
    # request — simulating a later login, not a live session at violation
    # time — TS-FR022-2 / TS-FR022-persist).
    notif_resp = await client.get(
        "/api/notifications", headers=_platform_admin_headers(platform_admin_token)
    )
    assert notif_resp.status_code == 200
    notifications = notif_resp.json()
    assert any("no-execute" in n["title"].lower() for n in notifications)
    matching = next(n for n in notifications if "no-execute" in n["title"].lower())
    assert matching["level"] == "error"

    # Second platform admin also received it (fan-out, not a single admin).
    second_headers = cast(dict[str, str], second_admin_auth["headers"])
    second_notif_resp = await client.get("/api/notifications", headers=second_headers)
    assert second_notif_resp.status_code == 200
    assert any("no-execute" in n["title"].lower() for n in second_notif_resp.json())

    # The org-scoped (non-superuser) admin in the SAME org does NOT receive
    # this alert (FR-022 targets Platform Administrator specifically,
    # unlike FR-008's own org-scoped alert).
    org_admin_notif_resp = await client.get(
        "/api/notifications", headers=_admin_headers(org_with_roles)
    )
    assert org_admin_notif_resp.status_code == 200
    assert not any(
        "no-execute" in n["title"].lower() for n in org_admin_notif_resp.json()
    )

    # A corresponding, real audit log entry exists.
    from app.audit.models import AuditLog

    audit_result = await session.execute(
        select(AuditLog).where(AuditLog.action == "assistant.no_execute_violation_detected")
    )
    audit_rows = audit_result.scalars().all()
    assert len(audit_rows) == 1
    assert audit_rows[0].entity_id == source.id
    assert audit_rows[0].entity_type == "information_source"
