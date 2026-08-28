"""
tasks/remediation-plan.md R5 — the RQ job entrypoint for extraction
(`FR-EXT-001`), mirroring `document_processing_worker.py`'s exact shape:
a thin, synchronous wrapper that opens its own session and calls the
identical service method an inline caller would (skills/backend.md §12),
plus the same per-job event-loop connection-pool disposal that module's
docstring documents (a real `rq worker` process runs many jobs sequentially
in one long-lived Python process; each job here gets its own fresh
`asyncio.run()` event loop, and the shared engine's pool must not hand the
next job a connection still bound to this job's already-closed loop).
"""

import asyncio
import logging
import uuid
from typing import Any

from app.ai.embeddings import get_embedding_provider
from app.ai.llm import get_llm_provider
from app.core.database import async_session_factory, engine
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.observability_repository import AiRequestRepository
from app.services.extraction_processing_service import ExtractionProcessingService
from app.services.retrieval_service import RetrievalService
from app.workers._observability import (
    log_job_completed,
    log_job_failed,
    log_job_started,
)

logger = logging.getLogger(__name__)

_JOB_TYPE = "extraction"


def run_extraction_job(user_id: str, extraction_id: str) -> None:
    """Synchronous RQ entrypoint — see module docstring."""
    asyncio.run(_run_extraction_job_async(user_id, extraction_id))


async def _run_extraction_job_async(user_id: str, extraction_id: str) -> None:
    start = log_job_started(logger, _JOB_TYPE, extraction_id=extraction_id)
    try:
        await _run_extraction_async(uuid.UUID(user_id), uuid.UUID(extraction_id))
    except Exception:
        log_job_failed(logger, _JOB_TYPE, start, extraction_id=extraction_id)
        raise
    else:
        log_job_completed(logger, _JOB_TYPE, start, extraction_id=extraction_id)
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop


async def _run_extraction_async(user_id: uuid.UUID, extraction_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        embedding_provider = get_embedding_provider()
        document_repo = DocumentRepository(session)
        retrieval_service = RetrievalService(
            DocumentChunkRepository(session), document_repo, embedding_provider
        )
        service = ExtractionProcessingService(
            ExtractionRepository(session),
            AiRequestRepository(session),
            get_llm_provider(),
            retrieval_service,
        )
        try:
            await service.run_extraction(user_id, extraction_id)
        except Exception:
            # Same commit-before-propagate pattern as
            # document_processing_worker.py: persist whatever was already
            # flushed before re-raising for RQ's own retry mechanism.
            await session.commit()
            raise
        else:
            await session.commit()


def on_extraction_failure(
    job: Any, connection: Any, exc_type: Any, exc_value: Any, traceback: Any
) -> None:
    """RQ's `on_failure` callback — runs on every failed attempt (RQ's own
    execution order), but only marks the extraction `failed` once no
    attempts remain, so it's never flashed to `failed` mid-retry."""
    if job.should_retry:
        return

    user_id_str, extraction_id_str = job.args
    asyncio.run(_mark_failed_after_retries_async(user_id_str, extraction_id_str))


async def _mark_failed_after_retries_async(user_id: str, extraction_id: str) -> None:
    try:
        async with async_session_factory() as session:
            await ExtractionRepository(session).set_result(
                uuid.UUID(user_id),
                uuid.UUID(extraction_id),
                status="failed",
                result_json=[],
            )
            await session.commit()
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop
