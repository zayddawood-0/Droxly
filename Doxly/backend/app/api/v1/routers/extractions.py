"""api.md §6 (/extractions) — tasks/remediation-plan.md R5."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graphs.extraction import PRESET_TEMPLATES
from app.core.csrf import verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.core.security import AccessTokenClaims
from app.models import Extraction
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.schemas.extraction import (
    ExtractionCorrectionRequest,
    ExtractionCreateRequest,
    ExtractionCreateResponse,
    ExtractionDetailResponse,
    ExtractionFieldResult,
    ExtractionFieldSchema,
    ExtractionListItem,
    ExtractionListResponse,
    ExtractionTemplate,
    ExtractionTemplateField,
    ExtractionTemplatesResponse,
)
from app.services.extraction_service import ExtractionService

router = APIRouter(
    prefix="/extractions",
    tags=["extractions"],
    dependencies=[Depends(rate_limit_general)],
)

# api.md §6 GET /documents/{document_id}/extractions is scoped under
# /documents, not /extractions — a second router mounted at that prefix,
# same pattern as documents.py's separate `tags_router`.
document_extractions_router = APIRouter(
    prefix="/documents",
    tags=["extractions"],
    dependencies=[Depends(rate_limit_general)],
)


def get_extraction_service(
    db: AsyncSession = Depends(get_db_session),
) -> ExtractionService:
    return ExtractionService(ExtractionRepository(db), DocumentRepository(db))


def _to_detail_response(extraction: Extraction) -> ExtractionDetailResponse:
    return ExtractionDetailResponse(
        id=extraction.id,
        document_id=extraction.document_id,
        template_key=extraction.template_key,
        schema=[ExtractionFieldSchema(**field) for field in extraction.schema_json],
        status=extraction.status,  # type: ignore[arg-type]
        result=[
            ExtractionFieldResult(
                field=item["field"],
                value=item["value"],
                confidence=item["confidence"],
                not_found_reason=item["not_found_reason"],
                corrected=item["corrected"],
                citation=item["citation"],
            )
            for item in extraction.result_json
        ],
        created_at=extraction.created_at,
    )


@router.get("/templates", response_model=ExtractionTemplatesResponse)
async def list_templates(
    current_user: AccessTokenClaims = Depends(get_current_user),
) -> ExtractionTemplatesResponse:
    return ExtractionTemplatesResponse(
        items=[
            ExtractionTemplate(
                key=key,
                name=template["name"],
                description=template["description"],
                fields=[
                    ExtractionTemplateField(**field) for field in template["fields"]
                ],
            )
            for key, template in PRESET_TEMPLATES.items()
        ]
    )


@router.post(
    "",
    response_model=ExtractionCreateResponse,
    status_code=202,
    dependencies=[Depends(verify_csrf), Depends(rate_limit_ai)],
)
async def create_extraction(
    body: ExtractionCreateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionCreateResponse:
    schema = (
        [field.model_dump() for field in body.schema_]
        if body.schema_ is not None
        else None
    )
    extraction = await service.create_extraction(
        current_user.user_id,
        body.document_id,
        template_key=body.template_key,
        schema=schema,
    )
    return ExtractionCreateResponse(id=extraction.id, status="processing")


@router.get("/{extraction_id}", response_model=ExtractionDetailResponse)
async def get_extraction(
    extraction_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionDetailResponse:
    extraction = await service.get_extraction(current_user.user_id, extraction_id)
    return _to_detail_response(extraction)


@router.patch(
    "/{extraction_id}",
    response_model=ExtractionDetailResponse,
    dependencies=[Depends(verify_csrf)],
)
async def correct_extraction(
    extraction_id: uuid.UUID,
    body: ExtractionCorrectionRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionDetailResponse:
    extraction = await service.apply_corrections(
        current_user.user_id,
        extraction_id,
        [c.model_dump() for c in body.corrections],
    )
    return _to_detail_response(extraction)


@document_extractions_router.get(
    "/{document_id}/extractions", response_model=ExtractionListResponse
)
async def list_document_extractions(
    document_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionListResponse:
    extractions, total = await service.list_for_document(
        current_user.user_id, document_id, limit=limit, offset=offset
    )
    return ExtractionListResponse(
        items=[
            ExtractionListItem(
                id=e.id,
                template_key=e.template_key,
                status=e.status,  # type: ignore[arg-type]
                created_at=e.created_at,
            )
            for e in extractions
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
