"""api.md §12 (/admin) request/response shapes — tasks/remediation-plan.md R10."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AdminUserListItem(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    plan: str
    status: str
    role: str
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
    total: int
    limit: int
    offset: int


class SystemHealthResponse(BaseModel):
    queue_depth: int
    processing_failure_rate_24h: float
    ai_requests_24h: int
    ai_error_rate_24h: float


class SuspendUserRequest(BaseModel):
    reason: str


class SuspendUserResponse(BaseModel):
    id: uuid.UUID
    status: Literal["suspended"]


class UnsuspendUserResponse(BaseModel):
    id: uuid.UUID
    status: Literal["active"]
