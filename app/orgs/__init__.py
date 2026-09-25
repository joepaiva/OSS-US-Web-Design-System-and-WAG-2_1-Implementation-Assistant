"""Multi-tenancy: Organization + Membership + TenantScoped mixin.

The chassis enforces tenant isolation through a SQLAlchemy event listener
that:
  1. Auto-filters any SELECT against tables inheriting TenantScoped with
     `WHERE org_id = :current_org_id` (see `app.db`).
  2. Auto-injects `org_id = :current_org_id` on insert.

Slots ONLY have to inherit `TenantScoped` on their tenant-owned tables;
isolation is then automatic. They never have to remember to filter.
"""
