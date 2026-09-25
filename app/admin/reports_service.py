"""Admin reporting (chassis v0.10).

Read-only operational counts for the `/admin/reports` page. Scope follows
the admin: a platform admin sees global figures; an org admin sees only
their organization's slice. Every query is parameterized and scoped; this
module never mutates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.auth.models import User
from app.files.models import FileObject
from app.llm.models import LLMProviderKey
from app.notifications.models import Notification
from app.orgs.models import Membership, Organization


@dataclass(frozen=True)
class PlatformReport:
    scope: str  # "platform" or "organization"
    users_total: int
    users_active: int
    orgs_total: int | None  # None for org-scoped reports
    audit_total: int
    audit_top_actions: list[tuple[str, int]] = field(default_factory=list)
    files_count: int = 0
    files_bytes: int = 0
    notifications_total: int = 0
    notifications_unread: int = 0
    llm_keys_active: int = 0


async def gather_report(
    session: AsyncSession, *, org_id: int | None, platform: bool
) -> PlatformReport:
    """Assemble the report. `platform=True` → global; else org-scoped."""
    if platform:
        users_total = (await session.execute(select(func.count(User.id)))).scalar_one()
        users_active = (
            await session.execute(
                select(func.count(User.id)).where(User.is_active.is_(True))
            )
        ).scalar_one()
        orgs_total = (
            await session.execute(select(func.count(Organization.id)))
        ).scalar_one()
    else:
        # Org-scoped: count members of the org.
        users_total = (
            await session.execute(
                select(func.count(Membership.id)).where(Membership.org_id == org_id)
            )
        ).scalar_one()
        users_active = (
            await session.execute(
                select(func.count(User.id))
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.org_id == org_id, User.is_active.is_(True))
            )
        ).scalar_one()
        orgs_total = None

    # Audit events (scoped by organization_id when org-scoped).
    audit_q = select(func.count(AuditLog.id))
    top_q = (
        select(AuditLog.action, func.count(AuditLog.id).label("c"))
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(5)
    )
    if not platform:
        audit_q = audit_q.where(AuditLog.organization_id == org_id)
        top_q = top_q.where(AuditLog.organization_id == org_id)
    audit_total = (await session.execute(audit_q)).scalar_one()
    audit_top = [(row[0], int(row[1])) for row in (await session.execute(top_q)).all()]

    # Files (scoped by organization_id when org-scoped).
    files_q = select(
        func.count(FileObject.id),
        func.coalesce(func.sum(FileObject.size_bytes), 0),
    )
    if not platform:
        files_q = files_q.where(FileObject.organization_id == org_id)
    f_row = (await session.execute(files_q)).one()
    files_count, files_bytes = int(f_row[0]), int(f_row[1])

    # Notifications (scoped by organization_id when org-scoped).
    notif_total_q = select(func.count(Notification.id))
    notif_unread_q = select(func.count(Notification.id)).where(
        Notification.is_read.is_(False)
    )
    if not platform:
        notif_total_q = notif_total_q.where(Notification.organization_id == org_id)
        notif_unread_q = notif_unread_q.where(Notification.organization_id == org_id)
    notifications_total = (await session.execute(notif_total_q)).scalar_one()
    notifications_unread = (await session.execute(notif_unread_q)).scalar_one()

    # Active LLM keys (shared + org for platform; just the org for org-scoped).
    llm_q = select(func.count(LLMProviderKey.id)).where(
        LLMProviderKey.is_active.is_(True)
    )
    if not platform:
        llm_q = llm_q.where(LLMProviderKey.organization_id == org_id)
    llm_keys_active = (await session.execute(llm_q)).scalar_one()

    return PlatformReport(
        scope="platform" if platform else "organization",
        users_total=int(users_total),
        users_active=int(users_active),
        orgs_total=int(orgs_total) if orgs_total is not None else None,
        audit_total=int(audit_total),
        audit_top_actions=audit_top,
        files_count=files_count,
        files_bytes=files_bytes,
        notifications_total=int(notifications_total),
        notifications_unread=int(notifications_unread),
        llm_keys_active=int(llm_keys_active),
    )
