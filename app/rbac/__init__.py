"""RBAC — role-based access control.

Two seeded roles ship with v0.1.0:
  - admin: holds every permission, including future ones added by slots.
  - user:  read-only on owned resources.

Permissions are colon-scoped strings (e.g. `users:read`, `audit:read`).
Slots register their own permissions at the CHASSIS-EXTENSION-POINT in
`permissions.py`.
"""
