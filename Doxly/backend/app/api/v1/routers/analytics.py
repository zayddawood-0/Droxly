"""api.md §9 (/analytics) — tasks/remediation-plan.md R9. GET-only; only
`GET /analytics/dashboard` (FR-ANALYTICS-001, P1) is in scope for R9 —
`GET /analytics/documents/{id}` is FR-ANALYTICS-002 (P2), explicitly
deferred past this task per remediation-plan.md §17."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_general
from app.core.security import AccessTokenClaims
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.analytics import AnalyticsDashboardResponse, AnalyticsPeriod
from app.services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(rate_limit_general)],
)


def get_analytics_service(
    db: AsyncSession = Depends(get_db_session),
) -> AnalyticsService:
    return AnalyticsService(AnalyticsRepository(db), UserRepository(db))


@router.get("/dashboard", response_model=AnalyticsDashboardResponse)
async def get_dashboard(
    period: AnalyticsPeriod = Query(default="30d"),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsDashboardResponse:
    return await service.get_dashboard(current_user.user_id, period)
