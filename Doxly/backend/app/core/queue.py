"""
tasks/remediation-plan.md R3 — decisions.md ADR-008's Redis + RQ background
job infrastructure, actually wired up for the first time. The one place a
document-processing job gets enqueued from — skills/backend.md §12: "when a
service method determines an operation belongs on the queued side of the
inline-vs-queued line, it calls the Redis/RQ enqueue helper ... never a
serialized ORM object or an open DB session."
"""

import logging
import uuid

import redis
from rq import Queue, Retry
from rq.job import Callback

from app.core.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_PROCESSING_QUEUE_NAME = "document_processing"

# NFR-AVAIL-002 — up to 3 attempts, exponential-ish backoff, for a
# transient failure (app/workers/document_processing_worker.py is what
# actually distinguishes transient from permanent parse failures; only the
# former ever re-raises into this retry policy).
_MAX_RETRIES = 3
_RETRY_INTERVALS_SECONDS = [10, 30, 60]

# A separate, synchronous redis-py connection from core/rate_limit.py's
# async one (redis.asyncio) — RQ's own API is synchronous end-to-end (it is
# designed to be driven by a plain `rq worker` process), so this connection
# is never shared with the async rate-limiter client.
redis_connection = redis.Redis.from_url(settings.redis_url)


def get_document_processing_queue() -> Queue:
    return Queue(DOCUMENT_PROCESSING_QUEUE_NAME, connection=redis_connection)


def enqueue_document_processing(user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """
    FR-PROC-001's trigger — called once a document is confirmed `queued`
    (DocumentService.confirm_upload) or reset to `queued` for a manual
    retry (DocumentService.reprocess_document, FR-PROC-005). Arguments are
    plain values (str-ified UUIDs), never a serialized ORM object or an
    open DB session (skills/backend.md §12) — the worker (workers/
    document_processing_worker.py) opens its own session.

    decisions.md ADR-023 — fails open on a Redis outage (mirrors ADR-021's
    rate-limiter precedent, NFR-AVAIL-001): a document is left `queued`
    with no job enqueued rather than the confirm/reprocess request itself
    failing with a 500. The warning below is what makes that operationally
    visible rather than a silent gap.
    """
    try:
        queue = get_document_processing_queue()
        queue.enqueue(
            "app.workers.document_processing_worker.process_document_job",
            str(user_id),
            str(document_id),
            retry=Retry(max=_MAX_RETRIES, interval=_RETRY_INTERVALS_SECONDS),
            on_failure=Callback(
                "app.workers.document_processing_worker.on_processing_failure"
            ),
        )
    except redis.RedisError:
        logger.warning(
            "document_processing.enqueue_failed",
            extra={"user_id": str(user_id), "document_id": str(document_id)},
        )


# --- R5 (tasks/remediation-plan.md) — extraction ---

EXTRACTION_QUEUE_NAME = "extraction"


def get_extraction_queue() -> Queue:
    return Queue(EXTRACTION_QUEUE_NAME, connection=redis_connection)


def enqueue_extraction(user_id: uuid.UUID, extraction_id: uuid.UUID) -> None:
    """
    FR-EXT-001's trigger — called once `ExtractionService.create_extraction`
    has persisted the initial `extractions` row (`status='processing'`),
    mirroring `enqueue_document_processing`'s exact shape: plain str-ified
    UUID args, the same job-level `Retry`/`on_failure` resilience pattern
    (a worker crash mid-job is the same operational reality here as it is
    for document processing), and the same ADR-023 fail-open behavior on a
    Redis outage (a document is left `queued`/an extraction is left
    `processing` with no job enqueued, rather than the request itself
    failing with a 500 — operationally visible via the warning below, not
    a silent gap).
    """
    try:
        queue = get_extraction_queue()
        queue.enqueue(
            "app.workers.extraction_worker.run_extraction_job",
            str(user_id),
            str(extraction_id),
            retry=Retry(max=_MAX_RETRIES, interval=_RETRY_INTERVALS_SECONDS),
            on_failure=Callback("app.workers.extraction_worker.on_extraction_failure"),
        )
    except redis.RedisError:
        logger.warning(
            "extraction.enqueue_failed",
            extra={"user_id": str(user_id), "extraction_id": str(extraction_id)},
        )


# --- R6 (tasks/remediation-plan.md) — comparison ---

COMPARISON_QUEUE_NAME = "comparison"


def get_comparison_queue() -> Queue:
    return Queue(COMPARISON_QUEUE_NAME, connection=redis_connection)


def enqueue_comparison(user_id: uuid.UUID, comparison_id: uuid.UUID) -> None:
    """FR-COMP-001's trigger — mirrors `enqueue_extraction`'s exact shape
    (same job-level `Retry`/`on_failure` resilience, same ADR-023 fail-open
    behavior on a Redis outage)."""
    try:
        queue = get_comparison_queue()
        queue.enqueue(
            "app.workers.comparison_worker.run_comparison_job",
            str(user_id),
            str(comparison_id),
            retry=Retry(max=_MAX_RETRIES, interval=_RETRY_INTERVALS_SECONDS),
            on_failure=Callback("app.workers.comparison_worker.on_comparison_failure"),
        )
    except redis.RedisError:
        logger.warning(
            "comparison.enqueue_failed",
            extra={"user_id": str(user_id), "comparison_id": str(comparison_id)},
        )
