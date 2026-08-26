import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models import Extraction
from app.repositories.base import TenantScopedRepository


class ExtractionRepository(TenantScopedRepository[Extraction]):
    model = Extraction

    async def list_for_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[Extraction], int]:
        """api.md §6 `GET /documents/{document_id}/extractions` — history for
        one document, newest first (mirrors ConversationRepository.list_paginated's
        shape: items + total in one round-trip pair)."""
        base_filters = [
            Extraction.user_id == user_id,
            Extraction.document_id == document_id,
        ]
        stmt = (
            select(Extraction)
            .where(*base_filters)
            .order_by(Extraction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Extraction).where(*base_filters)
        items = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total

    async def set_result(
        self,
        user_id: uuid.UUID,
        id: uuid.UUID,
        *,
        status: str,
        result_json: list[dict],
    ) -> Extraction | None:
        """
        FR-EXT-001 — the background worker's terminal write, whichever the
        Extraction graph's own outcome (`success`/`failed`, langgraph.md
        §4). Owner-scoped like every other write here (`NFR-SEC-001`).
        """
        extraction = await self.get(user_id, id)
        if extraction is None:
            return None
        extraction.status = status
        extraction.result_json = result_json
        await self.session.flush()
        return extraction
