import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import Citation
from app.repositories.conversation_repository import CitationRepository
from app.services.retrieval_service import ContextItem


@dataclass(frozen=True)
class CitationInput:
    """
    What the (future, Phase 8) Citation Validator node hands this service
    once it has decided which retrieved item actually supports a specific
    claim. `snippet` is caller-supplied — deciding the focused excerpt
    within a chunk that backs a claim is generation-time logic (rag.md §9:
    "the specific text span supporting the claim"), not this service's job;
    this service only persists the resulting rows correctly.
    """

    document_chunk_id: uuid.UUID | None
    document_id: uuid.UUID
    page_number: int | None
    snippet: str
    relevance_score: float | None


class CitationService:
    """
    rag.md §9's citation model, roadmap.md Phase 7's "citations table
    population logic" — the persistence mechanism, not the claim-to-snippet
    decision (Phase 8's Citation Validator node). `Citation.message_id` is
    NOT NULL, so this service takes an already-created message_id as a
    parameter rather than owning conversation/message creation, which is
    Chat's (Phase 9's) responsibility — the same "take the missing
    upstream stage as an input parameter" pattern Phase 6's EmbeddingService
    used for text extraction.
    """

    def __init__(self, citation_repository: CitationRepository) -> None:
        self._citations = citation_repository

    async def record_citations(
        self, message_id: uuid.UUID, citations: Sequence[CitationInput]
    ) -> list[Citation]:
        return [
            await self._citations.create(
                message_id=message_id,
                document_chunk_id=citation.document_chunk_id,
                document_id=citation.document_id,
                page_number=citation.page_number,
                snippet=citation.snippet,
                relevance_score=citation.relevance_score,
            )
            for citation in citations
        ]

    @staticmethod
    def citation_input_from_context_item(
        item: ContextItem, *, snippet: str | None = None
    ) -> CitationInput:
        """Convenience for citing an item's full chunk content as-is — a reasonable default until Phase 8 has real per-claim snippet selection."""
        return CitationInput(
            document_chunk_id=item.document_chunk_id,
            document_id=item.document_id,
            page_number=item.page_number,
            snippet=snippet if snippet is not None else item.content,
            relevance_score=item.similarity,
        )
