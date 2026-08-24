"""api.md §3 (/documents) request/response shapes (tasks/remediation-plan.md R2)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.tag import TagResponse

SUPPORTED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
    }
)

DOCUMENT_STATUSES = frozenset(
    {"queued", "extracting", "chunking", "embedding", "ready", "failed"}
)


class PresignRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=500)
    # NOT validated against SUPPORTED_MIME_TYPES here — api.md assigns
    # "unsupported_mime_type" as a specific error code that only a raised
    # DoxlyError (app/errors.py's UnsupportedMimeTypeError, in
    # DocumentService.presign_upload) can produce; a Pydantic
    # field_validator would instead surface as R1's generic
    # `validation_error` (see UnsupportedMimeTypeError's own docstring for
    # the full reasoning).
    mime_type: str
    size_bytes: int = Field(gt=0)


class PresignResponse(BaseModel):
    document_id: uuid.UUID
    upload_url: str
    upload_method: Literal["PUT"]
    upload_headers: dict[str, str]
    expires_in: int


class ConfirmResponse(BaseModel):
    id: uuid.UUID
    status: Literal["queued"]


class DocumentListItem(BaseModel):
    id: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int
    status: str
    page_count: int | None
    tags: list[TagResponse]
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentListItem):
    checksum_sha256: str
    processing_error: str | None
    extracted_text_available: bool


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


class DocumentUpdateRequest(BaseModel):
    file_name: str | None = Field(default=None, min_length=1, max_length=500)
    tag_ids: list[uuid.UUID] | None = None


class DownloadResponse(BaseModel):
    download_url: str
    expires_in: int


class StatusResponse(BaseModel):
    status: str
    processing_error: str | None


class ContentPagesResponse(BaseModel):
    pages: list[dict]


class ContentTextResponse(BaseModel):
    text: str


class ContentRowsResponse(BaseModel):
    rows: list[dict]
    columns: list[str]


class BulkActionRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1)
    action: Literal["delete", "tag"]
    # validate_default=True: without it, Pydantic v2 skips field_validators
    # entirely when a field is omitted from the request body and falls back
    # to its default — meaning `{"action": "tag"}` with no `tag_ids` key at
    # all would never even run the check below (only an explicit
    # `"tag_ids": null` would). Found by a failing test
    # (test_bulk_tag_requires_tag_ids expected 422, got an unhandled
    # AssertionError deeper in the service instead).
    tag_ids: list[uuid.UUID] | None = Field(default=None, validate_default=True)

    @field_validator("tag_ids")
    @classmethod
    def _tag_ids_required_for_tag_action(
        cls, value: list[uuid.UUID] | None, info
    ) -> list[uuid.UUID] | None:
        if info.data.get("action") == "tag" and not value:
            raise ValueError("tag_ids is required when action is 'tag'.")
        return value


class BulkActionResponse(BaseModel):
    affected: int
    skipped: int
