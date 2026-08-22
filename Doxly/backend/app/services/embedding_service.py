import uuid

from app.ai.embeddings import EmbeddingProvider
from app.document_processing.chunking import chunk_text
from app.errors import EmptyDocumentError
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)


class EmbeddingService:
    """
    Orchestrates rag.md's Indexing pipeline from already-extracted text
    through to a `ready` document: chunk -> embed -> persist -> status
    transition (FR-PROC-002/003). Text extraction itself (FR-PROC-001,
    document-processing.md) is a separate stage this service takes as an
    input, not a responsibility it owns — whichever caller eventually
    performs extraction (the Phase 5 backend worker, not yet built) hands
    this service the resulting plain text.

    Constructor-injected repositories/provider (skills/backend.md §7) so
    this is unit-testable with a fake provider and real or faked
    repositories, independent of the full FastAPI dependency graph.
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

    async def process_extracted_text(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        full_text: str,
        *,
        page_breaks: list[int] | None = None,
    ) -> int:
        """
        Returns the number of chunks created. Raises EmptyDocumentError on
        the degenerate zero-chunk case (rag.md §2) — recording
        `documents.status='failed'` for that case is FR-PROC-004's job,
        owned by the caller, not this method.
        """
        text_chunks = chunk_text(full_text, page_breaks=page_breaks)
        if not text_chunks:
            raise EmptyDocumentError(document_id)

        vectors = await self._embeddings.embed_batch([c.content for c in text_chunks])

        await self._chunks.bulk_create(
            user_id,
            document_id,
            [
                {
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "token_count": chunk.token_count,
                    "embedding": vector,
                    "embedding_model": self._embeddings.model_name,
                }
                for chunk, vector in zip(text_chunks, vectors, strict=True)
            ],
        )

        await self._documents.set_status(user_id, document_id, status="ready")
        return len(text_chunks)
