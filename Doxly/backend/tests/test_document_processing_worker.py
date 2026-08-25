"""
tasks/remediation-plan.md R3 — workers/document_processing_worker.py.

Real Postgres, real (committed, not this suite's usual SAVEPOINT-rollback)
rows, and genuine cleanup at the end of each test — deliberately NOT using
tests/conftest.py's `db_session` fixture here: `process_document_job` calls
`asyncio.run(...)` internally (RQ job entrypoints are plain synchronous
functions, matching a real `rq worker` process, which has no ambient event
loop of its own to share), which both (a) cannot be invoked from within an
already-running loop — so every test here is a plain sync `def`, not
`async def` — and (b) opens its own genuinely separate DB connection via a
fresh event loop, which cannot safely reuse `db_session`'s
already-open-on-a-different-loop connection/transaction. Real commits +
`asyncio.run` per phase is the correct shape for testing this specific
sync-entrypoint-wrapping-async-code boundary, not a workaround.
"""

import asyncio
import uuid

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.core.storage import LocalFilesystemStorageProvider
from app.models import Document, User
from app.repositories.document_repository import DocumentChunkRepository
from app.workers.document_processing_worker import (
    on_processing_failure,
    process_document_job,
)


def _run(coro):
    """
    Runs `coro` to completion in a fresh event loop, disposing the shared
    `engine`'s connection pool both before and after — required because
    these tests deliberately call `asyncio.run()` directly
    (process_document_job/on_processing_failure do the same, and must be
    exercised as real sync entrypoints, not from inside an already-running
    loop). Every other test module in this suite runs its DB work on
    pytest-asyncio's one session-scoped loop (pyproject.toml); the
    module-level `engine`'s pool may already hold connections opened on
    THAT loop by the time this file's tests run. Disposing before
    guarantees this file never inherits one of those; disposing after
    guarantees it never leaves one behind for a subsequent `asyncio.run()`
    call (in this file or the real worker entrypoints below) to inherit —
    asyncpg rejects reusing a connection from a different, closed loop.
    """

    async def _wrapped():
        await engine.dispose()
        result = await coro
        await engine.dispose()
        return result

    return asyncio.run(_wrapped())


def _dispose_engine_before_and_after_sync_entrypoint_call():
    """Context manager disposing the engine's pool on both sides of a real
    `process_document_job`/`on_processing_failure` call — same hazard
    `_run` handles for this test file's own coroutines (see its docstring),
    applied around the worker module's own internal `asyncio.run` calls."""

    class _Guard:
        def __enter__(self):
            asyncio.run(engine.dispose())
            return self

        def __exit__(self, *exc_info):
            asyncio.run(engine.dispose())
            return False

    return _Guard()


async def _create_user_and_document(*, mime_type="text/plain", status="queued"):
    async with async_session_factory() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            display_name="Worker Test User",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.flush()
        document = Document(
            user_id=user.id,
            file_name="notes.txt",
            storage_key=f"documents/{user.id}/{uuid.uuid4()}",
            mime_type=mime_type,
            size_bytes=100,
            checksum_sha256="a" * 64,
            status=status,
        )
        session.add(document)
        await session.commit()
        return user.id, document.id


async def _cleanup(user_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(Document).where(Document.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _fetch_document(document_id: uuid.UUID) -> Document | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()


def test_process_document_job_runs_the_full_pipeline():
    user_id, document_id = _run(_create_user_and_document())
    try:
        storage_key = _run(_fetch_document(document_id)).storage_key
        storage = LocalFilesystemStorageProvider(
            base_dir=settings.storage_local_dir,
            base_url=settings.backend_public_base_url,
        )
        storage.write_object(
            storage_key, ("A real paragraph of text content. " * 20).encode()
        )

        with _dispose_engine_before_and_after_sync_entrypoint_call():
            process_document_job(str(user_id), str(document_id))

        document = _run(_fetch_document(document_id))
        assert document.status == "ready"

        async def _chunks():
            async with async_session_factory() as session:
                return await DocumentChunkRepository(session).list_for_document(
                    user_id, document_id
                )

        chunks = _run(_chunks())
        assert len(chunks) > 0
        assert all(chunk.embedding is not None for chunk in chunks)
    finally:
        _run(_cleanup(user_id))


def test_process_document_job_unexpected_error_propagates_and_does_not_mark_failed():
    """
    A missing storage object is an unexpected exception (FileNotFoundError),
    not a DocumentParseError — process_document_job must let it propagate
    (so RQ's retry mechanism sees the failure) rather than swallowing it,
    and the document must not be left `failed` by this attempt alone
    (workers/document_processing_worker.py's on_failure callback, not the
    job function itself, is what eventually marks it failed).
    """
    user_id, document_id = _run(_create_user_and_document())
    try:
        # No object written to the configured storage_key — the real
        # LocalFilesystemStorageProvider raises FileNotFoundError reading it.
        try:
            with _dispose_engine_before_and_after_sync_entrypoint_call():
                process_document_job(str(user_id), str(document_id))
            raise AssertionError("expected process_document_job to raise")
        except FileNotFoundError:
            pass

        document = _run(_fetch_document(document_id))
        assert document.status != "failed"
    finally:
        _run(_cleanup(user_id))


def test_on_processing_failure_is_a_noop_while_retries_remain():
    from types import SimpleNamespace

    job = SimpleNamespace(should_retry=True, args=("ignored", "ignored"))
    # Must not attempt to open a DB session / touch any document — a
    # non-UUID string in args would raise if this path were reached.
    on_processing_failure(job, None, None, None, None)


def test_on_processing_failure_marks_document_failed_once_retries_are_exhausted():
    from types import SimpleNamespace

    user_id, document_id = _run(_create_user_and_document(status="extracting"))
    try:
        job = SimpleNamespace(should_retry=False, args=(str(user_id), str(document_id)))
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            on_processing_failure(job, None, None, None, None)

        document = _run(_fetch_document(document_id))
        assert document.status == "failed"
        assert document.processing_error is not None
    finally:
        _run(_cleanup(user_id))
