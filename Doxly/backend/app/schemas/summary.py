"""api.md §5 (/summaries) request/response shapes — tasks/remediation-plan.md R7."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SummaryType = Literal["brief", "detailed", "bullet_points"]


class SummaryCreateRequest(BaseModel):
    summary_type: SummaryType


class SummaryCreateResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    summary_type: SummaryType
    status: Literal["processing"]


class SummaryDetailResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    summary_type: str
    status: str
    content: str | None
    created_at: datetime


class SummaryListItem(BaseModel):
    id: uuid.UUID
    summary_type: str
    status: str
    created_at: datetime


class SummaryListResponse(BaseModel):
    items: list[SummaryListItem]
    total: int
    limit: int
    offset: int
