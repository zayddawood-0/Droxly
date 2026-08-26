"""
tasks/remediation-plan.md R6 — FR-COMP-001..003. The API-facing half of
comparison (skills/backend.md §12's "trigger" side, mirroring
ExtractionService vs. ExtractionProcessingService's split from R5):
validates the request, persists the initial `processing` row, and enqueues
the background job. The graph-running half lives in
`ComparisonProcessingService` (called only by the worker), never here.
"""

import uuid
from collections.abc import Sequence

from app.core.queue import enqueue_comparison
from app.errors import DocumentNotReadyError, IdenticalDocumentsError, NotFoundError
from app.models import Comparison
from app.repositories.comparison_repository import ComparisonRepository
from app.repositories.document_repository import DocumentRepository


class ComparisonService:
    def __init__(
        self,
        comparison_repo: ComparisonRepository,
        document_repo: DocumentRepository,
    ) -> None:
        self.comparison_repo = comparison_repo
        self.document_repo = document_repo

    async def create_comparison(
        self,
        user_id: uuid.UUID,
        document_a_id: uuid.UUID,
        document_b_id: uuid.UUID,
    ) -> Comparison:
        """
        FR-COMP-001. api.md §7's error precedence: `422 identical_documents`
        is checked first — expressible purely from the request body's own
        two fields, no database lookup needed (cheapest check, and mirrors
        `comparisons`' own `CHECK (document_a_id <> document_b_id)`,
        `database.md` §3.12) — before the two-object tenant/readiness check
        remediation-plan.md §9 calls out as this task's "dedicated test
        shape, not the single-object pattern R4/R5 use": both documents must
        exist and be owned by the caller (404, either missing — never
        distinguishing which, per `NFR-SEC-001`'s 404-not-403 pattern) and
        both must be `ready` (409) before comparison can run.
        """
        if document_a_id == document_b_id:
            raise IdenticalDocumentsError()

        document_a = await self.document_repo.get(user_id, document_a_id)
        document_b = await self.document_repo.get(user_id, document_b_id)
        if document_a is None or document_b is None:
            raise NotFoundError()
        if document_a.status != "ready" or document_b.status != "ready":
            raise DocumentNotReadyError()

        comparison = await self.comparison_repo.create(
            user_id,
            document_a_id=document_a_id,
            document_b_id=document_b_id,
            result_json={},
            status="processing",
        )
        enqueue_comparison(user_id, comparison.id)
        return comparison

    async def get_comparison(
        self, user_id: uuid.UUID, comparison_id: uuid.UUID
    ) -> Comparison:
        comparison = await self.comparison_repo.get(user_id, comparison_id)
        if comparison is None:
            raise NotFoundError()
        return comparison

    async def list_comparisons(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[Comparison], int]:
        return await self.comparison_repo.list_paginated(
            user_id, limit=limit, offset=offset
        )
