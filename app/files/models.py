"""File-object ORM model (chassis v0.10).

Metadata for a stored file. Bytes live on disk under `file_storage_dir`
keyed by `storage_key` (a UUID); this row carries the org/owner scoping,
the original filename, content type, size, and a SHA-256 integrity hash.

Org-scoped explicitly (manual `organization_id` filter in the service)
rather than via the TenantScoped mixin, so the service stays testable
without binding the tenant context var.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FileObject(Base):
    __tablename__ = "file_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(127), nullable=False, default="application/octet-stream"
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"FileObject(id={self.id!r}, filename={self.filename!r}, "
            f"org={self.organization_id!r})"
        )
