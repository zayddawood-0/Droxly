import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models import Comparison
from app.repositories.base import TenantScopedRepository


class ComparisonRepository(TenantScopedRepository[Comparison]):
    model = Comparison

    async def list_paginated(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[Sequence[Comparison], int]:
        """api.md §7 `GET /comparisons` — the caller's past comparisons,
        newest first (mirrors ConversationRepository.list_paginated's shape:
        items + total in one round-trip pair)."""
        base_filters = [Comparison.user_id == user_id]
        stmt = (
            select(Comparison)
            .where(*base_filters)
            .order_by(Comparison.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Comparison).where(*base_filters)
        items = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total

    async def set_result(
        self,
        user_id: uuid.UUID,
        id: uuid.UUID,
        *,
        status: str,
        result_json: dict,
    ) -> Comparison | None:
        """FR-COMP-001/002 — the background worker's terminal write, whichever
        the Comparison graph's own outcome (`success`/`failed`, langgraph.md
        §5). Owner-scoped like every other write here (`NFR-SEC-001`)."""
        comparison = await self.get(user_id, id)
        if comparison is None:
            return None
        comparison.status = status
        comparison.result_json = result_json
        await self.session.flush()
        return comparison
