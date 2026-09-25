"""Slot-local pytest fixtures for the Accessibility Assistant slot.

Follows the HELPER-FIXTURE PATTERN from app/slots/example/tests/conftest.py.

Persona fixtures defined here:
  - end_user_token     — authenticated end user with assistant:ask + assistant:read
  - admin_user_token   — authenticated admin user with assistant:admin
  - other_user_token   — user in a DIFFERENT org (cross-org isolation tests)

Seeded-data fixtures:
  - seeded_category    — a QuestionCategory created via the ORM directly
  - seeded_faq         — a FAQ in seeded_category
  - seeded_interaction — an InteractionLog created via POST /assistant/ask
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_org, make_user  # noqa: F401


# ────────────────────────────────────────────────────────────────────────
# Persona fixtures
# ────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def end_user_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """An authenticated end user in their own org.

    The first user in an org gets the 'admin' role by chassis convention,
    which has all permissions including assistant:ask and assistant:read.
    """
    auth = await make_user(
        client, email="enduser@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], auth["headers"]),
        name="End User Org",
        slug="end-user-org",
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def admin_user_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """An authenticated admin user in their own org.

    Admin users have assistant:admin permission for the interaction log
    admin view (SR-003).
    """
    auth = await make_user(
        client, email="adminuser@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], auth["headers"]),
        name="Admin Org",
        slug="admin-org",
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


@pytest_asyncio.fixture
async def other_user_token(client: AsyncClient) -> AsyncIterator[dict[str, object]]:
    """A user in a DIFFERENT org — used for cross-org isolation tests."""
    auth = await make_user(
        client, email="otheruser@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], auth["headers"]),
        name="Other Org",
        slug="other-org",
    )
    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


# ────────────────────────────────────────────────────────────────────────
# Seeded-data fixtures
# ────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_category(
    client: AsyncClient,
    end_user_token: dict[str, object],
    session: AsyncSession,
) -> dict[str, object]:
    """Create a QuestionCategory directly via ORM for the end_user_token's org.

    We insert directly via ORM because the v0.1 increment does not expose
    a category-creation API route (that's an admin route in a later increment).
    We bind the org context by using the session after the end_user_token
    fixture has established the org.
    """
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import QuestionCategory

    org = cast(dict[str, object], end_user_token["org"])
    org_id = cast(int, org["id"])

    set_current_org_id(org_id)

    category = QuestionCategory(
        name="Accessibility Basics",
        description="Fundamental accessibility questions",
        org_id=org_id,
    )
    session.add(category)
    await session.flush()
    await session.commit()

    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "org_id": category.org_id,
    }


@pytest_asyncio.fixture
async def seeded_faq(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_category: dict[str, object],
    session: AsyncSession,
) -> dict[str, object]:
    """Create a FAQ entry in seeded_category via ORM."""
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import FAQ

    org = cast(dict[str, object], end_user_token["org"])
    org_id = cast(int, org["id"])
    category_id = cast(int, seeded_category["id"])

    set_current_org_id(org_id)

    faq = FAQ(
        org_id=org_id,
        question_category_id=category_id,
        question="What is WCAG?",
        answer="WCAG stands for Web Content Accessibility Guidelines.",
        reasoning="This is a foundational accessibility standard.",
        citations_json='[{"source_name": "W3C", "hyperlink": "https://www.w3.org/WAI/WCAG21/"}]',
    )
    session.add(faq)
    await session.flush()
    await session.commit()

    return {
        "id": faq.id,
        "org_id": faq.org_id,
        "question_category_id": faq.question_category_id,
        "question": faq.question,
        "answer": faq.answer,
        "reasoning": faq.reasoning,
    }


@pytest_asyncio.fixture
async def seeded_interaction(
    client: AsyncClient,
    end_user_token: dict[str, object],
    seeded_category: dict[str, object],
) -> dict[str, object]:
    """Create an interaction log record via POST /assistant/ask.

    Returns the QuestionResponse JSON which includes interaction_log_id.
    """
    headers = cast(dict[str, str], end_user_token["headers"])
    category_id = cast(int, seeded_category["id"])

    resp = await client.post(
        "/assistant/ask",
        json={
            "question_text": "What is accessibility?",
            "question_category_id": category_id,
            "session_id": "test-session-001",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return cast(dict[str, object], resp.json())
