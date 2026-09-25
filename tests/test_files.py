"""File storage tests (chassis v0.10) — service + REST API + org isolation.

Storage is redirected to a per-test tmp dir so nothing is written into the
repo. The dir is injected by monkeypatching the settings the service reads.
"""

from __future__ import annotations

import hashlib

import pytest
from httpx import AsyncClient

import app.files.service as files_service
from app.config import get_settings
from tests.conftest import make_org, make_user


@pytest.fixture(autouse=True)
def _tmp_storage(tmp_path, monkeypatch):
    """Point file storage at a tmp dir for every test in this module."""
    s = get_settings().model_copy(update={"file_storage_dir": str(tmp_path)})
    monkeypatch.setattr(files_service, "get_settings", lambda: s)
    yield


async def _upload(client: AsyncClient, headers, content: bytes, name="hello.txt"):
    return await client.post(
        "/api/files",
        files={"file": (name, content, "text/plain")},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_upload_list_download_delete(client: AsyncClient) -> None:
    u = await make_user(client, email="files1@example.com")
    await make_org(client, u["headers"], name="FOrg", slug="forg")
    content = b"the quick brown fox"

    # Upload.
    up = await _upload(client, u["headers"], content)
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["filename"] == "hello.txt"
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    file_id = body["id"]

    # List.
    ls = await client.get("/api/files", headers=u["headers"])
    assert ls.status_code == 200
    assert any(f["id"] == file_id for f in ls.json())

    # Download returns the exact bytes + integrity header.
    dl = await client.get(f"/api/files/{file_id}/download", headers=u["headers"])
    assert dl.status_code == 200
    assert dl.content == content
    assert dl.headers["X-Content-SHA256"] == body["sha256"]
    assert "hello.txt" in dl.headers["content-disposition"]

    # Delete → gone.
    rm = await client.delete(f"/api/files/{file_id}", headers=u["headers"])
    assert rm.status_code == 204
    dl2 = await client.get(f"/api/files/{file_id}/download", headers=u["headers"])
    assert dl2.status_code == 404


@pytest.mark.asyncio
async def test_org_isolation(client: AsyncClient) -> None:
    a = await make_user(client, email="files-a@example.com")
    await make_org(client, a["headers"], name="AOrg", slug="aorg")
    b = await make_user(client, email="files-b@example.com")
    await make_org(client, b["headers"], name="BOrg", slug="borg")

    up = await _upload(client, a["headers"], b"secret-a")
    fid = up.json()["id"]

    # B cannot list, download, or delete A's file.
    assert all(f["id"] != fid for f in (await client.get("/api/files", headers=b["headers"])).json())
    assert (await client.get(f"/api/files/{fid}/download", headers=b["headers"])).status_code == 404
    assert (await client.delete(f"/api/files/{fid}", headers=b["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_size_cap_enforced(client: AsyncClient, monkeypatch) -> None:
    # Shrink the cap on top of the already-tmp storage dir (autouse fixture).
    s = files_service.get_settings().model_copy(update={"max_upload_bytes": 8})
    monkeypatch.setattr(files_service, "get_settings", lambda: s)

    u = await make_user(client, email="files-big@example.com")
    await make_org(client, u["headers"], name="BigOrg", slug="bigorg")
    up = await _upload(client, u["headers"], b"way-too-many-bytes")
    assert up.status_code == 413


@pytest.mark.asyncio
async def test_upload_requires_org(client: AsyncClient) -> None:
    # User with no org → org-scoped route returns 400 (no org context).
    u = await make_user(client, email="files-noorg@example.com")
    up = await _upload(client, u["headers"], b"x")
    assert up.status_code == 400


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient) -> None:
    up = await _upload(client, {}, b"x")
    assert up.status_code == 401
