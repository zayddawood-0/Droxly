import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.ai.embeddings import EmbeddingProvider
from app.repositories.document_repository import (
    ChunkSearchResult,
    DocumentChunkRepository,
    DocumentRepository,
)

# rag.md §6 — default top-k differs by scope.
SINGLE_DOCUMENT_K = 8
MULTI_DOCUMENT_K = 12

# rag.md §8 point 3 — retrieval-side token budget, distinct from and smaller
# than the model's full context window (ai.md owns the overall budget).
DEFAULT_TOKEN_BUDGET = 3000

# rag.md §8 point 1 — collapse chunks with >90% content overlap.
DEDUPE_SIMILARITY_THRESHOLD = 0.9


@dataclass(frozen=True)
class ContextItem:
    """One retrieved, deduped, budget-included chunk with its provenance (rag.md §8 point 4) — everything the future Answer Generator node needs without a second lookup."""

    document_chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    content: str
    token_count: int
    similarity: float


@dataclass(frozen=True)
class AssembledContext:
    """
    rag.md §8's output: a bounded, ranked context block. An empty `items`
    list IS FR-RAG-003's retrieval-failure signal — a success path, not an
    exception (rag.md §10: "this is a success path for the system, not an
    error"). The caller (a future LangGraph node) checks `is_empty`, not a
    raised error, to route to the "cannot answer" response.
    """

    items: list[ContextItem]
    total_tokens: int

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0


class RetrievalService:
    """
    rag.md §6-8 — query processing + context assembly, the complete
    non-generative half of RAG (roadmap.md Phase 7). Ready to be called by
    a graph (Phase 8) but makes no LLM call itself.
    """

    def __init__(
        self,
        chunk_repository: DocumentChunkRepository,
        document_repository: DocumentRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._chunks = chunk_repository
        self._documents = document_repository
        self._embeddings = embedding_provider

    async def retrieve(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        document_id: uuid.UUID | None = None,
        document_ids: Sequence[uuid.UUID] | None = None,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        min_similarity: float = 0.75,
    ) -> AssembledContext:
        """
        rag.md §7's filter precedence: `user_id` always (enforced inside
        `similarity_search`), then document scope. Tag/date-range filters
        are Global Search's job (rag.md §7 point 3, Phase 13), not chat's.
        """
        [query_embedding] = await self._embeddings.embed_batch([query])

        k = SINGLE_DOCUMENT_K if document_id is not None else MULTI_DOCUMENT_K
        results = await self._chunks.similarity_search(
            user_id,
            query_embedding,
            document_id=document_id,
            document_ids=document_ids,
            k=k,
            min_similarity=min_similarity,
        )

        if not results:
            return AssembledContext(items=[], total_tokens=0)

        deduped = _dedupe(results)
        items = await self._attach_titles(user_id, deduped)
        return _trim_to_budget(items, token_budget)

    async def _attach_titles(
        self, user_id: uuid.UUID, results: list[ChunkSearchResult]
    ) -> list[ContextItem]:
        document_ids = {result.chunk.document_id for result in results}
        documents = await self._documents.get_many(user_id, list(document_ids))
        titles = {document.id: document.file_name for document in documents}
        return [
            ContextItem(
                document_chunk_id=result.chunk.id,
                document_id=result.chunk.document_id,
                document_title=titles.get(
                    result.chunk.document_id, "Untitled document"
                ),
                page_number=result.chunk.page_number,
                content=result.chunk.content,
                token_count=result.chunk.token_count,
                similarity=result.similarity,
            )
            for result in results
        ]


def _dedupe(results: list[ChunkSearchResult]) -> list[ChunkSearchResult]:
    """
    rag.md §8 point 1 — collapse chunks with >90% content overlap, keeping
    the higher-scoring one. Results arrive similarity-ordered already, so
    the first occurrence encountered for a near-duplicate is always the
    higher scorer.
    """
    kept: list[ChunkSearchResult] = []
    for result in results:
        if any(
            SequenceMatcher(None, result.chunk.content, existing.chunk.content).ratio()
            > DEDUPE_SIMILARITY_THRESHOLD
            for existing in kept
        ):
            continue
        kept.append(result)
    return kept


def _trim_to_budget(items: list[ContextItem], token_budget: int) -> AssembledContext:
    """rag.md §8 point 3 — sum token_count in relevance order, stop once the budget is reached; uses the stored token_count, never re-estimates."""
    included: list[ContextItem] = []
    running_total = 0
    for item in items:
        if included and running_total + item.token_count > token_budget:
            break
        included.append(item)
        running_total += item.token_count
    return AssembledContext(items=included, total_tokens=running_total)
