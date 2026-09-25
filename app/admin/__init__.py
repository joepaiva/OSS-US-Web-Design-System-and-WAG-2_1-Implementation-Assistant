"""Chassis admin shell (chassis v0.7).

A built-in, RBAC-gated administration UI that every chassis-deployed app
ships with — no slot code required. Two areas:

  - User Management   — platform admins manage ALL users; org admins manage
                        the members of their current org.
  - Org Management    — platform admins only: list + create organizations.

"Platform admin" = is_superuser OR holder of the chassis-wide `admin` role
(granted via `user_roles`, independent of any org). "Org admin" = holder of
the `admin` role for the current org (via `memberships.role_id`).

The shell is server-rendered (Jinja2 + USWDS, same pattern as app/frontend.py)
and gated by the existing `users:*` / `orgs:*` CorePermissions. Slots never
touch this module; they extend behaviour via their own routers.
"""
