"""api.md §4 (/chat) request/response shapes (tasks/remediation-plan.md R4)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ScopeType = Literal["single_document", "multi_document", "workspace"]


class ConversationCreateRequest(BaseModel):
    # Omitted/empty -> "workspace" (api.md §4). Not required.
    document_ids: list[uuid.UUID] = Field(default_factory=list)


class ConversationCreateResponse(BaseModel):
    id: uuid.UUID
    scope_type: ScopeType
    document_ids: list[uuid.UUID]
    title: None
    created_at: datetime


class ConversationListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    scope_type: ScopeType
    document_ids: list[uuid.UUID]
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    total: int
    limit: int
    offset: int


class CitationResponse(BaseModel):
    document_id: uuid.UUID
    page_number: int | None
    snippet: str
    relevance_score: float | None


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[CitationResponse]
    created_at: datetime


class ConversationDetailResponse(ConversationListItem):
    created_at: datetime
    messages: list[MessageResponse]


class ChatMessageRequest(BaseModel):
    # security.md §11.1 boundary validation; the exact 8000-char ceiling is
    # this task's own documented choice (tasks/R4-chat.md "Gap 2") —
    # security.md references a cap without naming a number.
    content: str = Field(min_length=1, max_length=8000)


class StopResponse(BaseModel):
    message_id: uuid.UUID
    status: Literal["stopped"]
