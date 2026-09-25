"""File API routes (chassis v0.10) — org-scoped upload/list/download/delete.

Every route requires an authenticated user AND an org context (`CurrentOrg`),
so files are isolated per tenant: a caller can only see/fetch/delete files
belonging to their current organization. No special RBAC permission — any
org member manages their org's files.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, UploadFile, status

from app.db import SessionDep
from app.deps import CurrentOrg, CurrentUser
from app.files.schemas import FileRead
from app.files.service import (
    FileError,
    FileTooLarge,
    delete_file,
    get_file,
    list_files,
    read_bytes,
    store_file,
)
from app.logging import get_logger

log = get_logger("files.routes")

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("", response_model=list[FileRead])
async def list_(
    user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> list[FileRead]:
    files = await list_files(session, org_id=org.id)
    return [FileRead.model_validate(f) for f in files]


@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    user: CurrentUser,
    org: CurrentOrg,
    session: SessionDep,
) -> FileRead:
    data = await file.read()
    try:
        obj = await store_file(
            session,
            org_id=org.id,
            owner_user_id=user.id,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    except FileTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc
    except FileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    log.info("files.uploaded", file_id=obj.id, org_id=org.id, owner_id=user.id)
    return FileRead.model_validate(obj)


@router.get("/{file_id}/download")
async def download(
    file_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> Response:
    obj = await get_file(session, file_id=file_id, org_id=org.id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )
    try:
        data = read_bytes(obj)
    except FileError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="File contents unavailable."
        ) from exc
    return Response(
        content=data,
        media_type=obj.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{obj.filename}"',
            "X-Content-SHA256": obj.sha256,
        },
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    file_id: int, user: CurrentUser, org: CurrentOrg, session: SessionDep
) -> Response:
    obj = await get_file(session, file_id=file_id, org_id=org.id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )
    await delete_file(session, obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
