import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Comparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """specs/database.md §3.12 — result of comparing two documents (FR-COMP-*)."""

    __tablename__ = "comparisons"
    __table_args__ = (
        CheckConstraint("status IN ('processing','completed','failed')"),
        CheckConstraint(
            "document_a_id <> document_b_id", name="ck_comparisons_distinct_documents"
        ),
        Index("ix_comparisons_user_created", "user_id", "created_at"),
        Index("ix_comparisons_document_a", "document_a_id"),
        Index("ix_comparisons_document_b", "document_b_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    document_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="completed"
    )
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
