import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Extraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """specs/database.md §3.11 — result of a structured extraction run (FR-EXT-*)."""

    __tablename__ = "extractions"
    __table_args__ = (
        CheckConstraint("status IN ('processing','completed','failed')"),
        Index("ix_extractions_user_document", "user_id", "document_id"),
        Index("ix_extractions_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # R5: both columns actually hold a JSON *array* of per-field dicts
    # (api.md §6: `schema?: [{...}]`, `result: [{...}]`) — `list[dict]`,
    # not a single JSON object, corrected from the original scaffold's
    # `Mapped[dict]` (JSONB itself is shape-agnostic; only the Python-side
    # type hint was wrong).
    schema_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="completed"
    )
