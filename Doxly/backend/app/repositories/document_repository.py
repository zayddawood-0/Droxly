import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentTag, Tag
from app.repositories.base import TenantScopedRepository


class DocumentRepository(TenantScopedRepository[Document]):
    model = Document

    async def set_status(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        status: str,
        processing_error: str | None = None,
    ) -> Document | None:
        """FR-PROC-003/004's status-transition point — owner-scoped like every other write here."""
        document = await self.get(user_id, document_id)
        if document is None:
            return None
        document.status = status
        document.processing_error = processing_error
        await self.session.flush()
        return document


@dataclass(frozen=True)
class ChunkSearchResult:
    """Typed result (skills/backend.md §4 — never a bare Row/tuple) pairing a chunk with its query-time similarity score."""

    chunk: DocumentChunk
    similarity: float


class DocumentChunkRepository(TenantScopedRepository[DocumentChunk]):
    """Generic CRUD from the base class, plus the domain-specific bulk insert and pgvector similarity search this phase (6) is the first to need."""

    model = DocumentChunk

    async def bulk_create(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[dict],
    ) -> list[DocumentChunk]:
        """One insert per chunk row for a just-embedded document — chunk dicts carry every DocumentChunk field except user_id/document_id."""
        instances = [
            DocumentChunk(user_id=user_id, document_id=document_id, **chunk)
            for chunk in chunks
        ]
        self.session.add_all(instances)
        await self.session.flush()
        return instances

    async def similarity_search(
        self,
        user_id: uuid.UUID,
        query_embedding: list[float],
        *,
        document_id: uuid.UUID | None = None,
        document_ids: Sequence[uuid.UUID] | None = None,
        k: int = 8,
        min_similarity: float = 0.75,
    ) -> list[ChunkSearchResult]:
        """
        rag.md §6's canonical query, verbatim: HNSW-indexed cosine distance
        (`<=>`, via pgvector's `.cosine_distance()`, matching the index's
        `vector_cosine_ops`), tenant-filtered on the denormalized `user_id`
        with no join back to `documents` (performance.md §6 — the join-free
        design the denormalization exists for). Results below
        `min_similarity` are discarded here per rag.md §6's relevance
        threshold; routing a zero-result set to a "can't answer" response is
        the caller's concern (rag.md §10), not this method's.

        `document_id` scopes to a single document (rag.md §7 point 2,
        single-document chat); `document_ids` scopes to a set (multi-document
        chat) — a caller passes at most one of the two.
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        similarity = 1 - distance

        stmt = (
            select(DocumentChunk, similarity.label("similarity"))
            .where(DocumentChunk.user_id == user_id)
            .where(similarity >= min_similarity)
            .order_by(distance.asc())
            .limit(k)
        )
        if document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == document_id)
        elif document_ids is not None:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        result = await self.session.execute(stmt)
        return [
            ChunkSearchResult(chunk=row[0], similarity=row[1]) for row in result.all()
        ]


class TagRepository(TenantScopedRepository[Tag]):
    model = Tag


class DocumentTagRepository:
    """
    Join table — no user_id column of its own (specs/database.md §3.6);
    tenancy is enforced transitively through the owning document, which the
    caller must already have fetched via DocumentRepository.get(user_id, ...).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tag_ids_for_document(
        self, document_id: uuid.UUID
    ) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(DocumentTag.tag_id).where(DocumentTag.document_id == document_id)
        )
        return list(result.scalars().all())

    async def add(self, document_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        self.session.add(DocumentTag(document_id=document_id, tag_id=tag_id))
        await self.session.flush()

    async def remove(self, document_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(DocumentTag).where(
                DocumentTag.document_id == document_id, DocumentTag.tag_id == tag_id
            )
        )
        await self.session.flush()
