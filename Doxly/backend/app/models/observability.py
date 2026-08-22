import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AiRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    specs/database.md §3.13 — observability + cost/rate-limit accounting.
    Never stores prompt/response content (specs/observability.md §1/§4).
    """

    __tablename__ = "ai_requests"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('chat','summarization','extraction','comparison','embedding')"
        ),
        CheckConstraint("status IN ('success','error','timeout')"),
        Index("ix_ai_requests_user_created", "user_id", "created_at"),
        Index("ix_ai_requests_created", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    specs/database.md §3.14 — security-relevant event trail. Records WHAT
    happened, never document/chat CONTENT (specs/security.md §12).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
