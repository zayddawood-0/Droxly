"""
tasks/remediation-plan.md R7 — FR-SUM-001..002. The API-facing half of
summarization (skills/backend.md §12's "trigger" side, mirroring
ExtractionService/ComparisonService's split from R5/R6): validates the
request, persists the initial `processing` row, and enqueues the
background job. The graph-running half lives in
`SummaryProcessingService` (called only by the worker), never here.
"""

import uuid
from collections.abc import Sequence

from app.core.queue import enqueue_summary
from app.errors import DocumentNotReadyError, NotFoundError
from app.models import DocumentSummary
from app.repositories.document_repository import DocumentRepository
from app.repositories.summary_repository import DocumentSummaryRepository


class SummaryService:
    def __init__(
        self,
        summary_repo: DocumentSummaryRepository,
        document_repo: DocumentRepository,
    ) -> None:
        self.summary_repo = summary_repo
        self.document_repo = document_repo

    async def create_summary(
        self, user_id: uuid.UUID, document_id: uuid.UUID, summary_type: str
    ) -> DocumentSummary:
        """
        FR-SUM-001. `summary_type`'s enum validity is already enforced by
        `SummaryCreateRequest`'s Pydantic `Literal` type (skills/backend.md
        §9 — expressible purely from the request body's own shape); this
        method only checks what requires database/business state: the
        document must exist, be owned by the caller, and be `ready`.

        FR-SUM-002: never overwrites a prior summary — always a fresh
        `document_summaries` row, even for the same document/summary_type.
        """
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        if document.status != "ready":
            raise DocumentNotReadyError()

        summary = await self.summary_repo.create(
            user_id,
            document_id=document_id,
            summary_type=summary_type,
            status="processing",
            content=None,
        )
        enqueue_summary(user_id, summary.id)
        return summary

    async def get_summary(
        self, user_id: uuid.UUID, summary_id: uuid.UUID
    ) -> DocumentSummary:
        summary = await self.summary_repo.get(user_id, summary_id)
        if summary is None:
            raise NotFoundError()
        return summary

    async def list_for_document(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[DocumentSummary], int]:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        return await self.summary_repo.list_for_document(
            user_id, document_id, limit=limit, offset=offset
        )
