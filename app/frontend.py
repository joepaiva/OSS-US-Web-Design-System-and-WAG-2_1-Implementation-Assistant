"""Chassis frontend wiring — USWDS 3.x + Stripe-aesthetic admin shell.

This module:
  1. Mounts /static/ to serve `app/static/` files (CSS, images).
  2. Configures Jinja2Templates against `app/templates/`.
  3. Registers a small set of HTML routes for the admin shell:
       - GET  /                — landing → /dashboard if logged in, else /auth/login
       - GET  /dashboard       — sample dashboard (slot authors override)
       - GET  /auth/login      — login form
       - POST /auth/login      — handles login, sets cookie, redirects
       - GET  /auth/register   — registration form
       - POST /auth/register   — handles registration, redirects
       - POST /auth/logout     — clears cookie, redirects to /auth/login
       - GET  /account         — current user profile + logout button

The JSON API endpoints at /auth/login (POST), /auth/register (POST), etc.
continue to exist alongside these HTML routes. Slot authors who want a
pure-API deployment can simply not include `frontend_router` in main.py.

Slot authors who want to extend the admin shell (e.g. add an
/account/settings page) inherit base.html, add their own Jinja2 templates
under app/templates/, and add the routes here.

Section 508 + accessibility: USWDS components shipped via CDN retain
their accessible defaults; stripe-overrides.css preserves focus-visible
outlines at AAA-grade contrast.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.auth import mfa
from app.auth.mfa import InvalidChallengeToken, InvalidMFACode, MFANotEnrolled
from app.auth.models import User
from app.auth.schemas import UserRegister
from app.auth.service import (
    AccountLocked,
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate,
    get_user_by_id,
    issue_access_token,
    register_user,
)
from app.config import get_settings
from app.db import SessionDep
from app.deps import ACCESS_TOKEN_COOKIE, get_current_user

CHASSIS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = CHASSIS_DIR / "templates"
STATIC_DIR = CHASSIS_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def mount_static(app: Any) -> None:
    """Mount /static/ on the FastAPI app. Called from main.py.

    Idempotent: safe to call multiple times during test setup.
    """
    if STATIC_DIR.exists():
        # Already mounted (test setup re-uses the app instance) -> RuntimeError, suppressed.
        with contextlib.suppress(RuntimeError):
            app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def optional_current_user(
    request: Request,
    session: SessionDep,
) -> User | None:
    """Same as get_current_user but returns None instead of raising on
    missing/invalid credentials. Used by the HTML routes which need to
    distinguish "not logged in → redirect to login" from "auth error".

    CP-B.8 fix (Chassis Program, 2026-09-02): get_current_user's third
    parameter (`cookie_token`) is only ever auto-populated from the request's
    Cookie header when FastAPI's own Depends() machinery calls the function
    -- that resolution is tied to FastAPI's dependency-injection path, not to
    calling the function directly. This helper was calling get_current_user
    as a PLAIN function (`await get_current_user(request=request,
    session=session)`), so `cookie_token` always kept its literal Python
    default of None, no matter what cookie the browser actually sent. Only
    an Authorization: Bearer header (which no real browser page navigation
    ever sends) could ever succeed here -- so every HTML page gated by this
    dependency (the dashboard, the whole /admin/* shell it's shared with,
    etc.) always treated a real, validly-cookied browser session as logged
    out. Found live via CP-B.8's real Playwright E2E pass: a fetch()-based
    call to /auth/me (which DOES go through FastAPI's Depends() machinery)
    succeeded with the same cookie that a same-page navigation to /dashboard
    was simultaneously rejecting. Inherited unchanged from the reference
    chassis (chassis/python-fastapi) -- flagged separately for Joe, not
    fixed there per this program's package-independence rule. Fix: resolve
    the cookie manually here and pass it through explicitly.
    """
    try:
        cookie_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        return await get_current_user(
            request=request, session=session, cookie_token=cookie_token
        )
    except Exception:
        return None


def _common_context(request: Request, user: User | None) -> dict[str, Any]:
    """Shared template context. Slot authors can pass these keys into
    their own templates extending base.html so the header renders right.
    """
    settings = get_settings()
    return {
        "request": request,
        "current_user": user,
        # `app_name` and `is_gov_app` not yet promoted to Settings columns;
        # templates default them via | default(...) filters. When customers
        # want to override, they can subclass Settings or set env vars.
        "app_name": "Application",
        "settings": {
            "is_gov_app": False,
            # AC-8 (chassis v0.6): system use notification banner. When
            # empty, the login template suppresses the banner div entirely.
            "system_use_notification": settings.system_use_notification,
        },
        "form_data": {},
        "errors": {},
        "flash": None,
    }


def _cookie_max_age() -> int:
    """Cookie max-age in seconds, derived from chassis Settings.

    Settings exposes `jwt_access_token_ttl_minutes` (config.py:86) — we
    multiply by 60 here so the cookie expiry matches the JWT expiry.
    """
    return get_settings().jwt_access_token_ttl_minutes * 60


frontend_router = APIRouter(tags=["frontend"], include_in_schema=False)


@frontend_router.get("/", response_class=HTMLResponse)
async def landing(
    user: User | None = Depends(optional_current_user),
) -> Response:
    if user is None:
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@frontend_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, user: User | None = Depends(optional_current_user)
) -> Response:
    if user is None:
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    ctx = _common_context(request, user)
    # Default stats / activity — slot authors override this route to
    # populate with real data.
    ctx["stats"] = {
        "total_approvals": 0,
        "recent_approvals": 0,
        "pending": 0,
        "active_users": 1,
        "orgs": 1,
    }
    ctx["recent_activity"] = []
    return templates.TemplateResponse(request, "dashboard/index.html", ctx)


@frontend_router.get("/auth/login", response_class=HTMLResponse)
async def login_page(
    request: Request, user: User | None = Depends(optional_current_user)
) -> Response:
    if user is not None:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "auth/login.html", _common_context(request, None))


def _set_browser_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="chassis_access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=_cookie_max_age(),
        path="/",
    )


# CP-B.8 fix (Chassis Program, 2026-09-02): this handler used to be registered
# at POST /auth/login — the exact same (path, method) already claimed by the
# JSON API's `auth_router` (app/auth/routes.py), which is included in
# app/main.py BEFORE this router. Two APIRouters both declaring the same
# route is a silent routing conflict in Starlette/FastAPI: only the
# first-registered one is ever reachable, so this handler had been dead code
# since the reference chassis was first authored — no real browser could log
# in through the HTML login form at all (it always hit the JSON-only handler
# and got a 422). Found live via CP-B.8's real Playwright E2E pass (the
# mandatory browser-verification gate, not a unit test — unit/service tests
# never exercise routing collisions like this). Fixed by giving the
# browser-facing form its own, non-colliding path (`/login`) instead of
# reusing the JSON API's path. This handler ALSO previously skipped the
# IA-2(1) MFA check entirely (it called authenticate() then issued a token
# unconditionally) — a real security gap for the FISMA-Moderate MFA mandate
# that a naive "just fix the routing" patch would have silently reintroduced
# if it had simply made this path reachable without also closing the gap
# below.
@frontend_router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    ctx = _common_context(request, None)
    ctx["form_data"] = {"email": email}
    try:
        user = await authenticate(session, email=email, password=password)
    except AccountLocked as exc:
        # AC-7 (chassis v0.6): identical UI message to InvalidCredentials
        # (anti-enumeration), but include the retry timing so legit users
        # see a useful banner.
        retry_min = max(1, exc.retry_after_seconds // 60)
        ctx["errors"] = {
            "_form": [
                f"Invalid email or password. (If this account is locked due to failed attempts, try again in about {retry_min} minute(s).)"
            ]
        }
        return templates.TemplateResponse(request, "auth/login.html", ctx, status_code=401)
    except InvalidCredentials:
        ctx["errors"] = {"_form": ["Invalid email or password."]}
        return templates.TemplateResponse(request, "auth/login.html", ctx, status_code=401)

    if user.mfa_enabled:
        # IA-2(1): mirror the JSON API's login() branch exactly -- an
        # MFA-enabled user does NOT get a usable token yet, only a
        # short-lived challenge they must complete via /login/mfa.
        challenge_token = mfa.issue_challenge_token(user)
        mfa_ctx = _common_context(request, None)
        mfa_ctx["challenge_token"] = challenge_token
        return templates.TemplateResponse(request, "auth/mfa_verify.html", mfa_ctx)

    token = issue_access_token(user)
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_browser_cookie(response, token)
    return response


@frontend_router.post("/login/mfa", response_class=HTMLResponse)
async def login_mfa_submit(
    request: Request,
    session: SessionDep,
    challenge_token: str = Form(...),
    code: str = Form(...),
) -> Response:
    """Browser-facing completion of an MFA challenge issued by login_submit.
    Distinct path from the JSON API's POST /auth/mfa/verify for the same
    routing-collision reason documented on login_submit above."""
    ctx = _common_context(request, None)
    ctx["challenge_token"] = challenge_token

    try:
        user_id = mfa.decode_challenge_token(challenge_token)
    except InvalidChallengeToken:
        ctx["errors"] = {"_form": ["Your sign-in attempt expired. Please sign in again."]}
        return templates.TemplateResponse(request, "auth/login.html", ctx, status_code=401)

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        ctx["errors"] = {"_form": ["Your sign-in attempt expired. Please sign in again."]}
        return templates.TemplateResponse(request, "auth/login.html", ctx, status_code=401)

    try:
        await mfa.verify_login_code(session, user, code)
    except (MFANotEnrolled, InvalidMFACode):
        ctx["errors"] = {"_form": ["Invalid code. Please try again."]}
        return templates.TemplateResponse(request, "auth/mfa_verify.html", ctx, status_code=401)

    token = issue_access_token(user)
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_browser_cookie(response, token)
    return response


@frontend_router.get("/auth/register", response_class=HTMLResponse)
async def register_page(
    request: Request, user: User | None = Depends(optional_current_user)
) -> Response:
    if user is not None:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "auth/register.html", _common_context(request, None)
    )


@frontend_router.post("/auth/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
) -> Response:
    ctx = _common_context(request, None)
    ctx["form_data"] = {"email": email, "full_name": full_name}
    try:
        payload = UserRegister(
            email=email,
            password=password,
            full_name=full_name or None,
        )
    except ValidationError as exc:
        # IA-5 (chassis v0.6): Pydantic ValidationError carries per-field
        # errors. Translate to the template's errors-dict shape so the
        # USWDS form macros render them on the offending input.
        field_errors: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = err.get("loc") or ()
            field = str(loc[0]) if loc else "_form"
            field_errors.setdefault(field, []).append(str(err.get("msg", "Invalid value.")))
        ctx["errors"] = field_errors
        return templates.TemplateResponse(
            request, "auth/register.html", ctx, status_code=422
        )
    try:
        user = await register_user(session, payload)
    except EmailAlreadyRegistered:
        ctx["errors"] = {"email": ["An account with this email already exists."]}
        return templates.TemplateResponse(
            request, "auth/register.html", ctx, status_code=409
        )

    token = issue_access_token(user)
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    settings = get_settings()
    response.set_cookie(
        key="chassis_access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=_cookie_max_age(),
        path="/",
    )
    return response


@frontend_router.post("/auth/logout")
async def logout() -> Response:
    response = RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("chassis_access_token", path="/")
    return response


@frontend_router.get("/account", response_class=HTMLResponse)
async def account(
    request: Request, user: User | None = Depends(optional_current_user)
) -> Response:
    if user is None:
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "auth/account.html", _common_context(request, user))
