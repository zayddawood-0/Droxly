"""api.md §5 (/summaries) — tasks/remediation-plan.md R7."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csrf import verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.core.security import AccessTokenClaims
from app.models import DocumentSummary
from app.repositories.document_repository import DocumentRepository
from app.repositories.summary_repository import DocumentSummaryRepository
from app.schemas.summary import (
    SummaryCreateRequest,
    SummaryCreateResponse,
    SummaryDetailResponse,
    SummaryListItem,
    SummaryListResponse,
)
from app.services.summary_service import SummaryService

# api.md §5 splits across two path prefixes — POST/GET-list live under
# /documents/{id}/summaries, GET-one lives under /summaries/{id} — same
# split pattern extractions.py uses for its own /documents sub-router.
router = APIRouter(
    prefix="/summaries", tags=["summaries"], dependencies=[Depends(rate_limit_general)]
)
document_summaries_router = APIRouter(
    prefix="/documents", tags=["summaries"], dependencies=[Depends(rate_limit_general)]
)


def get_summary_service(db: AsyncSession = Depends(get_db_session)) -> SummaryService:
    return SummaryService(DocumentSummaryRepository(db), DocumentRepository(db))


def _to_detail_response(summary: DocumentSummary) -> SummaryDetailResponse:
    return SummaryDetailResponse(
        id=summary.id,
        document_id=summary.document_id,
        summary_type=summary.summary_type,
        status=summary.status,
        content=summary.content,
        created_at=summary.created_at,
    )


@document_summaries_router.post(
    "/{document_id}/summaries",
    response_model=SummaryCreateResponse,
    status_code=202,
    dependencies=[Depends(verify_csrf), Depends(rate_limit_ai)],
)
async def create_summary(
    document_id: uuid.UUID,
    body: SummaryCreateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryCreateResponse:
    summary = await service.create_summary(
        current_user.user_id, document_id, body.summary_type
    )
    return SummaryCreateResponse(
        id=summary.id,
        document_id=document_id,
        summary_type=body.summary_type,
        status="processing",
    )


@document_summaries_router.get(
    "/{document_id}/summaries", response_model=SummaryListResponse
)
async def list_document_summaries(
    document_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryListResponse:
    summaries, total = await service.list_for_document(
        current_user.user_id, document_id, limit=limit, offset=offset
    )
    return SummaryListResponse(
        items=[
            SummaryListItem(
                id=s.id,
                summary_type=s.summary_type,
                status=s.status,
                created_at=s.created_at,
            )
            for s in summaries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{summary_id}", response_model=SummaryDetailResponse)
async def get_summary(
    summary_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryDetailResponse:
    summary = await service.get_summary(current_user.user_id, summary_id)
    return _to_detail_response(summary)
