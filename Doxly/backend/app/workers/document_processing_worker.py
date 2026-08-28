"""
tasks/remediation-plan.md R3 — the RQ job entrypoint (skills/backend.md §12:
"a job function in app/workers/ is a thin wrapper: it obtains its own DB
session and repository/service instances ... then calls the identical
service method the API would call for an inline equivalent"). Business
logic (extract/chunk/embed/status transitions) lives entirely in
DocumentProcessingService — this module never duplicates it.

Retry policy (NFR-AVAIL-002): `core/queue.py` configures
`Retry(max=3, interval=[10, 30, 60])` at enqueue time. `process_document_job`
lets a transient failure propagate straight through so RQ's own retry
mechanism re-invokes it; `on_processing_failure` is RQ's `on_failure`
callback, which — per RQ's own execution order — runs on *every* failed
attempt, not only the last. It checks `job.should_retry` itself and only
marks the document `failed` once no attempts remain, so a document is never
flashed to `failed` and back mid-retry.

**Engine disposal, found by a live smoke test, not by the (per-test-fresh-
process) pytest suite:** a real `rq worker` process handles many jobs
sequentially in one long-lived Python process. Each job here runs inside
its own `asyncio.run(...)` (a fresh event loop per job — RQ itself is
synchronous and has no ambient loop to reuse). `app.core.database.engine`'s
connection pool is a process-wide singleton that, left alone, hands the
*next* job's `asyncio.run()` a connection object still bound to the
*previous* job's already-closed loop — asyncpg rejects this outright
(observed live: the second job in a worker's lifetime failed with
"attached to a different loop" / a proactor `AttributeError` on Windows).
Both entrypoints below therefore dispose the pool as the last thing they do
inside their own loop, before it closes — cheap (one job every few seconds
at most; a new physical connection costs a few ms) and guarantees the next
job, whichever entrypoint it uses, never inherits a connection from a dead
loop.
"""

import asyncio
import logging
import uuid
from typing import Any

from app.ai.embeddings import get_embedding_provider
from app.core.database import async_session_factory, engine
from app.core.storage import get_storage_provider
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.repositories.observability_repository import AiRequestRepository
from app.services.document_processing_service import DocumentProcessingService
from app.workers._observability import (
    log_job_completed,
    log_job_failed,
    log_job_started,
)

logger = logging.getLogger(__name__)

_JOB_TYPE = "document_processing"

_TRANSIENT_FAILURE_MESSAGE = (
    "A temporary error occurred while processing this document. "
    "Please try reprocessing it."
)


def process_document_job(user_id: str, document_id: str) -> None:
    """
    Synchronous RQ entrypoint — RQ workers invoke job functions
    synchronously (skills/backend.md §13's async-everywhere rule applies to
    the API process; the worker process is a different runtime with no
    ambient event loop of its own to reuse), so this bridges into the async
    service layer with a fresh event loop per job.
    """
    asyncio.run(_process_document_job_async(user_id, document_id))


async def _process_document_job_async(user_id: str, document_id: str) -> None:
    start = log_job_started(logger, _JOB_TYPE, document_id=document_id)
    try:
        await _process_document_async(uuid.UUID(user_id), uuid.UUID(document_id))
    except Exception:
        log_job_failed(logger, _JOB_TYPE, start, document_id=document_id)
        raise
    else:
        log_job_completed(logger, _JOB_TYPE, start, document_id=document_id)
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop


async def _process_document_async(user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        service = DocumentProcessingService(
            DocumentRepository(session),
            DocumentChunkRepository(session),
            get_storage_provider(),
            get_embedding_provider(),
            AiRequestRepository(session),
        )
        try:
            await service.process_document(user_id, document_id)
        except Exception:
            # Persist whatever status/partial state was already flushed
            # (e.g. status='extracting') before re-raising for RQ's retry
            # mechanism — mirrors core/database.py's own
            # commit-before-propagate pattern for an expected mid-flight
            # exception, not a rollback that would discard it.
            await session.commit()
            raise
        else:
            await session.commit()


def on_processing_failure(
    job: Any, connection: Any, exc_type: Any, exc_value: Any, traceback: Any
) -> None:
    if job.should_retry:
        return  # more attempts remain — RQ has already scheduled the retry.

    user_id_str, document_id_str = job.args
    asyncio.run(_mark_failed_after_retries_async(user_id_str, document_id_str))


async def _mark_failed_after_retries_async(user_id: str, document_id: str) -> None:
    try:
        async with async_session_factory() as session:
            await DocumentRepository(session).set_status(
                uuid.UUID(user_id),
                uuid.UUID(document_id),
                status="failed",
                processing_error=_TRANSIENT_FAILURE_MESSAGE,
            )
            await session.commit()
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop
