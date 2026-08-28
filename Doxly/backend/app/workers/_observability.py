"""
R12 (tasks/remediation-plan.md §15, observability.md §3's "Job start /
complete / fail" row) — shared job-lifecycle logging for the four RQ
entrypoints in this package. Each `job_type` (`document_processing`/
`extraction`/`comparison`/`summary`) previously logged nothing at all
about a job's own execution (only the persisted `status`/`*_error` DB
columns reflected outcome) — this closes that gap once, here, rather than
four times with drifting field names.
"""

import logging
import sys
import time
from typing import Any

from rq import get_current_job


def _job_context() -> tuple[str | None, int | None]:
    """`(job_id, retries_left)` from RQ's own current-job context, or
    `(None, None)` outside a real `rq worker` process — e.g. every
    existing `test_*_worker.py` file, which calls these job entrypoints
    directly rather than through a real queue (see those files' own
    docstrings for why)."""
    job = get_current_job()
    if job is None:
        return None, None
    return job.id, job.retries_left


def log_job_started(logger: logging.Logger, job_type: str, **fields: Any) -> float:
    job_id, _ = _job_context()
    logger.info("job.started", extra={"job_id": job_id, "job_type": job_type, **fields})
    return time.monotonic()


def log_job_completed(
    logger: logging.Logger, job_type: str, start: float, **fields: Any
) -> None:
    job_id, _ = _job_context()
    logger.info(
        "job.completed",
        extra={
            "job_id": job_id,
            "job_type": job_type,
            "status": "success",
            "duration_ms": int((time.monotonic() - start) * 1000),
            **fields,
        },
    )


def log_job_failed(
    logger: logging.Logger, job_type: str, start: float, **fields: Any
) -> None:
    """Must be called from within an `except Exception:` block — captures
    `sys.exc_info()` explicitly (rather than passing `exc_info=True`,
    which relies on the same ambient state one function-call removed) so
    the stack trace really is included, per observability.md §3's
    "exception type and internal stack trace (server-side only)"."""
    job_id, retries_left = _job_context()
    logger.error(
        "job.failed",
        exc_info=sys.exc_info(),
        extra={
            "job_id": job_id,
            "job_type": job_type,
            "status": "error",
            "duration_ms": int((time.monotonic() - start) * 1000),
            "retry_count": retries_left,
            **fields,
        },
    )
