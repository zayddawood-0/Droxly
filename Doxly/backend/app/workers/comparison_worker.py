"""
tasks/remediation-plan.md R6 — the RQ job entrypoint for comparison
(`FR-COMP-001`), mirroring `extraction_worker.py`'s exact shape: a thin,
synchronous wrapper that opens its own session and calls the identical
service method an inline caller would (skills/backend.md §12), plus the
same per-job event-loop connection-pool disposal `document_processing_
worker.py`'s docstring documents.
"""

import asyncio
import uuid
from typing import Any

from app.ai.embeddings import get_embedding_provider
from app.ai.llm import get_llm_provider
from app.core.database import async_session_factory, engine
from app.repositories.comparison_repository import ComparisonRepository
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository
from app.services.comparison_processing_service import (
    EMPTY_COMPARISON_RESULT,
    ComparisonProcessingService,
)


def run_comparison_job(user_id: str, comparison_id: str) -> None:
    """Synchronous RQ entrypoint — see module docstring."""
    asyncio.run(_run_comparison_job_async(user_id, comparison_id))


async def _run_comparison_job_async(user_id: str, comparison_id: str) -> None:
    try:
        await _run_comparison_async(uuid.UUID(user_id), uuid.UUID(comparison_id))
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop


async def _run_comparison_async(user_id: uuid.UUID, comparison_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        service = ComparisonProcessingService(
            ComparisonRepository(session),
            DocumentChunkRepository(session),
            AiRequestRepository(session),
            get_llm_provider(),
            get_embedding_provider(),
        )
        try:
            await service.run_comparison(user_id, comparison_id)
        except Exception:
            # Same commit-before-propagate pattern as extraction_worker.py:
            # persist whatever was already flushed before re-raising for
            # RQ's own retry mechanism.
            await session.commit()
            raise
        else:
            await session.commit()


def on_comparison_failure(
    job: Any, connection: Any, exc_type: Any, exc_value: Any, traceback: Any
) -> None:
    """RQ's `on_failure` callback — runs on every failed attempt, but only
    marks the comparison `failed` once no attempts remain."""
    if job.should_retry:
        return

    user_id_str, comparison_id_str = job.args
    asyncio.run(_mark_failed_after_retries_async(user_id_str, comparison_id_str))


async def _mark_failed_after_retries_async(user_id: str, comparison_id: str) -> None:
    try:
        async with async_session_factory() as session:
            await ComparisonRepository(session).set_result(
                uuid.UUID(user_id),
                uuid.UUID(comparison_id),
                status="failed",
                result_json=dict(EMPTY_COMPARISON_RESULT),
            )
            await session.commit()
    finally:
        await engine.dispose()  # see module docstring — must run in THIS loop
