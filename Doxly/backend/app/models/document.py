import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)

# Embedding dimension per decisions.md ADR-012/OQ-03 default (OpenAI
# text-embedding-3-small) — an implementation parameter, not product logic
# (rag.md §5): a provider swap requires a new column/table + backfill, not a
# silent change here.
EMBEDDING_DIMENSIONS = 1536


class Document(
    UUIDPrimaryKeyMixin, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin, Base
):
    """specs/database.md §3.3 — uploaded file metadata + processing state."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "mime_type IN ("
            "'application/pdf',"
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document',"
            "'text/plain','text/csv')"
        ),
        CheckConstraint(
            "status IN ('queued','extracting','chunking','embedding','ready','failed')"
        ),
        Index("ix_documents_user_deleted", "user_id", "deleted_at"),
        Index("ix_documents_user_status", "user_id", "status"),
        Index("ix_documents_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text_available: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """specs/database.md §3.4 — retrieval unit for RAG: chunked text + embedding vector."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("ix_document_chunks_user_id", "user_id"),
        # HNSW hand-authored in the migration (skills/database.md §4) —
        # Alembic autogenerate cannot produce it; declared here only for
        # ORM-level awareness, not relied on to create the index itself.
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized from documents.user_id (database.md §3.4 note) so the
    # pgvector query filters WHERE user_id = :user_id without a join
    # (NFR-PERF-005). Kept in sync at insert time only — never updated
    # independently.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    embedding_model: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="text-embedding-3-small"
    )


class Tag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """specs/database.md §3.5"""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentTag(Base):
    """specs/database.md §3.6 — join table."""

    __tablename__ = "document_tags"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
