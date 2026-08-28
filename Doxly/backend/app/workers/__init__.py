"""
R12 (tasks/remediation-plan.md §15) — a real `rq worker` process never
imports `app.main` (it's started as `rq worker <queues> --url ...`,
resolving job dotted-paths like `app.workers.document_processing_worker.
process_document_job` directly), so `main.py`'s own `configure_logging("api")`
call never runs for it. Python import semantics guarantee this package's
`__init__.py` runs before any of its submodules' job functions do (RQ must
import `app.workers.<module>` to resolve the dotted job reference), which
makes this the one reliable place to configure the worker process's own
structured-JSON logging.
"""

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging("worker", settings.log_level)
