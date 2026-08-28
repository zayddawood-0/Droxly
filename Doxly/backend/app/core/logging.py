"""
R12 (tasks/remediation-plan.md §15, observability.md §2) — structured JSON
logging, one object per line, across the API and worker services. Every
existing `logger.warning/info/error(...)` call site in this codebase
already passes an `event`-shaped message plus allow-listed `extra={...}`
fields (e.g. `core/rate_limit.py`'s `"rate_limit.redis_unavailable"` +
`extra={"key_prefix": ...}`) — the gap this module closes is purely at the
formatter/handler layer (previously unconfigured, so INFO logs were
silently dropped and WARNING+ printed in Python's bare default format, no
JSON structure at all). No call site needed to change.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# observability.md §2.2 — correlation across services via one request_id,
# read by the request-lifecycle middleware (main.py) and by any log call
# made while handling that request; a worker job sets its own (see
# workers/*.py's own entrypoints) since it has no HTTP request of its own.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# Attributes stdlib LogRecord always carries — anything else on the record
# is a caller-supplied `extra={...}` field and belongs in the JSON payload
# verbatim (observability.md §2.1's "allow-listed fields" — the allow-list
# is enforced by each call site choosing what to pass as `extra`, not by
# this formatter, which only decides *how* to emit whatever was given).
_STANDARD_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """observability.md §2.1's minimum field set, one JSON object per line."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            # Server-side only (observability.md §3's "Unhandled exception"
            # row) -- never returned to the client; NFR-SEC-009 governs the
            # *response*, not this log line.
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(service: str, level: str = "info") -> None:
    """
    Called once at process startup — `main.py` for the API, each worker
    entrypoint's own `if __name__ == "__main__"` for a standalone `rq
    worker` process. Replaces the root logger's handlers so every
    `logging.getLogger(__name__)` call anywhere in `app/` (no per-call-site
    change needed) emits structured JSON at the configured verbosity
    (`LOG_LEVEL`, deployment.md §10 — `debug` locally, `info`/`warning` in
    production).
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
