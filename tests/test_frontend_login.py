"""Browser-facing (HTML form) login + MFA tests.

Regression coverage for a real bug found live via Chassis Program CP-B.8's
mandatory browser E2E pass: the HTML login form previously posted to
POST /auth/login, the exact (path, method) already claimed by the JSON API
router (app/auth/routes.py), which is included in app/main.py BEFORE the
frontend router. Two APIRouters declaring the identical route is a silent
Starlette routing conflict -- only the first-registered one is ever
reachable -- so the HTML form's handler had been dead code since the
reference chassis was first authored: no real browser could ever log in
through the login page (every submission hit the JSON-only handler and got
a 422, since browsers submit HTML forms as
application/x-www-form-urlencoded, not JSON). No unit or service-level test
had ever caught this, because none of them drove the actual HTTP route the
browser's <form> targets -- exactly the "false green" gap real browser E2E
exists to catch.

The dead handler ALSO unconditionally issued an access token after a
successful password check, skipping the IA-2(1) MFA-challenge branch the
JSON login() endpoint correctly implements -- a real security gap that a
naive "just fix the routing collision" patch would have silently
reintroduced. These tests cover both: the browser form is now reachable at
its own non-colliding path (POST /login), and an MFA-enabled user is
correctly routed through the challenge/verify step (POST /login/mfa) before
receiving a session cookie, exactly like the JSON API path.
"""

from __future__ import annotations

import pyotp
from httpx import AsyncClient

from tests.conftest import make_user


async def _enroll(client: AsyncClient, headers: dict[str, str]) -> str:
    """Full enrollment flow. Returns the raw TOTP secret."""
    start = await client.post("/auth/mfa/enroll", headers=headers)
    assert start.status_code == 200, start.text
    secret = start.json()["secret"]
    code = pyotp.TOTP(secret).now()
    confirm = await client.post(
        "/auth/mfa/enroll/confirm", json={"code": code}, headers=headers
    )
    assert confirm.status_code == 200, confirm.text
    return secret


async def test_json_api_login_still_json_only(client: AsyncClient) -> None:
    """The JSON API's own POST /auth/login is unaffected by the fix -- it
    still requires (and only accepts) a JSON body, exactly as before."""
    await make_user(client, email="jsonlogin@example.com", password="CorrectHorseBattery1!")
    resp = await client.post(
        "/auth/login",
        json={"email": "jsonlogin@example.com", "password": "CorrectHorseBattery1!"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_html_form_post_to_auth_login_still_422(client: AsyncClient) -> None:
    """Regression guard for the OLD (broken) form action: posting
    form-encoded data to /auth/login must still be rejected -- proving the
    fix moved the browser form to a new path rather than making the JSON
    endpoint quietly accept form data (which would be a parsing-ambiguity
    footgun, not a fix)."""
    await make_user(client, email="oldpath@example.com", password="CorrectHorseBattery1!")
    resp = await client.post(
        "/auth/login",
        data={"email": "oldpath@example.com", "password": "CorrectHorseBattery1!"},
    )
    assert resp.status_code == 422


async def test_browser_login_form_success_sets_cookie_and_redirects(
    client: AsyncClient,
) -> None:
    """The actual bug: a real browser's <form action="/login" method="post">
    submission must now succeed, set the session cookie, and redirect to
    the dashboard -- for a user with NO MFA enrolled."""
    await make_user(client, email="formlogin@example.com", password="CorrectHorseBattery1!")
    resp = await client.post(
        "/login",
        data={"email": "formlogin@example.com", "password": "CorrectHorseBattery1!"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert "chassis_access_token" in resp.cookies


async def test_browser_login_cookie_actually_authenticates_dashboard(
    client: AsyncClient,
) -> None:
    """Regression test for a second, compounding bug found live via CP-B.8:
    optional_current_user() (app/frontend.py, shared by /dashboard and the
    entire /admin/* shell) called get_current_user() as a plain function
    rather than through FastAPI's Depends() machinery, so its cookie_token
    parameter was NEVER populated from the request's actual cookie -- only
    an Authorization: Bearer header could ever satisfy it. A real browser
    session (cookie-only, no header) was therefore ALWAYS treated as logged
    out on every HTML page gated by this dependency, even with a perfectly
    valid session cookie -- confirmed live by a fetch()-based /auth/me call
    succeeding with the same cookie a same-page navigation to /dashboard was
    simultaneously rejecting. This test follows the cookie (not the
    Authorization header) through login -> dashboard, exactly as a real
    browser does, so it fails if this regresses."""
    await make_user(client, email="cookieauth@example.com", password="CorrectHorseBattery1!")

    login_resp = await client.post(
        "/login",
        data={"email": "cookieauth@example.com", "password": "CorrectHorseBattery1!"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 303
    assert "chassis_access_token" in login_resp.cookies

    # Deliberately do NOT send an Authorization header -- a real browser
    # never does for a plain page navigation. Only the cookie the client
    # picked up from the login response should carry this request.
    dash_resp = await client.get("/dashboard", follow_redirects=False)
    assert dash_resp.status_code == 200, (
        f"expected the dashboard to render for a cookied session, got "
        f"{dash_resp.status_code} (a redirect back to /auth/login means the "
        f"cookie-only session was not recognized)"
    )
    assert "auth/login" not in dash_resp.headers.get("location", "")


async def test_browser_login_form_wrong_password_rerenders_with_error(
    client: AsyncClient,
) -> None:
    await make_user(client, email="wrongpw@example.com", password="CorrectHorseBattery1!")
    resp = await client.post(
        "/login",
        data={"email": "wrongpw@example.com", "password": "wrong-password-entirely"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "chassis_access_token" not in resp.cookies
    assert "Invalid email or password" in resp.text


async def test_browser_login_form_mfa_enabled_does_not_bypass_challenge(
    client: AsyncClient,
) -> None:
    """The security regression this fix specifically guards against: an
    MFA-enrolled user submitting the HTML login form must NOT receive a
    session cookie from the password step alone -- they must be routed to
    the MFA-verify step first, exactly like the JSON API."""
    u = await make_user(client, email="mfaform@example.com", password="CorrectHorseBattery1!")
    secret = await _enroll(client, u["headers"])

    resp = await client.post(
        "/login",
        data={"email": "mfaform@example.com", "password": "CorrectHorseBattery1!"},
        follow_redirects=False,
    )
    # Not a redirect to /dashboard, not a cookie -- an MFA challenge page.
    assert resp.status_code == 200
    assert "chassis_access_token" not in resp.cookies
    assert "verification code" in resp.text.lower()
    assert 'name="challenge_token"' in resp.text

    # Extract the challenge token the way a real browser would (it's a
    # hidden form field, not a header or cookie).
    import re

    m = re.search(r'name="challenge_token" value="([^"]+)"', resp.text)
    assert m is not None, "challenge_token hidden field not found in rendered MFA page"
    challenge_token = m.group(1)

    code = pyotp.TOTP(secret).now()
    verify = await client.post(
        "/login/mfa",
        data={"challenge_token": challenge_token, "code": code},
        follow_redirects=False,
    )
    assert verify.status_code == 303
    assert verify.headers["location"] == "/dashboard"
    assert "chassis_access_token" in verify.cookies


async def test_browser_mfa_verify_wrong_code_rerenders_challenge_not_login(
    client: AsyncClient,
) -> None:
    u = await make_user(client, email="mfawrong@example.com", password="CorrectHorseBattery1!")
    await _enroll(client, u["headers"])

    resp = await client.post(
        "/login",
        data={"email": "mfawrong@example.com", "password": "CorrectHorseBattery1!"},
        follow_redirects=False,
    )
    import re

    challenge_token = re.search(r'name="challenge_token" value="([^"]+)"', resp.text).group(1)  # type: ignore[union-attr]

    verify = await client.post(
        "/login/mfa",
        data={"challenge_token": challenge_token, "code": "000000"},
        follow_redirects=False,
    )
    assert verify.status_code == 401
    assert "chassis_access_token" not in verify.cookies
    assert "invalid code" in verify.text.lower()
