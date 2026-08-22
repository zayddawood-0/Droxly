import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin, Base):
    """specs/database.md §3.1 — account identity, plan, and auth credentials."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("oauth_provider IS NULL OR oauth_provider = 'google'"),
        CheckConstraint("role IN ('user', 'admin')"),
        CheckConstraint("plan IN ('free', 'pro')"),
        CheckConstraint("status IN ('active', 'suspended', 'pending_deletion')"),
        Index(
            "ix_users_oauth_identity",
            "oauth_provider",
            "oauth_provider_id",
            unique=True,
            postgresql_where="oauth_provider IS NOT NULL",
        ),
    )

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_provider_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    storage_used_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """specs/database.md §3.2 — session/device management (FR-AUTH-008) and revocation."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
