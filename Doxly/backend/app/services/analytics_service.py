import uuid
from datetime import UTC, date, datetime, timedelta

from app.repositories.analytics_repository import AnalyticsRepository, DayCount
from app.repositories.user_repository import UserRepository
from app.schemas.analytics import (
    AnalyticsDashboardResponse,
    AnalyticsPeriod,
    FeatureUsage,
    TimeSeriesPoint,
)

# api.md §9 — the period query param is a rolling window (now - N days),
# matching AiRequestRepository.count_since's existing "since" semantic
# elsewhere in the codebase, not a calendar-aligned bucket.
PERIOD_DAYS: dict[AnalyticsPeriod, int] = {"7d": 7, "30d": 30, "90d": 90}


def _fill_zero_days(
    counts: list[DayCount], *, since: date, until: date
) -> list[TimeSeriesPoint]:
    """
    A chart-ready, gap-free time series: every day in the window appears
    exactly once, in order, even if nothing happened that day — a chart
    consuming the raw grouped-by-day query would otherwise show
    misleadingly connected lines across missing days.
    """
    by_day = {c.day: c.count for c in counts}
    points: list[TimeSeriesPoint] = []
    day = since
    while day <= until:
        points.append(TimeSeriesPoint(date=day, count=by_day.get(day, 0)))
        day += timedelta(days=1)
    return points


class AnalyticsService:
    """
    api.md §9 (`GET /analytics/dashboard`), `FR-ANALYTICS-001` — read-only
    aggregation, no AI/provider calls of its own (`observability.md` §4
    doesn't apply here — R9 makes no LLM/embedding calls, it only reads
    already-logged `ai_requests` rows).
    """

    def __init__(
        self,
        analytics_repository: AnalyticsRepository,
        user_repository: UserRepository,
    ) -> None:
        self._analytics = analytics_repository
        self._users = user_repository

    async def get_dashboard(
        self, user_id: uuid.UUID, period: AnalyticsPeriod
    ) -> AnalyticsDashboardResponse:
        now = datetime.now(UTC)
        since = now - timedelta(days=PERIOD_DAYS[period])
        since_date = since.date()
        until_date = now.date()

        documents_by_day = await self._analytics.documents_processed_by_day(
            user_id, since
        )
        ai_requests_by_day = await self._analytics.ai_requests_by_day(user_id, since)
        feature_counts = await self._analytics.most_used_features(user_id, since)
        user = await self._users.get_by_id(user_id)

        documents_over_time = _fill_zero_days(
            documents_by_day, since=since_date, until=until_date
        )
        ai_requests_over_time = _fill_zero_days(
            ai_requests_by_day, since=since_date, until=until_date
        )

        return AnalyticsDashboardResponse(
            documents_processed=sum(p.count for p in documents_over_time),
            documents_over_time=documents_over_time,
            ai_requests=sum(p.count for p in ai_requests_over_time),
            ai_requests_over_time=ai_requests_over_time,
            storage_used_bytes=user.storage_used_bytes if user is not None else 0,
            most_used_features=[
                FeatureUsage(feature=f.feature, count=f.count) for f in feature_counts
            ],
        )
