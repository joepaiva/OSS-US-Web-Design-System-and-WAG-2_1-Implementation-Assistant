"""File API schemas (chassis v0.10) — Pydantic v2."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
