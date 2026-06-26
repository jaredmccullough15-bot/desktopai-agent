from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TenantRecord(BaseModel):
    tenant_id: str
    name: str
    workflows: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive", "draft"] = "active"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class TenantCreateRequest(BaseModel):
    tenant_id: str
    name: str
    workflows: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)
    status: Literal["active", "inactive", "draft"] = "draft"


class TenantUpdateRequest(BaseModel):
    name: str | None = None
    workflows: list[str] | None = None
    systems: list[str] | None = None
    status: Literal["active", "inactive", "draft"] | None = None
