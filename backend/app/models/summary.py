import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DocumentSummary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    specs/database.md §6's "Open Item": implied by FR-SUM-001/002 but not in
    the brief's minimum table list. Resolved there as a necessary, minimal
    addition — same shape/isolation pattern as `extractions` — rather than
    overloading `extractions` with a different JSON shape. Field shape
    mirrors specs/api.md's GET /summaries/{id} response exactly.
    """

    __tablename__ = "document_summaries"
    __table_args__ = (
        CheckConstraint("summary_type IN ('brief','detailed','bullet_points')"),
        CheckConstraint("status IN ('processing','completed','failed')"),
        Index("ix_document_summaries_user_document", "user_id", "document_id"),
        Index("ix_document_summaries_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="processing"
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
