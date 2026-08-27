"""search tsvector + GIN indexes (R8 — Global Search)

tasks/remediation-plan.md R8 / specs/database.md §11.1 — adds the
generated `search_vector` columns rag.md §12's Hybrid Search needs:
`document_chunks.search_vector` (from `content`, chunk-level full-text
matches) and `documents.search_vector` (from `file_name`, filename
matches). Both are `GENERATED ALWAYS ... STORED` so they stay
automatically in sync with their source column with no application-level
maintenance, and both get a GIN index (the standard index type for
`tsvector` columns — HNSW is pgvector-specific and irrelevant here).

`documents.search_vector` strips non-alphanumeric characters to spaces
before tokenizing, rather than feeding `file_name` to `to_tsvector` as-is:
Postgres's default parser classifies a `word.ext`-shaped string as a single
"file" token and does not decompose it, so `to_tsvector('english',
'invoice-march.pdf')` produces exactly one lexeme — `'invoice-march.pdf'`,
never `'invoic'`/`'march'` — and a search for "invoice" would never match
it. Verified directly against a live Postgres instance before choosing this
expression (`skills/database.md` §5's migration-authoring convention).

Hand-authored (skills/database.md §4 — autogenerate cannot express a
generated column or a GIN index on its own).

Revision ID: 0004_search_tsvector
Revises: 0003_messages_status
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_search_tsvector"
down_revision: str | Sequence[str] | None = "0003_messages_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )

    op.add_column(
        "documents",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', regexp_replace(file_name, '[^a-zA-Z0-9]+', ' ', 'g'))",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_documents_search_vector",
        "documents",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_documents_search_vector", table_name="documents")
    op.drop_column("documents", "search_vector")
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    op.drop_column("document_chunks", "search_vector")
