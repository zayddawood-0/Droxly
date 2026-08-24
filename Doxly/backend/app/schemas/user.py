"""api.md §2 (/users) request/response shapes (tasks/remediation-plan.md R1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# decisions.md OQ-07 — Free: 100 MB / 10 documents. Pro: 5 GB / unlimited.
STORAGE_QUOTA_BYTES_FREE = 100 * 1024 * 1024
STORAGE_QUOTA_BYTES_PRO = 5 * 1024 * 1024 * 1024
DOCUMENT_QUOTA_FREE = 10
DOCUMENT_QUOTA_PRO = None  # unlimited (OQ-07)

# api.md §0.7 — AI daily cap by plan, mirrored from core/rate_limit.py's
# same constants so /users/me/usage reports the identical numbers the rate
# limiter actually enforces.
AI_DAILY_CAP_FREE = 30
AI_DAILY_CAP_PRO = 500


class UserResponse(BaseModel):
    """
    Built explicitly in the service layer, not purely via from_attributes
    (skills/backend.md §5) — email_verified is derived from
    `email_verified_at is not None`, and the ORM object has no attribute
    named `email_verified` for from_attributes to pick up automatically.
    model_config is kept for the fields that DO map 1:1 to ORM attributes.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None
    role: str
    plan: str
    email_verified: bool
    storage_used_bytes: int
    created_at: datetime


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    avatar_url: str | None = None
    email: EmailStr | None = None


class UsageResponse(BaseModel):
    plan: str
    storage_used_bytes: int
    storage_quota_bytes: int
    document_count: int
    document_quota: int | None
    ai_requests_today: int
    ai_requests_daily_limit: int


class AccountDeletionRequest(BaseModel):
    """api.md §2 DELETE /users/me — a typed-confirmation pattern
    (tasks/remediation-plan.md R2, the FR-USER-002 half owned by this
    router per R1 §5.1's cascade contract)."""

    confirmation_email: str


class AccountDeletionResponse(BaseModel):
    status: str = "pending_deletion"
    purge_scheduled_after_days: int = 30
