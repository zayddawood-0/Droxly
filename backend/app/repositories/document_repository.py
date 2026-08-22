import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentTag, Tag
from app.repositories.base import TenantScopedRepository


class DocumentRepository(TenantScopedRepository[Document]):
    model = Document


class DocumentChunkRepository(TenantScopedRepository[DocumentChunk]):
    """
    Generic CRUD only. The tenant-filtered pgvector similarity search
    (specs/rag.md §6's canonical query) is deliberately not scaffolded here —
    it's added in Phase 6/7 (Embeddings & RAG), the phase that actually
    consumes it, per skills/ai-engineering.md's "one shared, tenant-filtered
    retrieval function" rule (never reinvented per call site).
    """

    model = DocumentChunk


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
