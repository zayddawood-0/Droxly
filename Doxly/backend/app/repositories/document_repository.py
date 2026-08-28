import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentTag, Tag
from app.repositories.base import TenantScopedRepository

_SORT_COLUMNS: dict[str, ColumnElement] = {
    "created_at_desc": Document.created_at.desc(),
    "created_at_asc": Document.created_at.asc(),
    "name_asc": Document.file_name.asc(),
    "size_desc": Document.size_bytes.desc(),
}


class DocumentRepository(TenantScopedRepository[Document]):
    model = Document

    async def get(self, user_id: uuid.UUID, id: uuid.UUID) -> Document | None:
        """
        Overrides the generic base — skills/backend.md §4: "soft-deletion
        ... applied inside the repository by default, not left to every
        call site to remember." A soft-deleted document must 404 exactly
        like one owned by another user (FR-DOC-005's "disappears from all
        queries immediately"), so this is the one place that guarantee is
        enforced for every caller (get/update/delete-attempt) at once.
        """
        result = await self.session.execute(
            select(Document).where(
                Document.id == id,
                Document.user_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        tag_id: uuid.UUID | None = None,
        mime_type: str | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[Sequence[Document], int]:
        """FR-DOC-002 — api.md §3's exact filter/sort surface. Returns
        (page, total) so the router can build §0.6's pagination envelope
        without a second round trip for the count."""
        base_filters = [Document.user_id == user_id, Document.deleted_at.is_(None)]
        if status is not None:
            base_filters.append(Document.status == status)
        if mime_type is not None:
            base_filters.append(Document.mime_type == mime_type)

        stmt = select(Document).where(*base_filters)
        count_stmt = select(func.count()).select_from(Document).where(*base_filters)
        if tag_id is not None:
            stmt = stmt.join(DocumentTag, DocumentTag.document_id == Document.id).where(
                DocumentTag.tag_id == tag_id
            )
            count_stmt = count_stmt.join(
                DocumentTag, DocumentTag.document_id == Document.id
            ).where(DocumentTag.tag_id == tag_id)

        stmt = stmt.order_by(_SORT_COLUMNS[sort]).limit(limit).offset(offset)

        items = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        """FR-USER-003's usage endpoint (R1) — replaces the hardcoded 0
        R1's own remediation left as a documented placeholder pending R2."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.user_id == user_id, Document.deleted_at.is_(None))
        )
        return result.scalar_one()

    async def soft_delete(self, user_id: uuid.UUID, id: uuid.UUID) -> Document | None:
        """FR-DOC-005 — the user-facing delete. Deliberately NOT the base
        class's `delete()` (a hard DELETE): the row (and its storage
        object/chunks) survive until the retention-window purge job runs,
        per privacy.md — only immediate list/search/retrieval visibility
        changes now."""
        document = await self.get(user_id, id)
        if document is None:
            return None
        document.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return document

    async def purge_for_user(self, user_id: uuid.UUID) -> list[str]:
        """
        R1 §5.1's cascade contract — FR-USER-002/FR-DOC-005's actual
        hard-delete: removes every document row for this user (chunks
        cascade via ON DELETE CASCADE, database.md §3.4). Returns the
        purged rows' storage_keys so the caller (DocumentService, per
        skills/backend.md's repository/service split — this method only
        knows about rows, never calls out to StorageProvider itself) can
        delete the corresponding storage objects.

        Callable and tested directly today; **not yet invoked by any
        scheduled job** — the actual "30 days after DELETE /users/me"
        trigger needs the RQ worker/queue infrastructure roadmap.md
        Phase 5/8 scope, which doesn't exist yet (R3, not built). This is
        the documented, honest boundary: the mechanism this method
        provides is real and tested; the scheduler that will eventually
        call it is a known, flagged gap, not silently assumed done.
        """
        result = await self.session.execute(
            select(Document.storage_key).where(Document.user_id == user_id)
        )
        storage_keys = list(result.scalars().all())
        if not storage_keys:
            return []
        await self.session.execute(delete(Document).where(Document.user_id == user_id))
        await self.session.flush()
        return storage_keys

    async def confirm_if_unconfirmed(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        checksum_sha256: str,
        size_bytes: int,
    ) -> Document | None:
        """
        Final-release-audit remediation (finding #1, self-disclosed in
        tasks/R3-document-processing.md as owned by R2) — the atomic
        compare-and-swap `confirm_upload` needs to be safe against a
        genuinely concurrent duplicate request, not just a sequential
        retry. `checksum_sha256=""` is the sentinel `presign_upload` sets
        (never a real sha256 hex digest, which is always 64 hex chars),
        so the WHERE clause below only ever matches a document that has
        never been confirmed yet.

        Postgres serializes two concurrent UPDATEs targeting the same row:
        the second transaction blocks until the first commits, then
        re-evaluates this WHERE clause against the now-already-confirmed
        row and matches zero rows — no SELECT FOR UPDATE or explicit
        locking needed, this is the standard atomic guarded-UPDATE
        pattern. A `None` return means the document was already confirmed
        (by an earlier call from this same client, or a concurrent one) —
        the caller must treat that as a no-op, not an error, so a
        double-click or client retry never double-counts
        `storage_used_bytes` or double-enqueues processing.
        """
        result = await self.session.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
                Document.deleted_at.is_(None),
                Document.checksum_sha256 == "",
            )
            .values(checksum_sha256=checksum_sha256, size_bytes=size_bytes)
            .returning(Document)
        )
        document = result.scalar_one_or_none()
        await self.session.flush()
        return document

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

    async def delete_for_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> int:
        """
        R3 — FR-PROC-005/NFR-AVAIL-002: clears every chunk row for a
        document before a (re)processing run writes a fresh set, so neither
        a manual reprocess nor an automatic retry after a partial failure
        ever leaves stale/duplicate rows behind (the (document_id,
        chunk_index) unique constraint would otherwise reject a retry's
        second bulk_create). Owner-scoped like every other write here.
        """
        result = await self.session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.user_id == user_id,
                DocumentChunk.document_id == document_id,
            )
        )
        await self.session.flush()
        # SQLAlchemy's async execute() is typed as the generic Result[Any];
        # .rowcount is real on the CursorResult a DELETE actually returns
        # at runtime, just not part of that generic type's static surface.
        return result.rowcount or 0  # type: ignore[attr-defined]

    async def list_for_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentChunk]:
        """GET /documents/{id}/content (R2) — the extracted-content viewer
        reads directly from already-chunked content (document-processing.md
        §4/§10: there is no separate raw-extracted-text column; chunks ARE
        the stored extracted content), ordered for reassembly."""
        result = await self.session.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.user_id == user_id,
                DocumentChunk.document_id == document_id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        return list(result.scalars().all())


class TagRepository(TenantScopedRepository[Tag]):
    model = Tag

    async def get_by_name(self, user_id: uuid.UUID, name: str) -> Tag | None:
        """FR-DOC-006 / api.md's 409 tag_already_exists pre-check — an
        explicit query rather than relying on the UNIQUE(user_id, name)
        constraint violation to surface as the error path."""
        result = await self.session.execute(
            select(Tag).where(Tag.user_id == user_id, Tag.name == name)
        )
        return result.scalar_one_or_none()


class DocumentTagRepository:
    """
    Join table — no user_id column of its own (specs/database.md §3.6);
    tenancy is enforced transitively through the owning document, which the
    caller must already have fetched via DocumentRepository.get(user_id, ...).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_document(
        self, document_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]
    ) -> None:
        """PATCH /documents/{id}'s "supplying tag_ids replaces the full
        tag set" (api.md §3) — caller has already validated every tag_id
        is owned by the requesting user (TagRepository.get_many)."""
        await self.session.execute(
            delete(DocumentTag).where(DocumentTag.document_id == document_id)
        )
        if tag_ids:
            self.session.add_all(
                [
                    DocumentTag(document_id=document_id, tag_id=tag_id)
                    for tag_id in tag_ids
                ]
            )
        await self.session.flush()

    async def list_tag_ids_for_document(
        self, document_id: uuid.UUID
    ) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(DocumentTag.tag_id).where(DocumentTag.document_id == document_id)
        )
        return list(result.scalars().all())

    async def list_tags_for_documents(
        self, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Tag]]:
        """GET /documents (R2) — one batched query for every document's
        tags in the current page, instead of N+1 (skills/backend.md §6's
        N+1-avoidance rule, applied here without an ORM relationship)."""
        if not document_ids:
            return {}
        result = await self.session.execute(
            select(DocumentTag.document_id, Tag)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id.in_(document_ids))
        )
        tags_by_document: dict[uuid.UUID, list[Tag]] = {
            doc_id: [] for doc_id in document_ids
        }
        for document_id, tag in result.all():
            tags_by_document[document_id].append(tag)
        return tags_by_document

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
