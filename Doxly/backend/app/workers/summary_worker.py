"""
tasks/remediation-plan.md R7 — the RQ job entrypoint for summarization
(`FR-SUM-001`), mirroring `extraction_worker.py`/`comparison_worker.py`'s
exact shape: a thin, synchronous wrapper that opens its own session and
calls the identical service method an inline caller would (skills/
backend.md §12), plus the same per-job event-loop connection-pool
disposal `document_processing_worker.py`'s docstring documents.
"""

import asyncio
import uuid
from typing import Any

from app.ai.llm import get_llm_provider
from app.core.database import async_session_factory, engine
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.summary_repository import DocumentSummaryRepository
from app.services.summary_processing_service import SummaryProcessingService


def run_summary_job(user_id: str, summary_id: str) -> None:
    """Synchronous RQ entrypoint — see module docstring."""
    asyncio.run(_run_summary_job_async(user_id, summary_id))


async def _run_summary_job_async(user_id: str, summary_id: str) -> None:
    try:
        await _run_summary_async(uuid.UUID(user_id), uuid.UUID(summary_id))
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop


async def _run_summary_async(user_id: uuid.UUID, summary_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        service = SummaryProcessingService(
            DocumentSummaryRepository(session),
            DocumentChunkRepository(session),
            AiRequestRepository(session),
            get_llm_provider(),
        )
        try:
            await service.run_summary(user_id, summary_id)
        except Exception:
            # Same commit-before-propagate pattern as extraction_worker.py/
            # comparison_worker.py: persist whatever was already flushed
            # before re-raising for RQ's own retry mechanism.
            await session.commit()
            raise
        else:
            await session.commit()


def on_summary_failure(
    job: Any, connection: Any, exc_type: Any, exc_value: Any, traceback: Any
) -> None:
    """RQ's `on_failure` callback — runs on every failed attempt, but only
    marks the summary `failed` once no attempts remain."""
    if job.should_retry:
        return

    user_id_str, summary_id_str = job.args
    asyncio.run(_mark_failed_after_retries_async(user_id_str, summary_id_str))


async def _mark_failed_after_retries_async(user_id: str, summary_id: str) -> None:
    try:
        async with async_session_factory() as session:
            await DocumentSummaryRepository(session).set_result(
                uuid.UUID(user_id),
                uuid.UUID(summary_id),
                status="failed",
                content=None,
            )
            await session.commit()
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop
