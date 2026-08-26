"""api.md §6 (/extractions) request/response shapes — tasks/remediation-plan.md R5."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.graphs.extraction import PRESET_TEMPLATES


class ExtractionFieldSchema(BaseModel):
    """
    A single field in a (custom or resolved-preset) extraction schema.
    Attribute names deliberately match `app/ai/graphs/extraction.py`'s
    internal field-dict shape (`name`/`type`/`description`/`required`)
    exactly — the graph consumes whichever of the two produced this data
    identically, no adapter needed between "preset" and "custom" schemas.
    """

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    description: str | None = None
    required: bool = False


class ExtractionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID
    template_key: str | None = None
    schema_: list[ExtractionFieldSchema] | None = Field(default=None, alias="schema")

    @model_validator(mode="after")
    def _exactly_one_of_template_or_schema(self) -> "ExtractionCreateRequest":
        """api.md §6: "exactly one of template_key or schema must be present" —
        expressible purely from the request body's own shape plus the static
        template registry, so this belongs in Pydantic (skills/backend.md §9),
        not a service-layer check."""
        has_template = self.template_key is not None
        has_schema = self.schema_ is not None
        if has_template == has_schema:
            raise ValueError("Exactly one of template_key or schema must be provided.")
        if has_template and self.template_key not in PRESET_TEMPLATES:
            raise ValueError(f"Unknown template_key: {self.template_key!r}")
        return self


class ExtractionCreateResponse(BaseModel):
    id: uuid.UUID
    status: Literal["processing"]


class ExtractionCitation(BaseModel):
    page_number: int | None
    snippet: str


class ExtractionFieldResult(BaseModel):
    field: str
    value: Any | None
    confidence: float | None
    not_found_reason: str | None
    corrected: bool
    citation: ExtractionCitation | None


class ExtractionDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID
    template_key: str | None
    schema_: list[ExtractionFieldSchema] = Field(alias="schema")
    status: str
    result: list[ExtractionFieldResult]
    created_at: datetime


class ExtractionListItem(BaseModel):
    id: uuid.UUID
    template_key: str | None
    status: str
    created_at: datetime


class ExtractionListResponse(BaseModel):
    items: list[ExtractionListItem]
    total: int
    limit: int
    offset: int


class ExtractionCorrectionItem(BaseModel):
    field: str = Field(min_length=1)
    value: Any


class ExtractionCorrectionRequest(BaseModel):
    corrections: list[ExtractionCorrectionItem] = Field(min_length=1)


class ExtractionTemplateField(BaseModel):
    name: str
    type: str
    description: str | None
    required: bool


class ExtractionTemplate(BaseModel):
    key: str
    name: str
    description: str
    fields: list[ExtractionTemplateField]


class ExtractionTemplatesResponse(BaseModel):
    items: list[ExtractionTemplate]
