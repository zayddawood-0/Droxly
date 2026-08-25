import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class Conversation(
    UUIDPrimaryKeyMixin, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin, Base
):
    """specs/database.md §3.7 — a chat thread, optionally scoped to document(s)."""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('single_document','multi_document','workspace')"
        ),
        Index("ix_conversations_user_deleted", "user_id", "deleted_at"),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)


class ConversationDocument(Base):
    """specs/database.md §3.8 — join table for single-/multi-document chat scope."""

    __tablename__ = "conversation_documents"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """specs/database.md §3.9"""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')"),
        CheckConstraint("status IN ('complete','stopped','incomplete')"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized for direct tenant filtering (database.md §3.9).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # R4 — tasks/remediation-plan.md — distinguishes a normally-completed
    # assistant turn from one halted by /stop or a mid-stream failure
    # (database.md §3.9's note on this column).
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="complete")


class Citation(UUIDPrimaryKeyMixin, Base):
    """specs/database.md §3.10 — grounding record linking a message to its source chunk(s)."""

    __tablename__ = "citations"
    __table_args__ = (Index("ix_citations_message_id", "message_id"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL, not CASCADE (skills/database.md §8): a citation still records
    # a useful snippet/page reference even if its source chunk is purged.
    document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
