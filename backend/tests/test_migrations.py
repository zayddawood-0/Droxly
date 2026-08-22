import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text

from app.core.database import engine
from app.models import Base

EXPECTED_TABLES = {
    "users",
    "refresh_tokens",
    "documents",
    "document_chunks",
    "tags",
    "document_tags",
    "conversations",
    "conversation_documents",
    "messages",
    "citations",
    "extractions",
    "comparisons",
    "document_summaries",
    "ai_requests",
    "audit_logs",
}


async def test_schema_matches_database_md_table_list():
    """Acceptance criterion: schema matches specs/database.md exactly."""

    def _table_names(sync_conn):
        return set(inspect(sync_conn).get_table_names())

    async with engine.connect() as conn:
        actual = await conn.run_sync(_table_names)

    assert EXPECTED_TABLES <= actual
    # SQLAlchemy's own metadata (app/models) must also agree with the schema
    # the migrations actually produced — catches a model/migration drift.
    assert EXPECTED_TABLES == set(Base.metadata.tables.keys())


async def test_document_chunks_has_hnsw_cosine_index():
    """specs/database.md §4 — HNSW with vector_cosine_ops, hand-authored (not autogenerate-able)."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'document_chunks' AND indexname = 'ix_document_chunks_embedding_hnsw'"
            )
        )
        row = result.first()

    assert row is not None, "HNSW index on document_chunks.embedding is missing"
    assert "USING hnsw" in row[0]
    assert "vector_cosine_ops" in row[0]


def test_migration_upgrade_and_downgrade_round_trip():
    """
    Acceptance criterion: `alembic upgrade head` / `downgrade base` both
    succeed cleanly on a fresh DB (specs/roadmap.md Phase 3 Definition of
    Done). Run as a subprocess against the same DATABASE_URL this test
    session uses, then restored to head so the rest of the suite (which
    assumes the schema exists) is unaffected.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    env_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://doxly:doxly@localhost:5432/doxly"
    )
    env = {**os.environ, "DATABASE_URL": env_url}

    def run_alembic(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    downgrade = run_alembic("downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr

    upgrade = run_alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
