"""
tasks/remediation-plan.md R5 — FR-EXT-001..004. The API-facing half of
extraction (skills/backend.md §12's "trigger" side, mirroring
DocumentService vs. DocumentProcessingService's split from R3): validates
the request, persists the initial `processing` row, and enqueues the
background job. The graph-running half lives in
`ExtractionProcessingService` (called only by the worker), never here.
"""

import uuid
from collections.abc import Sequence

from app.ai.graphs.extraction import PRESET_TEMPLATES
from app.core.queue import enqueue_extraction
from app.errors import DocumentNotReadyError, NotFoundError, UnknownExtractionFieldError
from app.models import Extraction
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository


class ExtractionService:
    def __init__(
        self,
        extraction_repo: ExtractionRepository,
        document_repo: DocumentRepository,
    ) -> None:
        self.extraction_repo = extraction_repo
        self.document_repo = document_repo

    async def create_extraction(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        template_key: str | None,
        schema: list[dict] | None,
    ) -> Extraction:
        """
        FR-EXT-001. `template_key`/`schema` mutual exclusivity and
        `template_key` membership are already enforced by
        `ExtractionCreateRequest` (Pydantic, api.md §6) — this method only
        checks what requires database/business state (skills/backend.md
        §9): the document must exist, be owned by the caller, and be
        `ready` before extraction can run.
        """
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        if document.status != "ready":
            raise DocumentNotReadyError()

        if schema is not None:
            resolved_schema = schema
        else:
            # `ExtractionCreateRequest`'s model_validator (api.md §6)
            # already guarantees exactly one of template_key/schema is set,
            # and that template_key is a known key when set.
            assert template_key is not None
            resolved_schema = PRESET_TEMPLATES[template_key]["fields"]
        extraction = await self.extraction_repo.create(
            user_id,
            document_id=document_id,
            template_key=template_key,
            schema_json=resolved_schema,
            result_json=[],
            status="processing",
        )
        enqueue_extraction(user_id, extraction.id)
        return extraction

    async def get_extraction(
        self, user_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> Extraction:
        extraction = await self.extraction_repo.get(user_id, extraction_id)
        if extraction is None:
            raise NotFoundError()
        return extraction

    async def list_for_document(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Extraction], int]:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        return await self.extraction_repo.list_for_document(
            user_id, document_id, limit=limit, offset=offset
        )

    async def apply_corrections(
        self,
        user_id: uuid.UUID,
        extraction_id: uuid.UUID,
        corrections: list[dict],
    ) -> Extraction:
        """
        FR-EXT-004. api.md §6 PATCH: "the model's original value is
        retained internally in result_json for audit purposes but not
        surfaced in this response" — each stored field result already
        carries an `original_value` (set once, at persistence time by
        `ExtractionProcessingService`, and never overwritten here); a
        correction only ever updates `value` and flips `corrected=True`.
        """
        extraction = await self.extraction_repo.get(user_id, extraction_id)
        if extraction is None:
            raise NotFoundError()

        # api.md §6: "422 if any field name isn't present in the
        # extraction's schema" — validated against `schema_json` (the
        # field definitions), not `result_json` (the populated results),
        # since these can genuinely differ while an extraction is still
        # `processing` (no results persisted yet).
        known_fields = {field["name"] for field in extraction.schema_json}
        unknown = [c["field"] for c in corrections if c["field"] not in known_fields]
        if unknown:
            raise UnknownExtractionFieldError()

        updated_result = [dict(item) for item in extraction.result_json]
        by_field = {item["field"]: item for item in updated_result}
        for correction in corrections:
            field_result = by_field.get(correction["field"])
            if field_result is None:
                field_result = {
                    "field": correction["field"],
                    "value": None,
                    "original_value": None,
                    "confidence": None,
                    "not_found_reason": None,
                    "citation": None,
                    "corrected": False,
                }
                updated_result.append(field_result)
                by_field[correction["field"]] = field_result
            field_result["value"] = correction["value"]
            field_result["corrected"] = True

        updated = await self.extraction_repo.set_result(
            user_id, extraction_id, status=extraction.status, result_json=updated_result
        )
        assert updated is not None
        return updated
