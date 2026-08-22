"""users and refresh_tokens

Prerequisite for Phase 3 (specs/roadmap.md: "Phase 1 (Phase 2's users table
must exist first)"). This repo's session series has been frontend-only
through Phases 1-2, so this migration — the schema half only, no auth
business logic/routers — is built now as genuine infrastructure Phase 3
depends on, not a re-run of Phase 2. specs/database.md §3.1-3.2.

Revision ID: 20260821_users_and_refresh_tokens
Revises:
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_users_refresh_tokens"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgcrypto (gen_random_uuid()) and citext (case-insensitive email) are
    # created in the initial migration, not left implicit — skills/database.md §4.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("oauth_provider", sa.Text(), nullable=True),
        sa.Column("oauth_provider_id", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), server_default="user", nullable=False),
        sa.Column("plan", sa.Text(), server_default="free", nullable=False),
        sa.Column(
            "storage_used_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("oauth_provider IS NULL OR oauth_provider = 'google'"),
        sa.CheckConstraint("role IN ('user', 'admin')"),
        sa.CheckConstraint("plan IN ('free', 'pro')"),
        sa.CheckConstraint("status IN ('active', 'suspended', 'pending_deletion')"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(
        "ix_users_oauth_identity",
        "users",
        ["oauth_provider", "oauth_provider_id"],
        unique=True,
        postgresql_where=sa.text("oauth_provider IS NOT NULL"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("device_label", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(
        "ix_users_oauth_identity",
        table_name="users",
        postgresql_where=sa.text("oauth_provider IS NOT NULL"),
    )
    op.drop_table("users")
    # Extensions are left in place on downgrade — dropping a shared Postgres
    # extension is a cluster-wide, high-blast-radius action unrelated to this
    # migration's own tables, and citext/pgcrypto are meant to be a durable
    # baseline, not something toggled by an app-schema downgrade.
