import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models import DocumentSummary
from app.repositories.base import TenantScopedRepository


class DocumentSummaryRepository(TenantScopedRepository[DocumentSummary]):
    model = DocumentSummary

    async def list_for_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[DocumentSummary], int]:
        """api.md §5 `GET /documents/{id}/summaries` — every summary ever
        generated for the document, newest first (FR-SUM-002: regenerating
        never overwrites or hides a prior one)."""
        base_filters = [
            DocumentSummary.user_id == user_id,
            DocumentSummary.document_id == document_id,
        ]
        stmt = (
            select(DocumentSummary)
            .where(*base_filters)
            .order_by(DocumentSummary.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = (
            select(func.count()).select_from(DocumentSummary).where(*base_filters)
        )
        items = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total

    async def set_result(
        self,
        user_id: uuid.UUID,
        id: uuid.UUID,
        *,
        status: str,
        content: str | None,
    ) -> DocumentSummary | None:
        """FR-SUM-001 — the background worker's terminal write, whichever
        the Summarization graph's own outcome (`success`/`failed`,
        langgraph.md §3). Owner-scoped like every other write here
        (`NFR-SEC-001`)."""
        summary = await self.get(user_id, id)
        if summary is None:
            return None
        summary.status = status
        summary.content = content
        await self.session.flush()
        return summary
