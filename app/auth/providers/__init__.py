"""Auth provider registry — CHASSIS-EXTENSION-POINT: auth-providers.

v0.1.0 ships email/password only. Future versions:
  - v1.1: OAuth (Google, GitHub)
  - v1.2: SAML SSO
  - v1.3: 2FA (TOTP)

The registry pattern below is intentionally simple — providers are
registered by name and dispatched at route time. Real implementations
will add their own routes under `app/auth/providers/<name>/routes.py`
and register here.
"""

from __future__ import annotations

from typing import Protocol


class AuthProvider(Protocol):
    """Provider interface placeholder.

    Future implementations will satisfy this protocol; current v0.1.0
    ships no providers other than the built-in email/password.
    """

    name: str

    async def login(self, *args: object, **kwargs: object) -> str:
        """Return a JWT access token."""
        ...


_registry: dict[str, AuthProvider] = {}


def register(provider: AuthProvider) -> None:
    """Register an auth provider by name. Idempotent."""
    _registry[provider.name] = provider


def get(name: str) -> AuthProvider | None:
    return _registry.get(name)


def all_providers() -> dict[str, AuthProvider]:
    return dict(_registry)
