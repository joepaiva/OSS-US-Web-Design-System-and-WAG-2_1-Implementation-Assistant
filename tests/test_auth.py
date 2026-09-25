"""Auth endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import make_user


async def test_register_returns_201_with_token_and_user(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": "CorrectHorseBattery1!",
            "full_name": "Alice",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["full_name"] == "Alice"
    assert body["user"]["is_active"] is True
    assert body["user"]["is_superuser"] is False
    # Password hash MUST NOT leak.
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await make_user(client, email="dup@example.com")
    resp = await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "AnotherPassword1!"},
    )
    assert resp.status_code == 409


async def test_register_short_password_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "x@example.com", "password": "short"},
    )
    assert resp.status_code == 422


# IA-5 (chassis v0.6) — 14-char + 4 character-class complexity
async def test_register_password_missing_uppercase_returns_422(
    client: AsyncClient,
) -> None:
    """IA-5: 14+ chars but no uppercase letter → 422."""
    resp = await client.post(
        "/auth/register",
        json={"email": "ia5a@example.com", "password": "noupperabc12345!"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert any("uppercase" in str(d).lower() for d in body.get("detail", []))


async def test_register_password_missing_digit_returns_422(
    client: AsyncClient,
) -> None:
    """IA-5: 14+ chars but no digit → 422."""
    resp = await client.post(
        "/auth/register",
        json={"email": "ia5b@example.com", "password": "NoDigitHereAtAll!"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert any("digit" in str(d).lower() for d in body.get("detail", []))


async def test_register_password_missing_special_returns_422(
    client: AsyncClient,
) -> None:
    """IA-5: 14+ chars but no special character → 422."""
    resp = await client.post(
        "/auth/register",
        json={"email": "ia5c@example.com", "password": "NoSpecialHere123"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert any("special" in str(d).lower() for d in body.get("detail", []))


async def test_register_password_meets_complexity_returns_201(
    client: AsyncClient,
) -> None:
    """IA-5: 14+ chars + upper + lower + digit + special → 201."""
    resp = await client.post(
        "/auth/register",
        json={"email": "ia5ok@example.com", "password": "AllFourClasses1!"},
    )
    assert resp.status_code == 201


async def test_login_correct_credentials_returns_200(client: AsyncClient) -> None:
    await make_user(client, email="login@example.com", password="MyPassword123!")
    resp = await client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "MyPassword123!"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await make_user(client, email="login2@example.com", password="RealPassword1!")
    resp = await client.post(
        "/auth/login",
        json={"email": "login2@example.com", "password": "WrongPassword1!"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_email_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "TestPassword123!"},
    )
    # Same 401 as wrong-password to prevent email enumeration.
    assert resp.status_code == 401


async def test_me_with_bearer_token_returns_user(client: AsyncClient) -> None:
    u = await make_user(client, email="me@example.com")
    resp = await client.get("/auth/me", headers=u["headers"])  # type: ignore[arg-type]
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


async def test_me_without_auth_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.real.jwt"}
    )
    assert resp.status_code == 401


async def test_logout_returns_204(client: AsyncClient) -> None:
    resp = await client.post("/auth/logout")
    assert resp.status_code == 204
