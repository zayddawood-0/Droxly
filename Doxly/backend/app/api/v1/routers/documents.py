"""api.md §3 (/documents, /tags) — tasks/remediation-plan.md R2."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csrf import verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.core.security import AccessTokenClaims
from app.core.storage import get_storage_provider
from app.errors import NotFoundError
from app.models import Document, Tag
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
    DocumentTagRepository,
    TagRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.document import (
    BulkActionRequest,
    BulkActionResponse,
    ConfirmResponse,
    ContentPagesResponse,
    ContentRowsResponse,
    ContentTextResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentUpdateRequest,
    DownloadResponse,
    PresignRequest,
    PresignResponse,
    StatusResponse,
)
from app.schemas.tag import TagCreateRequest, TagResponse, TagsListResponse
from app.services.document_service import DocumentService

router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(rate_limit_general)]
)
tags_router = APIRouter(
    prefix="/tags", tags=["tags"], dependencies=[Depends(rate_limit_general)]
)


def get_document_service(db: AsyncSession = Depends(get_db_session)) -> DocumentService:
    return DocumentService(
        DocumentRepository(db),
        DocumentChunkRepository(db),
        TagRepository(db),
        DocumentTagRepository(db),
        UserRepository(db),
        get_storage_provider(),
    )


def _to_list_item(document: Document, tags: list[Tag]) -> DocumentListItem:
    return DocumentListItem(
        id=document.id,
        file_name=document.file_name,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        status=document.status,
        page_count=document.page_count,
        tags=[TagResponse.model_validate(t) for t in tags],
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _to_detail(document: Document, tags: list[Tag]) -> DocumentDetail:
    base = _to_list_item(document, tags)
    return DocumentDetail(
        **base.model_dump(),
        checksum_sha256=document.checksum_sha256,
        processing_error=document.processing_error,
        extracted_text_available=document.extracted_text_available,
    )


@router.post(
    "/presign",
    response_model=PresignResponse,
    status_code=201,
    dependencies=[Depends(verify_csrf)],
)
async def presign(
    body: PresignRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> PresignResponse:
    document, presigned = await service.presign_upload(
        current_user.user_id,
        file_name=body.file_name,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
    )
    return PresignResponse(
        document_id=document.id,
        upload_url=presigned.upload_url,
        upload_method=presigned.upload_method,  # type: ignore[arg-type]
        upload_headers=presigned.upload_headers,
        expires_in=presigned.expires_in,
    )


@router.post(
    "/{document_id}/confirm",
    response_model=ConfirmResponse,
    status_code=202,
    dependencies=[Depends(verify_csrf)],
)
async def confirm(
    document_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> ConfirmResponse:
    document = await service.confirm_upload(current_user.user_id, document_id)
    return ConfirmResponse(id=document.id, status="queued")


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    tag_id: uuid.UUID | None = Query(default=None),
    mime_type: str | None = Query(default=None),
    sort: str = Query(default="created_at_desc"),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    documents, tags_by_document, total = await service.list_documents(
        current_user.user_id,
        limit=limit,
        offset=offset,
        status=status,
        tag_id=tag_id,
        mime_type=mime_type,
        sort=sort,
    )
    items = [_to_list_item(doc, tags_by_document.get(doc.id, [])) for doc in documents]
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentDetail:
    document, tags = await service.get_document(current_user.user_id, document_id)
    return _to_detail(document, tags)


@router.get("/{document_id}/download", response_model=DownloadResponse)
async def download(
    document_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DownloadResponse:
    presigned = await service.get_download_url(current_user.user_id, document_id)
    return DownloadResponse(
        download_url=presigned.download_url, expires_in=presigned.expires_in
    )


@router.get("/{document_id}/content")
async def get_content(
    document_id: uuid.UUID,
    page: int | None = Query(default=None),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> ContentPagesResponse | ContentTextResponse | ContentRowsResponse:
    content = await service.get_content(current_user.user_id, document_id)
    if "pages" in content:
        pages = content["pages"]
        if page is not None:
            pages = [p for p in pages if p["page_number"] == page]
        return ContentPagesResponse(pages=pages)
    if "rows" in content:
        return ContentRowsResponse(**content)
    return ContentTextResponse(**content)


@router.patch(
    "/{document_id}", response_model=DocumentDetail, dependencies=[Depends(verify_csrf)]
)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentDetail:
    document, tags = await service.update_document(
        current_user.user_id,
        document_id,
        file_name=body.file_name,
        tag_ids=body.tag_ids,
    )
    return _to_detail(document, tags)


@router.delete("/{document_id}", status_code=204, dependencies=[Depends(verify_csrf)])
async def delete_document(
    document_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> None:
    await service.delete_document(current_user.user_id, document_id)


@router.post(
    "/{document_id}/reprocess",
    response_model=ConfirmResponse,
    status_code=202,
    dependencies=[Depends(verify_csrf), Depends(rate_limit_ai)],
)
async def reprocess(
    document_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> ConfirmResponse:
    document = await service.reprocess_document(current_user.user_id, document_id)
    return ConfirmResponse(id=document.id, status="queued")


@router.get("/{document_id}/status", response_model=StatusResponse)
async def get_status(
    document_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> StatusResponse:
    document = await service.get_status(current_user.user_id, document_id)
    return StatusResponse(
        status=document.status, processing_error=document.processing_error
    )


_SSE_POLL_INTERVAL_SECONDS = 1.0
_SSE_MAX_ITERATIONS = 600  # 10 minutes at 1s — a safety bound, not a budget claim


async def _status_event_stream(
    document_repo: DocumentRepository,
    request: Request,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
):
    """
    tasks/remediation-plan.md R2 §5.2 — polls documents.status (the same
    column FR-PROC-*/R3's worker will eventually drive) rather than any
    pub/sub mechanism, since none exists yet; correct under Postgres's
    default READ COMMITTED isolation (each poll's own SELECT sees the
    latest committed value, even from a different transaction). Emits the
    current status immediately on connect, then again only on change,
    closing right after a terminal ready/failed event.
    """
    last_status: str | None = None
    for _ in range(_SSE_MAX_ITERATIONS):
        if await request.is_disconnected():
            return
        document = await document_repo.get(user_id, document_id)
        if document is None:
            return
        if document.status != last_status:
            last_status = document.status
            yield f"event: status\ndata: {json.dumps({'status': document.status})}\n\n"
            if document.status in ("ready", "failed"):
                return
        await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)


@router.get("/{document_id}/status/stream")
async def stream_status(
    document_id: uuid.UUID,
    request: Request,
    current_user: AccessTokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    document_repo = DocumentRepository(db)
    # Ownership checked before the stream opens (remediation-plan.md R2
    # §5.2: "404 before any event streams") — never inside the generator,
    # where a 404 would otherwise have to be smuggled in as an SSE event
    # instead of a real HTTP status code.
    document = await document_repo.get(current_user.user_id, document_id)
    if document is None:
        raise NotFoundError()

    return StreamingResponse(
        _status_event_stream(document_repo, request, current_user.user_id, document_id),
        media_type="text/event-stream",
    )


@router.post(
    "/bulk", response_model=BulkActionResponse, dependencies=[Depends(verify_csrf)]
)
async def bulk_action(
    body: BulkActionRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> BulkActionResponse:
    affected, skipped = await service.bulk_action(
        current_user.user_id,
        document_ids=body.document_ids,
        action=body.action,
        tag_ids=body.tag_ids,
    )
    return BulkActionResponse(affected=affected, skipped=skipped)


# --- /tags ---


@tags_router.get("", response_model=TagsListResponse)
async def list_tags(
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> TagsListResponse:
    tags = await service.list_tags(current_user.user_id)
    return TagsListResponse(items=[TagResponse.model_validate(t) for t in tags])


@tags_router.post(
    "", response_model=TagResponse, status_code=201, dependencies=[Depends(verify_csrf)]
)
async def create_tag(
    body: TagCreateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> TagResponse:
    tag = await service.create_tag(
        current_user.user_id, name=body.name, color=body.color
    )
    return TagResponse.model_validate(tag)


@tags_router.delete("/{tag_id}", status_code=204, dependencies=[Depends(verify_csrf)])
async def delete_tag(
    tag_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> None:
    await service.delete_tag(current_user.user_id, tag_id)
