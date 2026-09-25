"""Org endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import make_org, make_user


async def test_list_orgs_empty_for_new_user(client: AsyncClient) -> None:
    u = await make_user(client, email="solo@example.com")
    resp = await client.get("/orgs", headers=u["headers"])  # type: ignore[arg-type]
    assert resp.status_code == 200
    assert resp.json() == []


async def test_default_org_is_null_when_no_memberships(client: AsyncClient) -> None:
    u = await make_user(client, email="solo2@example.com")
    resp = await client.get("/orgs/me", headers=u["headers"])  # type: ignore[arg-type]
    assert resp.status_code == 200
    assert resp.json() is None


async def test_create_org_makes_creator_default(client: AsyncClient) -> None:
    u = await make_user(client, email="creator@example.com")
    org = await make_org(client, u["headers"], name="Acme", slug="acme")  # type: ignore[arg-type]
    assert org["slug"] == "acme"

    me_resp = await client.get("/orgs/me", headers=u["headers"])  # type: ignore[arg-type]
    assert me_resp.json()["slug"] == "acme"


async def test_create_org_duplicate_slug_returns_409(client: AsyncClient) -> None:
    u = await make_user(client, email="dup-org@example.com")
    await make_org(client, u["headers"], slug="taken")  # type: ignore[arg-type]
    resp = await client.post(
        "/orgs",
        json={"name": "Other", "slug": "taken"},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    assert resp.status_code == 409


async def test_create_org_invalid_slug_returns_422(client: AsyncClient) -> None:
    u = await make_user(client, email="bad-slug@example.com")
    resp = await client.post(
        "/orgs",
        json={"name": "X", "slug": "BAD SLUG!"},
        headers=u["headers"],  # type: ignore[arg-type]
    )
    assert resp.status_code == 422


async def test_switch_default_org_to_owned(client: AsyncClient) -> None:
    u = await make_user(client, email="switcher@example.com")
    await make_org(client, u["headers"], name="A", slug="orga")  # type: ignore[arg-type]
    org_b = await make_org(client, u["headers"], name="B", slug="orgb")  # type: ignore[arg-type]

    resp = await client.put(
        "/orgs/me", json={"org_id": org_b["id"]}, headers=u["headers"]  # type: ignore[arg-type]
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == "orgb"

    me_resp = await client.get("/orgs/me", headers=u["headers"])  # type: ignore[arg-type]
    assert me_resp.json()["slug"] == "orgb"


async def test_switch_to_org_not_a_member_returns_403(client: AsyncClient) -> None:
    u = await make_user(client, email="notmem@example.com")
    await make_org(client, u["headers"], slug="myown")  # type: ignore[arg-type]
    resp = await client.put(
        "/orgs/me", json={"org_id": 99999}, headers=u["headers"]  # type: ignore[arg-type]
    )
    assert resp.status_code == 403
