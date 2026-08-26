"""api.md §7 (/comparisons) — tasks/remediation-plan.md R6."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csrf import verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.core.security import AccessTokenClaims
from app.models import Comparison
from app.repositories.comparison_repository import ComparisonRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.comparison import (
    ComparisonCreateRequest,
    ComparisonCreateResponse,
    ComparisonDetailResponse,
    ComparisonListItem,
    ComparisonListResponse,
    ComparisonResult,
)
from app.services.comparison_service import ComparisonService

router = APIRouter(
    prefix="/comparisons",
    tags=["comparisons"],
    dependencies=[Depends(rate_limit_general)],
)


def get_comparison_service(
    db: AsyncSession = Depends(get_db_session),
) -> ComparisonService:
    return ComparisonService(ComparisonRepository(db), DocumentRepository(db))


def _to_detail_response(comparison: Comparison) -> ComparisonDetailResponse:
    # api.md §7: "result is null while status='processing'" — extended the
    # same way to `failed` (no meaningful result exists for either
    # non-terminal-success status); only a `completed` comparison has a
    # real ComparisonResult to surface.
    result = (
        ComparisonResult(**comparison.result_json)
        if comparison.status == "completed"
        else None
    )
    return ComparisonDetailResponse(
        id=comparison.id,
        document_a_id=comparison.document_a_id,
        document_b_id=comparison.document_b_id,
        status=comparison.status,
        result=result,
        created_at=comparison.created_at,
    )


@router.post(
    "",
    response_model=ComparisonCreateResponse,
    status_code=202,
    dependencies=[Depends(verify_csrf), Depends(rate_limit_ai)],
)
async def create_comparison(
    body: ComparisonCreateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonCreateResponse:
    comparison = await service.create_comparison(
        current_user.user_id, body.document_a_id, body.document_b_id
    )
    return ComparisonCreateResponse(id=comparison.id, status="processing")


@router.get("/{comparison_id}", response_model=ComparisonDetailResponse)
async def get_comparison(
    comparison_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonDetailResponse:
    comparison = await service.get_comparison(current_user.user_id, comparison_id)
    return _to_detail_response(comparison)


@router.get("", response_model=ComparisonListResponse)
async def list_comparisons(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonListResponse:
    comparisons, total = await service.list_comparisons(
        current_user.user_id, limit=limit, offset=offset
    )
    return ComparisonListResponse(
        items=[
            ComparisonListItem(
                id=c.id,
                document_a_id=c.document_a_id,
                document_b_id=c.document_b_id,
                status=c.status,
                created_at=c.created_at,
            )
            for c in comparisons
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
