"""File storage service (chassis v0.10).

Stores bytes on local disk under `settings.file_storage_dir`, keyed by a
UUID `storage_key`, and records metadata in `file_objects`. All reads/writes
are org-scoped: callers pass the resolved `org_id` and the service refuses
to return another org's file.

Disk layout: `<file_storage_dir>/<storage_key>` — flat, opaque keys (no
user-controlled path component), so traversal is impossible.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.decorator import audited
from app.config import get_settings
from app.files.models import FileObject
from app.logging import get_logger

log = get_logger("files")


class FileError(Exception):
    """Raised for file-service failures the route layer maps to 4xx."""


class FileTooLarge(FileError):
    pass


def _storage_dir() -> Path:
    d = Path(get_settings().file_storage_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


@audited(
    "files.uploaded",
    entity_type="file_object",
    capture_details=lambda f: {
        "filename": f.filename,
        "size_bytes": f.size_bytes,
        "organization_id": f.organization_id,
    },
)
async def store_file(
    session: AsyncSession,
    *,
    org_id: int,
    owner_user_id: int | None,
    filename: str,
    content_type: str,
    data: bytes,
) -> FileObject:
    """Persist `data` to disk + a metadata row. Enforces the size cap."""
    max_bytes = get_settings().max_upload_bytes
    if len(data) > max_bytes:
        raise FileTooLarge(f"file exceeds the {max_bytes}-byte limit")
    if not filename.strip():
        raise FileError("filename is required")

    storage_key = uuid.uuid4().hex
    sha = hashlib.sha256(data).hexdigest()
    path = _storage_dir() / storage_key
    path.write_bytes(data)

    obj = FileObject(
        organization_id=org_id,
        owner_user_id=owner_user_id,
        filename=filename.strip()[:255],
        content_type=(content_type or "application/octet-stream")[:127],
        size_bytes=len(data),
        sha256=sha,
        storage_key=storage_key,
    )
    session.add(obj)
    await session.flush()
    return obj


async def get_file(
    session: AsyncSession, *, file_id: int, org_id: int
) -> FileObject | None:
    """Fetch a file's metadata, scoped to the org. None if absent/foreign."""
    stmt = select(FileObject).where(
        FileObject.id == file_id, FileObject.organization_id == org_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_files(session: AsyncSession, *, org_id: int) -> list[FileObject]:
    stmt = (
        select(FileObject)
        .where(FileObject.organization_id == org_id)
        .order_by(FileObject.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


def read_bytes(obj: FileObject) -> bytes:
    """Read a file's bytes from disk. Raises FileError if missing."""
    path = _storage_dir() / obj.storage_key
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FileError(f"stored file missing: {exc}") from exc


@audited(
    "files.deleted",
    entity_type="file_object",
    capture_details=lambda f: {"filename": f.filename, "file_id": f.id},
)
async def delete_file(session: AsyncSession, obj: FileObject) -> FileObject:
    """Remove the metadata row and best-effort unlink the disk file."""
    path = _storage_dir() / obj.storage_key
    await session.delete(obj)
    await session.flush()
    with contextlib.suppress(OSError):
        os.remove(path)  # disk file already gone; row removal is authoritative
    return obj


async def org_usage(session: AsyncSession, *, org_id: int) -> tuple[int, int]:
    """Return (file_count, total_bytes) for an org."""
    stmt = select(
        func.count(FileObject.id), func.coalesce(func.sum(FileObject.size_bytes), 0)
    ).where(FileObject.organization_id == org_id)
    row = (await session.execute(stmt)).one()
    return int(row[0]), int(row[1])
