"""api.md §7 (/comparisons) request/response shapes — tasks/remediation-plan.md R6."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ComparisonCreateRequest(BaseModel):
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID


class ComparisonCreateResponse(BaseModel):
    id: uuid.UUID
    status: Literal["processing"]


class ComparisonSegment(BaseModel):
    document: Literal["a", "b"]
    page_number: int | None
    excerpt: str


class ComparisonModification(BaseModel):
    change_type: Literal["factual", "numeric", "wording"]
    a_page_number: int | None
    a_excerpt: str
    b_page_number: int | None
    b_excerpt: str
    explanation: str


class ComparisonResult(BaseModel):
    alignment_quality: Literal["high", "medium", "low"]
    message: str | None
    additions: list[ComparisonSegment]
    deletions: list[ComparisonSegment]
    modifications: list[ComparisonModification]


class ComparisonDetailResponse(BaseModel):
    id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    status: str
    result: ComparisonResult | None
    created_at: datetime


class ComparisonListItem(BaseModel):
    id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    status: str
    created_at: datetime


class ComparisonListResponse(BaseModel):
    items: list[ComparisonListItem]
    total: int
    limit: int
    offset: int
