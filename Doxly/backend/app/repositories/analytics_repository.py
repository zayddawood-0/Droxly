import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiRequest, Document

# api.md §9 — "most_used_features" reflects operations a user actually
# chose to invoke (chat/summarization/extraction/comparison). "embedding"
# is excluded deliberately: it's an internal implementation detail fired
# by chat retrieval, document processing, and search, never a feature a
# user selected in its own right — counting it here would make every
# other feature look artificially rare by comparison.
FEATURE_OPERATIONS = ("chat", "summarization", "extraction", "comparison")


@dataclass(frozen=True)
class DayCount:
    day: date
    count: int


@dataclass(frozen=True)
class FeatureCount:
    feature: str
    count: int


class AnalyticsRepository:
    """
    api.md §9 (`GET /analytics/dashboard`), `FR-ANALYTICS-001` — read-only
    aggregate queries over `documents` and `ai_requests`. Deliberately not a
    `TenantScopedRepository` subclass (same reasoning as `SearchRepository`,
    R8): these are cross-table aggregates, not generic CRUD over one model,
    and `database.md` §6 traceability is explicit there is no dedicated
    analytics table for MVP — everything here is computed at query time.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def documents_processed_by_day(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[DayCount]:
        """
        `FR-ANALYTICS-001`'s "documents processed" — a document that
        actually reached `ready` (successfully processed), not merely
        uploaded/attempted. `NFR-SEC-001`: scoped to `user_id`, excluding
        soft-deleted rows, matching every other document query in the
        codebase.
        """
        day = func.date_trunc("day", Document.created_at).label("day")
        stmt = (
            select(day, func.count().label("total"))
            .where(
                Document.user_id == user_id,
                Document.deleted_at.is_(None),
                Document.status == "ready",
                Document.created_at >= since,
            )
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.session.execute(stmt)).all()
        # `row.count` would silently resolve to Row's inherited tuple.count
        # method, not a labeled column — the label is "total" specifically
        # to avoid that collision (verified via mypy, not assumed safe).
        return [DayCount(day=row.day.date(), count=row.total) for row in rows]

    async def ai_requests_by_day(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[DayCount]:
        day = func.date_trunc("day", AiRequest.created_at).label("day")
        stmt = (
            select(day, func.count().label("total"))
            .where(AiRequest.user_id == user_id, AiRequest.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.session.execute(stmt)).all()
        return [DayCount(day=row.day.date(), count=row.total) for row in rows]

    async def most_used_features(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[FeatureCount]:
        stmt = (
            select(AiRequest.operation, func.count().label("total"))
            .where(
                AiRequest.user_id == user_id,
                AiRequest.created_at >= since,
                AiRequest.operation.in_(FEATURE_OPERATIONS),
            )
            .group_by(AiRequest.operation)
            .order_by(func.count().desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [FeatureCount(feature=row.operation, count=row.total) for row in rows]
