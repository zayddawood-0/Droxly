"""api.md §3 (/tags) — tasks/remediation-plan.md R2."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str | None


class TagsListResponse(BaseModel):
    items: list[TagResponse]
