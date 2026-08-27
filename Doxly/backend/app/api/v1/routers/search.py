"""api.md §8 (/search) — tasks/remediation-plan.md R8."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingProvider, get_embedding_provider
from app.core.dependencies import get_current_user, get_db_session
from app.core.rate_limit import rate_limit_general
from app.core.security import AccessTokenClaims
from app.errors import RequestValidationFailedError
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.search_repository import SearchRepository
from app.schemas.search import (
    SearchHighlight,
    SearchResponse,
    SearchResultItem,
    SearchSnippet,
)
from app.services.search_service import SearchService

# GET-only (api.md §8) — no CSRF dependency needed (security.md §6.3 only
# requires it for mutating verbs); general rate-limit tier applies like
# every other router (api.md §0.7 — search isn't in the AI-tier route list).
router = APIRouter(
    prefix="/search", tags=["search"], dependencies=[Depends(rate_limit_general)]
)


def get_search_service(
    db: AsyncSession = Depends(get_db_session),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> SearchService:
    return SearchService(
        SearchRepository(db), AiRequestRepository(db), embedding_provider
    )


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    mime_type: str | None = Query(default=None),
    tag_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    # api.md §8: "422 if q is empty or date_from > date_to". `q`'s
    # min_length=1 is enforced by the Query() constraint above (Pydantic
    # request-shape validation, skills/backend.md §9); date_from > date_to
    # needs current values from both params so it's checked here rather
    # than expressed as a field constraint. No dedicated error code is
    # named for this case, so the generic validation_error shape applies
    # (RequestValidationFailedError, the same one FastAPI's own Query
    # failures produce) — no invented DoxlyError subclass needed.
    if date_from is not None and date_to is not None and date_from > date_to:
        raise RequestValidationFailedError(
            {"date_to": "date_to must not be before date_from."}
        )

    results, total = await service.search(
        current_user.user_id,
        q,
        limit=limit,
        offset=offset,
        mime_type=mime_type,
        tag_id=tag_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return SearchResponse(
        items=[
            SearchResultItem(
                document_id=r.document_id,
                file_name=r.file_name,
                snippet=SearchSnippet(
                    text=r.snippet_text,
                    highlights=[
                        SearchHighlight(start=start, end=end)
                        for start, end in r.highlights
                    ],
                ),
                relevance_score=r.relevance_score,
                matched_page=r.matched_page,
            )
            for r in results
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
