"""messages.status column (R4 chat)

tasks/remediation-plan.md R4 — specs/database.md §3.9 gap closed alongside
this migration (CLAUDE.md §4/§6): api.md's stop/error SSE behavior requires
distinguishing a normally-completed assistant message from one that was
user-stopped or cut short by a mid-stream failure, which the messages table
had no column for. Backfills every existing row to 'complete' (the
default), which is correct for all pre-R4 data since no stop/error path
existed before this task to have produced anything else.

Revision ID: 0003_messages_status
Revises: 0002_phase3_schema
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_messages_status"
down_revision: str | Sequence[str] | None = "0002_phase3_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("status", sa.Text(), server_default="complete", nullable=False),
    )
    op.create_check_constraint(
        "messages_status_check",
        "messages",
        "status IN ('complete','stopped','incomplete')",
    )


def downgrade() -> None:
    op.drop_constraint("messages_status_check", "messages", type_="check")
    op.drop_column("messages", "status")
