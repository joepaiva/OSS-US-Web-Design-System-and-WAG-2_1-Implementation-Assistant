"""Pydantic v2 schemas for org/membership endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrgCreate(BaseModel):
    """Body for POST /orgs.

    The creator becomes the first member with the `admin` role and
    `is_default=True`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class OrgRead(BaseModel):
    """Org representation in responses."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    slug: str
    created_at: datetime


class MembershipRead(BaseModel):
    """A single membership row."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    user_id: int
    org_id: int
    role_id: int | None
    is_default: bool
    created_at: datetime


class SwitchOrgRequest(BaseModel):
    """Body for PUT /orgs/me — flip the user's default org."""

    model_config = ConfigDict(extra="forbid")

    org_id: int
