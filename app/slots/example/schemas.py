"""Pydantic v2 schemas for Note endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    """Body for POST /notes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    body: str = Field(default="", max_length=10_000)


class NoteUpdate(BaseModel):
    """Body for PATCH /notes/{id}. Both fields optional."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=10_000)


class NoteRead(BaseModel):
    """Note representation in responses."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    org_id: int
    author_id: int
    title: str
    body: str
    created_at: datetime
    updated_at: datetime
