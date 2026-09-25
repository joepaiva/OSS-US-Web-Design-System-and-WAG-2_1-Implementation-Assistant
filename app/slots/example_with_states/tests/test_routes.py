"""Approval Request route tests — the canonical state-machine test shape.

Covers:
  - Happy path: create (DRAFT) → submit → approve
  - Illegal transitions: DRAFT → APPROVED (skip submitted),
    APPROVED → DRAFT (terminal violation)
  - Terminal-state guards: APPROVED + REJECTED reject all transitions
  - Decision-note required: SUBMITTED → APPROVED without note → 422
  - Cross-org isolation: approver's org cannot see requester's org's data
  - Update on non-DRAFT row → 409
"""

from __future__ import annotations

from typing import cast

import pytest
from httpx import AsyncClient

# ────────────────────────────────────────────────────────────────────────
# Happy path: full lifecycle
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_lifecycle_draft_to_approved(
    client: AsyncClient, requester_token: dict[str, object]
) -> None:
    """DRAFT → SUBMITTED → APPROVED end-to-end."""
    headers = cast(dict[str, str], requester_token["headers"])

    # 1. Create — lands in DRAFT.
    create_resp = await client.post(
        "/approval-requests",
        json={"title": "Hire decision", "body": "Approve senior engineer hire"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["status"] == "draft"
    assert data["submitted_at"] is None
    assert data["decided_at"] is None
    request_id = data["id"]

    # 2. Submit — DRAFT → SUBMITTED, submitted_at stamped.
    submit_resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "submitted"},
        headers=headers,
    )
    assert submit_resp.status_code == 200
    sd = submit_resp.json()
    assert sd["status"] == "submitted"
    assert sd["submitted_at"] is not None

    # 3. Approve — SUBMITTED → APPROVED with decision_note.
    approve_resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "approved", "decision_note": "Strong candidate"},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    ad = approve_resp.json()
    assert ad["status"] == "approved"
    assert ad["decided_at"] is not None
    assert ad["decision_note"] == "Strong candidate"


# ────────────────────────────────────────────────────────────────────────
# Illegal transitions — the gate the chassis state machine enforces
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_draft_to_approved_rejected(
    client: AsyncClient, requester_token: dict[str, object], seeded_draft: dict[str, object]
) -> None:
    """Skipping SUBMITTED is illegal — returns 409 with explanation."""
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_draft["id"]
    resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "approved", "decision_note": "Shortcut!"},
        headers=headers,
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "illegal_transition"
    assert detail["current_status"] == "draft"
    assert detail["attempted_target"] == "approved"


@pytest.mark.asyncio
async def test_approved_to_draft_rejected(
    client: AsyncClient,
    requester_token: dict[str, object],
    seeded_submitted: dict[str, object],
) -> None:
    """Terminal state APPROVED has no outbound transitions."""
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_submitted["id"]
    # First, approve it.
    approve_resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "approved", "decision_note": "OK"},
        headers=headers,
    )
    assert approve_resp.status_code == 200
    # Now try to roll back to draft — terminal-state rejection.
    rollback_resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "draft"},
        headers=headers,
    )
    assert rollback_resp.status_code == 409
    assert rollback_resp.json()["detail"]["current_status"] == "approved"


@pytest.mark.asyncio
async def test_decision_note_required_for_terminal_transition(
    client: AsyncClient,
    requester_token: dict[str, object],
    seeded_submitted: dict[str, object],
) -> None:
    """SUBMITTED → APPROVED without decision_note returns 422."""
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_submitted["id"]
    resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "approved"},  # no decision_note
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "decision_note_required"


# ────────────────────────────────────────────────────────────────────────
# Update guards — non-DRAFT rows reject mutation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_draft_allowed(
    client: AsyncClient, requester_token: dict[str, object], seeded_draft: dict[str, object]
) -> None:
    """PATCH a DRAFT row: title/body update succeeds."""
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_draft["id"]
    resp = await client.patch(
        f"/approval-requests/{request_id}",
        json={"title": "Revised title"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Revised title"


@pytest.mark.asyncio
async def test_update_submitted_rejected(
    client: AsyncClient,
    requester_token: dict[str, object],
    seeded_submitted: dict[str, object],
) -> None:
    """PATCH a SUBMITTED row: rejected with 409 (only DRAFT is editable)."""
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_submitted["id"]
    resp = await client.patch(
        f"/approval-requests/{request_id}",
        json={"title": "Sneaky update"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "illegal_state"


# ────────────────────────────────────────────────────────────────────────
# Cross-org isolation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_org_isolation(
    client: AsyncClient,
    requester_token: dict[str, object],
    approver_token: dict[str, object],
    seeded_draft: dict[str, object],
) -> None:
    """Approver's org cannot see requester's org's approval requests."""
    approver_headers = cast(dict[str, str], approver_token["headers"])
    request_id = seeded_draft["id"]
    resp = await client.get(
        f"/approval-requests/{request_id}", headers=approver_headers
    )
    # Chassis TenantScoped auto-filter scopes by org_id; the request is
    # invisible to a different org. 404 (not 403) to avoid info leakage.
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────
# Auth gate
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_requires_auth(client: AsyncClient) -> None:
    """POST /approval-requests without Authorization returns 401."""
    resp = await client.post(
        "/approval-requests",
        json={"title": "x", "body": "y"},
    )
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_validates_title(
    client: AsyncClient, requester_token: dict[str, object]
) -> None:
    """Empty title → 422 (Pydantic min_length=1)."""
    headers = cast(dict[str, str], requester_token["headers"])
    resp = await client.post(
        "/approval-requests",
        json={"title": "", "body": "anything"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_target_status_rejected(
    client: AsyncClient, requester_token: dict[str, object], seeded_draft: dict[str, object]
) -> None:
    """Unknown target_status in payload → 422 (Pydantic enum validation)."""
    headers = cast(dict[str, str], requester_token["headers"])
    request_id = seeded_draft["id"]
    resp = await client.post(
        f"/approval-requests/{request_id}/transitions",
        json={"target_status": "nonexistent_state"},
        headers=headers,
    )
    assert resp.status_code == 422
