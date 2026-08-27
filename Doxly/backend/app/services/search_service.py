import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date

from app.ai.embeddings import EmbeddingProvider
from app.document_processing.chunking import count_tokens
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.search_repository import SearchRepository

logger = logging.getLogger(__name__)

# rag.md §12 / ui-ux.md §12 — an excerpt window around the first matched
# term, not the whole chunk; keeps the response payload small and the
# highlighted region legible.
SNIPPET_WINDOW = 160
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class SearchResultView:
    """Service-layer result, fully assembled — the router only wraps this
    into `schemas.search` response models, no further business logic."""

    document_id: uuid.UUID
    file_name: str
    snippet_text: str
    highlights: list[tuple[int, int]]
    relevance_score: float
    matched_page: int | None


def _query_terms(query: str) -> list[str]:
    # Longest-first so the alternation regex prefers a longer overlapping
    # match (e.g. "invoices" over "invoice") at the same position.
    return sorted(
        {t for t in _WORD_RE.findall(query.lower()) if len(t) > 1},
        key=len,
        reverse=True,
    )


def build_snippet(content: str, query: str) -> tuple[str, list[tuple[int, int]]]:
    """
    api.md §8's `SearchSnippet`: a plain-text excerpt plus character-offset
    highlight ranges *into that excerpt* (never into the full content, and
    never pre-built HTML — `security.md` §6.2, document content is
    untrusted). Centers the excerpt on the first query-term occurrence; a
    vector-only match with no literal term overlap falls back to the
    excerpt's leading window with no highlights, which is a valid, expected
    shape (not an error).
    """
    terms = _query_terms(query)
    if not terms:
        return content[:SNIPPET_WINDOW], []

    pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    first_match = pattern.search(content)
    if first_match is None:
        return content[:SNIPPET_WINDOW], []

    start = max(0, first_match.start() - SNIPPET_WINDOW // 2)
    end = min(len(content), start + SNIPPET_WINDOW)
    start = max(0, end - SNIPPET_WINDOW)
    excerpt = content[start:end]
    highlights = [(m.start(), m.end()) for m in pattern.finditer(excerpt)]
    return excerpt, highlights


class SearchService:
    """
    api.md §8 (`GET /search`), `rag.md` §12 — the API-facing half: embeds
    the query (the one AI-provider call this synchronous, `GET`-only
    endpoint makes), delegates ranking/filtering to `SearchRepository`, and
    assembles snippets. No LangGraph workflow here (`CLAUDE.md` §5's
    "unnecessary LLM calls" guard) — search is a single provider call plus
    a database query, not a stateful multi-step workflow.
    """

    def __init__(
        self,
        search_repository: SearchRepository,
        ai_request_repo: AiRequestRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._search_repo = search_repository
        self._ai_request_repo = ai_request_repo
        self._embeddings = embedding_provider

    async def search(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        limit: int,
        offset: int,
        mime_type: str | None = None,
        tag_id: uuid.UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[SearchResultView], int]:
        query_embedding = await self._embed_query_with_observability(user_id, query)
        hits, total = await self._search_repo.search(
            user_id,
            query,
            query_embedding,
            limit=limit,
            offset=offset,
            mime_type=mime_type,
            tag_id=tag_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        results = []
        for hit in hits:
            snippet_text, highlights = build_snippet(hit.content, query)
            results.append(
                SearchResultView(
                    document_id=hit.document_id,
                    file_name=hit.file_name,
                    snippet_text=snippet_text,
                    highlights=highlights,
                    relevance_score=hit.relevance_score,
                    matched_page=hit.page_number,
                )
            )
        return results, total

    async def _embed_query_with_observability(
        self, user_id: uuid.UUID, query: str
    ) -> list[float]:
        """
        `NFR-OBS-001` (`observability.md` §4, read literally, same
        interpretation R3's `document_processing_service._embed_with_observability`
        already established): every embedding-provider call writes one
        `ai_requests` row (`operation="embedding"`), success and failure.
        `input_tokens` uses the query's own real token count (no chunk
        objects exist here to reuse, unlike R3's bulk-embed case);
        `output_tokens` stays `None` — embedding has no generated tokens.
        """
        input_tokens = count_tokens(query)
        status = "success"
        error_code: str | None = None
        start = time.monotonic()
        try:
            [vector] = await self._embeddings.embed_batch([query])
            return vector
        except Exception:
            status = "error"
            error_code = "embedding_failed"
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            await self._log_ai_request(
                user_id,
                status=status,
                error_code=error_code,
                input_tokens=input_tokens,
                latency_ms=latency_ms,
            )

    async def _log_ai_request(
        self,
        user_id: uuid.UUID,
        *,
        status: str,
        error_code: str | None,
        input_tokens: int,
        latency_ms: int,
    ) -> None:
        """A failure logging this row must never turn an otherwise-successful
        search into a failed request — mirrors R3's identical guard."""
        try:
            await self._ai_request_repo.create(
                user_id,
                operation="embedding",
                provider=self._embeddings.provider_name,
                model=self._embeddings.model_name,
                input_tokens=input_tokens,
                output_tokens=None,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
            )
        except Exception:  # noqa: BLE001 — best-effort logging, mirrors R3/R6/R7
            logger.warning(
                "search.ai_request_log_failed",
                extra={"user_id": str(user_id), "operation": "embedding"},
            )
