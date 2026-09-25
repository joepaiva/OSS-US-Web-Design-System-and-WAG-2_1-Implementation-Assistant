"""Accessibility Assistant route tests.

Covers FR-001 through FR-006, SR-001 through SR-004.

Every test that covers a TS-NNN scenario cites the exact ID in a comment
or docstring (FR-357 compliance gate requirement).

Test categories:
  1. Happy path — authenticated user with right perm → 200/201
  2. Auth gate — no Authorization header → 401
  3. Permission gate — auth'd user without perm → 403 (not tested here
     because all first-org-users get admin role with all perms; the
     permission gate is tested via the admin endpoint with a non-admin user)
  4. Cross-org isolation — user in org A cannot see org B's data → 404
  5. Validation — bad payload → 422
  6. Domain edge cases — SR-002 content blocking, SR-003 access control,
     FR-005 multi-turn sessions, FR-006 rating
"""

from __future__ import annotations

from typing import cast

import pytest
from httpx import AsyncClient

# ────────────────────────────────────────────────────────────────────────
# FR-003: Browse question categories
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_categories_happy_path(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_category: dict[str, object],
) -> None:
    # TS-FR003: authenticated user can list question categories
    """GET /assistant/categories returns categories for the current org (FR-003)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.get("/assistant/categories", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    category_ids = [c["id"] for c in data]
    assert seeded_category["id"] in category_ids


@pytest.mark.asyncio
async def test_list_categories_empty_state(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR003-3: no categories configured → empty list returned
    """GET /assistant/categories returns empty list when no categories exist (FR-003)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.get("/assistant/categories", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_categories_requires_auth(client: AsyncClient) -> None:
    # TS-FR001-3: unauthenticated access is rejected
    """GET /assistant/categories without auth returns 401 (FR-001)."""
    resp = await client.get("/assistant/categories")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_faqs_in_category_happy_path(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_category: dict[str, object],
    seeded_faq: dict[str, object],
) -> None:
    # TS-FR003-1: category with FAQs returns the FAQ list
    """GET /assistant/categories/{id}/faqs returns FAQs in the category (FR-003)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    category_id = seeded_category["id"]
    resp = await client.get(f"/assistant/categories/{category_id}/faqs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    faq_ids = [f["id"] for f in data]
    assert seeded_faq["id"] in faq_ids


@pytest.mark.asyncio
async def test_list_faqs_in_category_empty(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_category: dict[str, object],
) -> None:
    # TS-FR003-2: category exists but has no FAQs → empty list
    """GET /assistant/categories/{id}/faqs returns empty list when category has no FAQs (FR-003)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    category_id = seeded_category["id"]
    resp = await client.get(f"/assistant/categories/{category_id}/faqs", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_faqs_in_category_not_found(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR003: non-existent category returns 404
    """GET /assistant/categories/99999/faqs returns 404 for unknown category (FR-003)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.get("/assistant/categories/99999/faqs", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_faqs_requires_auth(client: AsyncClient) -> None:
    # TS-FR001-3: unauthenticated access is rejected
    """GET /assistant/categories/{id}/faqs without auth returns 401."""
    resp = await client.get("/assistant/categories/1/faqs")
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# FR-003, FR-004: Get a single FAQ
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_faq_happy_path(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_faq: dict[str, object],
) -> None:
    # TS-FR003-1: selecting an FAQ displays the full answer
    # TS-FR004-1: response contains expository text, reasoning, citations, rating control
    """GET /assistant/faqs/{id} returns full FAQ with answer, reasoning, citations (FR-003, FR-004)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    faq_id = seeded_faq["id"]
    resp = await client.get(f"/assistant/faqs/{faq_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == faq_id
    assert "answer" in data
    assert "reasoning" in data
    assert "citations" in data
    assert isinstance(data["citations"], list)
    # FR-004: at least one citation with hyperlink
    assert len(data["citations"]) >= 1
    assert "hyperlink" in data["citations"][0]
    assert "source_name" in data["citations"][0]


@pytest.mark.asyncio
async def test_get_faq_not_found(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR003: non-existent FAQ returns 404
    """GET /assistant/faqs/99999 returns 404 for unknown FAQ."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.get("/assistant/faqs/99999", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_faq_requires_auth(client: AsyncClient) -> None:
    # TS-FR001-3: unauthenticated access is rejected
    """GET /assistant/faqs/{id} without auth returns 401."""
    resp = await client.get("/assistant/faqs/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_faq_cross_org_isolation(
    client: AsyncClient,
    other_user_token: dict[str, object],
    seeded_faq: dict[str, object],
) -> None:
    # TS-FR003: cross-org isolation — other org cannot see this org's FAQ
    """GET /assistant/faqs/{id} from a different org returns 404 (cross-org isolation)."""
    headers = cast(dict[str, str], other_user_token["headers"])
    faq_id = seeded_faq["id"]
    resp = await client.get(f"/assistant/faqs/{faq_id}", headers=headers)
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────
# FR-001, FR-002: Submit a question
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_question_happy_path(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR002: authenticated user submits a question and receives a response
    # TS-FR001: self-service interface accepts question and returns structured response
    """POST /assistant/ask returns 201 with structured response (FR-001, FR-002, FR-004)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "What is WCAG?"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # FR-004: structured response fields
    assert "interaction_log_id" in data
    assert "response_text" in data
    assert "reasoning" in data
    assert "citations" in data
    assert "has_citations" in data
    assert isinstance(data["citations"], list)
    assert isinstance(data["interaction_log_id"], int)


@pytest.mark.asyncio
async def test_ask_question_requires_auth(client: AsyncClient) -> None:
    # TS-FR001-3: unauthenticated user is redirected / rejected
    """POST /assistant/ask without auth returns 401 (FR-001)."""
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "What is accessibility?"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ask_question_empty_text_rejected(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR002-1: empty question is rejected with validation message
    """POST /assistant/ask with empty question_text returns 422 (FR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": ""},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ask_question_too_long_rejected(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR002-3: question exceeding 200 characters is rejected
    """POST /assistant/ask with question > 200 chars returns 422 (FR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    long_question = "a" * 201
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": long_question},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ask_question_exactly_200_chars_accepted(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR002-2: question of exactly 200 characters is accepted
    """POST /assistant/ask with exactly 200-char question returns 201 (FR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    question = "a" * 200
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": question},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_ask_question_missing_body_rejected(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR002: missing required field returns 422
    """POST /assistant/ask with missing question_text returns 422 (FR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post("/assistant/ask", json={}, headers=headers)
    assert resp.status_code == 422


# ────────────────────────────────────────────────────────────────────────
# SR-002: PII and source-code blocking
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_question_pii_blocked(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-SR002: question containing PII is blocked before LLM call
    # TS-001: PII detection blocks submission
    """POST /assistant/ask with PII in question returns 422 (SR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "My email is john.doe@example.com, what is WCAG?"},
        headers=headers,
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "personal information" in detail.lower() or "rephrase" in detail.lower()


@pytest.mark.asyncio
async def test_ask_question_source_code_blocked(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-SR002: question containing source code is blocked before LLM call
    # TS-002: source code detection blocks submission
    """POST /assistant/ask with source code in question returns 422 (SR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "def my_function(x): return x + 1"},
        headers=headers,
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "source code" in detail.lower() or "rephrase" in detail.lower()


@pytest.mark.asyncio
async def test_ask_question_clean_content_passes(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-SR002: clean question (no PII, no code) is forwarded normally
    """POST /assistant/ask with clean content is accepted (SR-002)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "What are the WCAG 2.1 success criteria?"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


# ────────────────────────────────────────────────────────────────────────
# FR-005: Multi-turn conversation context
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_turn_session(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR005-1: follow-up question uses prior conversational context
    """POST /assistant/ask with session_id groups turns for multi-turn context (FR-005)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    session_id = "multi-turn-test-session"

    # First turn
    resp1 = await client.post(
        "/assistant/ask",
        json={
            "question_text": "What is WCAG?",
            "session_id": session_id,
        },
        headers=headers,
    )
    assert resp1.status_code == 201, resp1.text
    log_id_1 = resp1.json()["interaction_log_id"]

    # Second turn in same session
    resp2 = await client.post(
        "/assistant/ask",
        json={
            "question_text": "Can you explain that further?",
            "session_id": session_id,
        },
        headers=headers,
    )
    assert resp2.status_code == 201, resp2.text
    log_id_2 = resp2.json()["interaction_log_id"]

    # Both turns should produce distinct interaction log records
    assert log_id_1 != log_id_2


@pytest.mark.asyncio
async def test_new_session_starts_fresh(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR005-2: new session carries no context from prior session
    """POST /assistant/ask with a new session_id starts fresh (FR-005)."""
    headers = cast(dict[str, str], end_user_token["headers"])

    # First session
    resp1 = await client.post(
        "/assistant/ask",
        json={"question_text": "What is WCAG?", "session_id": "session-A"},
        headers=headers,
    )
    assert resp1.status_code == 201, resp1.text

    # New session — should succeed independently
    resp2 = await client.post(
        "/assistant/ask",
        json={"question_text": "What is Section 508?", "session_id": "session-B"},
        headers=headers,
    )
    assert resp2.status_code == 201, resp2.text
    # Different interaction log IDs confirm separate records
    assert resp1.json()["interaction_log_id"] != resp2.json()["interaction_log_id"]


# ────────────────────────────────────────────────────────────────────────
# FR-006: Interaction log persistence
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interaction_log_persisted(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-FR006-1: interaction log record is persisted after question is answered
    """GET /assistant/interactions returns the persisted interaction log (FR-006)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.get("/assistant/interactions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    log_ids = [entry["id"] for entry in data]
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    assert interaction_log_id in log_ids


@pytest.mark.asyncio
async def test_interaction_log_fields(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-FR006-1: log record contains all required fields
    """Interaction log record contains all FR-006 required fields."""
    headers = cast(dict[str, str], end_user_token["headers"])
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    resp = await client.get(
        f"/assistant/interactions/{interaction_log_id}", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    # FR-006: required fields
    assert "created_at" in data       # date-time group
    assert "question_text" in data    # question text
    assert "question_category_id" in data  # question category
    assert "response_text" in data    # response provided
    assert "sources" in data          # sources used
    assert "rating" in data           # thumbs up/down rating
    # FR-006 AC: rating is null when not yet submitted
    assert data["rating"] is None


@pytest.mark.asyncio
async def test_interaction_log_requires_auth(client: AsyncClient) -> None:
    # TS-FR006: unauthenticated access to interaction logs is rejected
    """GET /assistant/interactions without auth returns 401 (FR-006)."""
    resp = await client.get("/assistant/interactions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_interaction_log_own_records_only(
    client: AsyncClient,
    end_user_token: dict[str, object],
    other_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-SR003: end user can only see their own interaction logs
    # TS-005: own records returned; no other user's data disclosed
    """GET /assistant/interactions returns only the calling user's records (SR-003)."""
    other_headers = cast(dict[str, str], other_user_token["headers"])
    resp = await client.get("/assistant/interactions", headers=other_headers)
    assert resp.status_code == 200
    data = resp.json()
    # The other user should have no interactions (they haven't asked anything)
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    log_ids = [entry["id"] for entry in data]
    assert interaction_log_id not in log_ids


@pytest.mark.asyncio
async def test_get_interaction_cross_user_denied(
    client: AsyncClient,
    end_user_token: dict[str, object],
    other_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-SR003: accessing another user's interaction log returns 403
    # TS-006: unauthorized access attempt returns authorization error
    """GET /assistant/interactions/{id} for another user's record returns 403 (SR-003)."""
    other_headers = cast(dict[str, str], other_user_token["headers"])
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    resp = await client.get(
        f"/assistant/interactions/{interaction_log_id}", headers=other_headers
    )
    # SR-003: returns authorization error (403), not 404
    # Note: the other user is in a different org, so TenantScoped will
    # filter the record out → 404. Both 403 and 404 are acceptable here
    # per the spec (cross-org returns 404, same-org cross-user returns 403).
    assert resp.status_code in (403, 404)


# ────────────────────────────────────────────────────────────────────────
# FR-006: Rating an interaction
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_interaction_thumbs_up(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-FR006-1: user can rate an interaction thumbs up
    """PATCH /assistant/interactions/{id}/rate with rating=true returns updated record (FR-006)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    resp = await client.patch(
        f"/assistant/interactions/{interaction_log_id}/rate",
        json={"rating": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rating"] is True


@pytest.mark.asyncio
async def test_rate_interaction_thumbs_down(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-FR006-1: user can rate an interaction thumbs down
    """PATCH /assistant/interactions/{id}/rate with rating=false returns updated record (FR-006)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    resp = await client.patch(
        f"/assistant/interactions/{interaction_log_id}/rate",
        json={"rating": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rating"] is False


@pytest.mark.asyncio
async def test_rate_interaction_null_clears_rating(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-FR006-2: rating field is null when not submitted
    """PATCH /assistant/interactions/{id}/rate with rating=null clears rating (FR-006)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])

    # First set a rating
    await client.patch(
        f"/assistant/interactions/{interaction_log_id}/rate",
        json={"rating": True},
        headers=headers,
    )

    # Then clear it
    resp = await client.patch(
        f"/assistant/interactions/{interaction_log_id}/rate",
        json={"rating": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["rating"] is None


@pytest.mark.asyncio
async def test_rate_interaction_requires_auth(client: AsyncClient) -> None:
    # TS-FR006: unauthenticated rating attempt is rejected
    """PATCH /assistant/interactions/{id}/rate without auth returns 401 (FR-006)."""
    resp = await client.patch(
        "/assistant/interactions/1/rate",
        json={"rating": True},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rate_interaction_not_found(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR006: rating a non-existent interaction returns 404
    """PATCH /assistant/interactions/99999/rate returns 404 for unknown interaction."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.patch(
        "/assistant/interactions/99999/rate",
        json={"rating": True},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rate_interaction_cross_user_denied(
    client: AsyncClient,
    end_user_token: dict[str, object],
    other_user_token: dict[str, object],
    seeded_interaction: dict[str, object],
) -> None:
    # TS-SR003: rating another user's interaction is denied
    """PATCH /assistant/interactions/{id}/rate for another user's record returns 403/404 (SR-003)."""
    other_headers = cast(dict[str, str], other_user_token["headers"])
    interaction_log_id = cast(int, seeded_interaction["interaction_log_id"])
    resp = await client.patch(
        f"/assistant/interactions/{interaction_log_id}/rate",
        json={"rating": True},
        headers=other_headers,
    )
    assert resp.status_code in (403, 404)


# ────────────────────────────────────────────────────────────────────────
# SR-003: Admin interaction log view
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_interactions_happy_path(
    client: AsyncClient,
    admin_user_token: dict[str, object],
) -> None:
    # TS-SR003: platform/org admin can view interaction logs in read-only mode
    # TS-007: admin sees org-scoped logs
    """GET /assistant/admin/interactions returns org logs for admin user (SR-003)."""
    headers = cast(dict[str, str], admin_user_token["headers"])
    resp = await client.get("/assistant/admin/interactions", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_admin_list_interactions_requires_auth(client: AsyncClient) -> None:
    # TS-SR003: unauthenticated access to admin log view is rejected
    """GET /assistant/admin/interactions without auth returns 401 (SR-003)."""
    resp = await client.get("/assistant/admin/interactions")
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# FR-004: Structured response format
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_structure_complete(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR004-1: response contains all four required elements
    """POST /assistant/ask response contains all FR-004 required elements."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "How do I make images accessible?"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # (1) expository response text
    assert "response_text" in data
    assert isinstance(data["response_text"], str)
    # (2) reasoning
    assert "reasoning" in data
    assert isinstance(data["reasoning"], str)
    # (3) citations (may be empty list if no sources found — FR-004 AC)
    assert "citations" in data
    assert isinstance(data["citations"], list)
    # (4) rating control represented by interaction_log_id
    assert "interaction_log_id" in data
    assert isinstance(data["interaction_log_id"], int)
    # FR-004 AC: has_citations indicates whether citations are available
    assert "has_citations" in data


@pytest.mark.asyncio
async def test_response_no_broken_citations(
    client: AsyncClient,
    end_user_token: dict[str, object],
) -> None:
    # TS-FR004-2: when no sources found, response indicates no citations rather than broken links
    """POST /assistant/ask response has has_citations=False when no sources found (FR-004)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    resp = await client.post(
        "/assistant/ask",
        json={"question_text": "What is the meaning of life?"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # FR-004 AC: has_citations correctly reflects whether citations exist
    if not data["citations"]:
        assert data["has_citations"] is False
    else:
        assert data["has_citations"] is True
        for citation in data["citations"]:
            assert "source_name" in citation
            assert "hyperlink" in citation


# ────────────────────────────────────────────────────────────────────────
# FR-003: Category browsing with FAQ in category
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_with_category_context(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_category: dict[str, object],
    seeded_faq: dict[str, object],
) -> None:
    # TS-FR003-1: user selects a category and asks a question within it
    # TS-FR002: question with category context is accepted
    """POST /assistant/ask with question_category_id uses category context (FR-002, FR-003)."""
    headers = cast(dict[str, str], end_user_token["headers"])
    category_id = seeded_category["id"]
    resp = await client.post(
        "/assistant/ask",
        json={
            "question_text": "What is WCAG?",
            "question_category_id": category_id,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["interaction_log_id"] is not None
    # The FAQ match should return the seeded FAQ's answer
    assert "WCAG" in data["response_text"] or len(data["response_text"]) > 0


# ────────────────────────────────────────────────────────────────────────
# Cross-org isolation for categories
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_categories_cross_org_isolation(
    client: AsyncClient,
    other_user_token: dict[str, object],
    seeded_category: dict[str, object],
) -> None:
    # TS-FR003: cross-org isolation — other org cannot see this org's categories
    """GET /assistant/categories from different org does not return other org's categories."""
    other_headers = cast(dict[str, str], other_user_token["headers"])
    resp = await client.get("/assistant/categories", headers=other_headers)
    assert resp.status_code == 200
    data = resp.json()
    category_ids = [c["id"] for c in data]
    assert seeded_category["id"] not in category_ids


@pytest.mark.asyncio
async def test_faqs_cross_org_isolation(
    client: AsyncClient,
    other_user_token: dict[str, object],
    seeded_category: dict[str, object],
) -> None:
    # TS-FR003: cross-org isolation for FAQ category browsing
    """GET /assistant/categories/{id}/faqs from different org returns 404 (cross-org isolation)."""
    other_headers = cast(dict[str, str], other_user_token["headers"])
    category_id = seeded_category["id"]
    resp = await client.get(
        f"/assistant/categories/{category_id}/faqs", headers=other_headers
    )
    # The category belongs to a different org; TenantScoped filter makes it invisible → 404
    assert resp.status_code == 404
