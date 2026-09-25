"""Slot-local pytest fixtures for the Accessibility Assistant slot.

Follows the HELPER-FIXTURE PATTERN from app/slots/example/tests/conftest.py.

Persona fixtures defined here (v0.1):
  - end_user_token     — authenticated end user with assistant:ask + assistant:read
  - admin_user_token   — authenticated admin user with assistant:admin
  - other_user_token   — user in a DIFFERENT org (cross-org isolation tests)

Seeded-data fixtures (v0.1):
  - seeded_category    — a QuestionCategory created via the ORM directly
  - seeded_faq         — a FAQ in seeded_category
  - seeded_interaction — an InteractionLog created via POST /assistant/ask

v0.2 additions (FR-007 through FR-017):
  - org_with_roles          — ONE org with three real personas sharing it:
                              admin (org creator), end_user (chassis "user"
                              role membership — genuinely NON-admin, unlike
                              v0.1's end_user_token), and content_manager
                              (slot-provisioned "content_manager" role).
                              This is what makes a real 403 test possible —
                              v0.1's fixtures never had a non-admin persona
                              at all (see that file's own test_routes.py
                              docstring).
  - seeded_source_category  — an InformationSourceCategory in org_with_roles
  - seeded_information_source — an InformationSource in org_with_roles

v0.3 additions (FR-017 through FR-022, SR-005..SR-007, NFR-001):
  - platform_admin_token    — a GENUINE Platform Administrator: is_superuser=True
                              + mfa_enabled=True (mirrors tests/test_admin.py's own
                              `_promote_to_superuser` precedent), belonging to its
                              OWN, separate org. This is what makes FR-020's
                              (share) and FR-021's (cross-org log view) real
                              Platform-vs-Organization-Administrator distinction
                              testable — `org_with_roles["admin"]` is only an
                              org-scoped admin (per-org Membership role), never a
                              real superuser (see that fixture's own docstring).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
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


# ════════════════════════════════════════════════════════════════════════
# v0.2 additions (FR-007 through FR-017)
# ════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def org_with_roles(
    client: AsyncClient, session: AsyncSession
) -> AsyncIterator[dict[str, object]]:
    """One org with three real personas: admin, end_user, content_manager.

    Unlike v0.1's end_user_token (secretly an org-creating admin per the
    chassis's "first user gets the admin role" convention — see this
    file's own module docstring), `end_user` here holds the chassis's
    genuinely non-privileged "user" role via a direct Membership row, and
    `content_manager` holds this slot's own provisioned "content_manager"
    role (app.slots.accessibility_assistant.service.ensure_content_manager_role).
    This is what makes a real FR-010/FR-015/FR-017 403 test possible.

    Also grants assistant:read/assistant:ask to the "user" role here (test
    setup mirroring service._ensure_baseline_role_grants — see that
    function's docstring for why production needs the same grant and why
    a lazy, request-time grant can't reliably run before the FIRST
    request's own permission check).
    """
    from sqlalchemy import select

    from app.db import set_current_org_id
    from app.orgs.models import Membership
    from app.rbac.models import Role
    from app.slots.accessibility_assistant.service import (
        _ensure_baseline_role_grants,
        ensure_content_manager_role,
    )

    admin_auth = await make_user(
        client, email="orgadmin@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], admin_auth["headers"]),
        name="Multi-Role Org",
        slug="multi-role-org",
    )
    org_id = cast(int, org["id"])

    end_user_auth = await make_user(
        client, email="plainenduser@example.com", password="TestPassword123!"
    )
    cm_auth = await make_user(
        client, email="contentmanager@example.com", password="TestPassword123!"
    )

    set_current_org_id(org_id)
    await _ensure_baseline_role_grants(session)
    user_role = (
        await session.execute(select(Role).where(Role.name == "user"))
    ).scalar_one()
    cm_role = await ensure_content_manager_role(session)

    end_user_id = cast(int, cast(dict[str, object], end_user_auth["user"])["id"])
    cm_id = cast(int, cast(dict[str, object], cm_auth["user"])["id"])

    session.add_all(
        [
            Membership(
                user_id=end_user_id, org_id=org_id, role_id=user_role.id, is_default=True
            ),
            Membership(user_id=cm_id, org_id=org_id, role_id=cm_role.id, is_default=True),
        ]
    )
    await session.flush()
    await session.commit()

    yield {
        "org": org,
        "admin": admin_auth,
        "end_user": end_user_auth,
        "content_manager": cm_auth,
    }


@pytest_asyncio.fixture
async def seeded_source_category(
    client: AsyncClient, org_with_roles: dict[str, object], session: AsyncSession
) -> dict[str, object]:
    """Create an InformationSourceCategory directly via ORM (FR-010)."""
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import InformationSourceCategory

    org = cast(dict[str, object], org_with_roles["org"])
    org_id = cast(int, org["id"])
    set_current_org_id(org_id)

    category = InformationSourceCategory(
        name="Code Repositories", description="Source-code repos", org_id=org_id
    )
    session.add(category)
    await session.flush()
    await session.commit()
    return {"id": category.id, "name": category.name, "org_id": category.org_id}


@pytest_asyncio.fixture
async def seeded_information_source(
    client: AsyncClient,
    org_with_roles: dict[str, object],
    seeded_source_category: dict[str, object],
    session: AsyncSession,
) -> dict[str, object]:
    """Create an InformationSource directly via ORM (FR-011)."""
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import (
        InformationSource,
        InformationSourceTestStatus,
        InformationSourceType,
    )

    org = cast(dict[str, object], org_with_roles["org"])
    org_id = cast(int, org["id"])
    category_id = cast(int, seeded_source_category["id"])
    set_current_org_id(org_id)

    source = InformationSource(
        category_id=category_id,
        name="Main Docs Repo",
        source_type=InformationSourceType.GITHUB_ONLINE_REPO.value,
        github_url="https://github.com/example/docs",
        test_status=InformationSourceTestStatus.SUCCESS.value,
        org_id=org_id,
    )
    session.add(source)
    await session.flush()
    await session.commit()
    return {"id": source.id, "name": source.name, "category_id": category_id, "org_id": org_id}


# ════════════════════════════════════════════════════════════════════════
# v0.3 additions (FR-017 through FR-022, SR-005..SR-007, NFR-001)
# ════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def platform_admin_token(
    client: AsyncClient, session: AsyncSession
) -> AsyncIterator[dict[str, object]]:
    """A genuine Platform Administrator: is_superuser=True + mfa_enabled=True
    (mirrors tests/test_admin.py's own `_promote_to_superuser` precedent),
    with its OWN separate org so it has a valid default-org context while
    still being able to act across every other org (FR-020's share action,
    FR-021's cross-org log view, FR-022's alert recipients all key off
    `user.is_superuser` — see service.py)."""
    from app.auth.models import User

    auth = await make_user(
        client, email="platformadmin@example.com", password="TestPassword123!"
    )
    org = await make_org(
        client,
        cast(dict[str, str], auth["headers"]),
        name="Platform Admin Org",
        slug="platform-admin-org",
    )
    user_id = cast(int, cast(dict[str, object], auth["user"])["id"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.is_superuser = True
    user.mfa_enabled = True
    await session.commit()

    yield {
        "token": auth["token"],
        "headers": auth["headers"],
        "user": auth["user"],
        "org": org,
    }


# ════════════════════════════════════════════════════════════════════════
# v0.4 additions (CON-001..CON-006, FR-025..FR-027, NFR-002)
# ════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def platform_admin_source_category(
    client: AsyncClient,
    platform_admin_token: dict[str, object],
    session: AsyncSession,
) -> dict[str, object]:
    """An InformationSourceCategory created by a genuine Platform
    Administrator, in the platform admin's OWN org — i.e. FR-027-eligible
    for platform-level sharing (`creator_role_snapshot == "platform_admin"`).
    Distinct from `seeded_source_category`, which is created by an ordinary
    org admin and is therefore FR-027-INELIGIBLE (used as that negative
    test case in test_v0_4.py)."""
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import InformationSourceCategory

    org = cast(dict[str, object], platform_admin_token["org"])
    org_id = cast(int, org["id"])
    user_id = cast(int, cast(dict[str, object], platform_admin_token["user"])["id"])
    set_current_org_id(org_id)

    category = InformationSourceCategory(
        name="Platform Admin Source Category",
        org_id=org_id,
        created_by_user_id=user_id,
        creator_role_snapshot="platform_admin",
    )
    session.add(category)
    await session.flush()
    await session.commit()
    return {"id": category.id, "name": category.name, "org_id": org_id}


@pytest_asyncio.fixture
async def platform_admin_information_source(
    client: AsyncClient,
    platform_admin_token: dict[str, object],
    platform_admin_source_category: dict[str, object],
    session: AsyncSession,
) -> dict[str, object]:
    """An InformationSource created by a genuine Platform Administrator, in
    the platform admin's OWN org — FR-027-eligible for platform-level
    sharing. Distinct from `seeded_information_source` (org-admin-created,
    FR-027-ineligible)."""
    from app.db import set_current_org_id
    from app.slots.accessibility_assistant.models import (
        InformationSource,
        InformationSourceTestStatus,
        InformationSourceType,
    )

    org_id = cast(int, platform_admin_source_category["org_id"])
    user_id = cast(int, cast(dict[str, object], platform_admin_token["user"])["id"])
    category_id = cast(int, platform_admin_source_category["id"])
    set_current_org_id(org_id)

    source = InformationSource(
        category_id=category_id,
        name="Platform Admin Source",
        source_type=InformationSourceType.GITHUB_ONLINE_REPO.value,
        github_url="https://github.com/example/platform-admin-repo",
        test_status=InformationSourceTestStatus.SUCCESS.value,
        org_id=org_id,
        created_by_user_id=user_id,
        creator_role_snapshot="platform_admin",
    )
    session.add(source)
    await session.flush()
    await session.commit()
    return {
        "id": source.id,
        "name": source.name,
        "category_id": category_id,
        "org_id": org_id,
    }
