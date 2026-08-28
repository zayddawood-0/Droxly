import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.routers import (
    admin,
    analytics,
    auth,
    chat,
    comparisons,
    documents,
    extractions,
    local_storage,
    search,
    summaries,
    users,
)
from app.core.config import settings
from app.core.database import engine
from app.core.logging import configure_logging, request_id_var
from app.errors import DoxlyError, RequestValidationFailedError

configure_logging("api", settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Doxly API")

# deployment.md §11 / §5.1 — only the configured origin(s) may call the API
# with credentials (cookies); allow_credentials=True is required for the
# httpOnly session cookies the BFF relays (decisions.md ADR-010), and
# FastAPI's CORSMiddleware refuses a wildcard origin whenever credentials
# are allowed, which is exactly the "never a wildcard in production" rule
# deployment.md §11 already states -- enforced by the library, not just
# documented.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    observability.md §2.2 — the one place `request_id` is established for
    the whole request: read from an inbound `X-Request-ID` (set by the
    Next.js BFF per its own request_id generation) or freshly generated for
    a direct/BFF-skipping call, stored in a contextvar so every log line
    emitted while handling this request (core/logging.py's JsonFormatter)
    carries it automatically, exposed via `request.state` for the
    exception handlers below so there is exactly one id per request -- not
    a second, independently-generated one if an error handler ran its own
    fallback. Also applies security.md §11.3's baseline response headers
    (NFR-SEC-011) and observability.md §3's `request.completed` log line
    (method/route template/status/duration, never body content).
    """
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    start = time.monotonic()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    duration_ms = int((time.monotonic() - start) * 1000)

    response.headers["X-Request-ID"] = request_id
    # security.md §11.3 (NFR-SEC-011) — CSP/X-Content-Type-Options/
    # X-Frame-Options/HSTS. HSTS is meaningful only over HTTPS (a
    # same-origin-http local dev request would otherwise get a header
    # promising a guarantee the connection doesn't provide); the platform
    # ingress terminates TLS in front of this app (deployment.md §11), so
    # `request.url.scheme` reflects what the client actually used to reach
    # whatever terminated TLS, forwarded correctly by a standards-compliant
    # proxy.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    if settings.environment != "local":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )

    route = request.scope.get("route")
    route_template = getattr(route, "path", request.url.path)
    logger.info(
        "request.completed",
        extra={
            "method": request.method,
            "route": route_template,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(documents.tags_router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(extractions.router, prefix="/api/v1")
app.include_router(extractions.document_extractions_router, prefix="/api/v1")
app.include_router(comparisons.router, prefix="/api/v1")
app.include_router(summaries.router, prefix="/api/v1")
app.include_router(summaries.document_summaries_router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

if settings.storage_provider == "local":
    # tasks/remediation-plan.md R2 — dev/test-only stand-in for the real
    # object store's presigned-URL endpoint (core/storage.py). Never
    # mounted against a real cloud StorageProvider (decisions.md ADR-022).
    app.include_router(local_storage.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """
    DB connectivity + basic liveness, no auth required, no sensitive data
    returned (specs/deployment.md §3) — polled by the platform orchestrator
    to route traffic only to ready replicas.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}


def _request_id(request: Request) -> str:
    """
    observability.md §2.2 — generated at the Next.js BFF for every incoming
    request and forwarded as X-Request-ID; FastAPI includes it in every log
    line and error response so a support interaction can reference
    "request abc-123" without exposing internals (security.md §11.2).
    `request_context_middleware` (above) is the single place this id is
    actually established for the request, stored on `request.state` --
    reading it from there (rather than re-deriving a second, possibly
    different fallback UUID here) is what guarantees the id in this error
    response always matches the id on every log line for the same request.
    The header/fresh-UUID fallback only matters for the — should-be-rare —
    case of a handler invoked outside that middleware's scope.
    """
    state_id = getattr(request.state, "request_id", None)
    return state_id or request.headers.get("x-request-id") or str(uuid.uuid4())


@app.exception_handler(DoxlyError)
async def doxly_error_handler(request: Request, exc: DoxlyError) -> JSONResponse:
    """
    skills/backend.md §10 — the single global handler mapping every
    DoxlyError subclass to the api.md §0.5 envelope via its own
    status_code/error_code class attributes; adding a new error type never
    requires touching this function. `fields` (api.md §0.5: "present only
    on 422 validation errors") is included only when the raised exception
    actually carries one (RequestValidationFailedError does; nothing else
    does) — added in the R1 remediation pass (audit finding S1).
    """
    request_id = _request_id(request)
    headers = {"X-Request-ID": request_id}
    retry_after = getattr(exc, "retry_after_seconds", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    error_body: dict[str, object] = {
        "code": exc.error_code,
        "message": str(exc),
        "request_id": request_id,
    }
    fields = getattr(exc, "fields", None)
    if fields is not None:
        error_body["fields"] = fields

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_body},
        headers=headers,
    )


def _fields_from_pydantic_errors(errors: Sequence[dict]) -> dict[str, str]:
    """
    Converts FastAPI/Pydantic's `RequestValidationError.errors()` list
    (each entry has `loc` — a tuple like `("body", "email")` — and `msg`)
    into api.md §0.5's flat `{"<field_name>": "<detail>"}` shape. The
    location-kind prefix (`body`/`query`/`path`) is dropped since api.md's
    `fields` dict is keyed by field name only, not by where in the request
    it came from.
    """
    fields: dict[str, str] = {}
    for error in errors:
        loc = error.get("loc", ())
        key = (
            ".".join(str(part) for part in loc[1:])
            if len(loc) > 1
            else str(loc[-1] if loc else "body")
        )
        fields[key] = error.get("msg", "Invalid value.")
    return fields


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    R1 remediation (audit finding S1, CRITICAL): FastAPI registers its own
    handler for RequestValidationError ahead of any app-level handler for a
    broader exception type, so every Pydantic 422 was shipping FastAPI's
    default `{"detail": [...]}` body — never api.md §0.5's mandated
    envelope — until this handler was added. Delegates to
    doxly_error_handler so there remains exactly one place that actually
    builds the JSON envelope (skills/backend.md §10's "single global
    handler" principle, not two parallel ones).
    """
    return await doxly_error_handler(
        request,
        RequestValidationFailedError(_fields_from_pydantic_errors(exc.errors())),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback for anything not raised as a DoxlyError — NFR-SEC-009: never a
    stack trace, SQL fragment, or internal file path in the response body.
    Full detail is logged server-side instead (observability.md §3's
    "Unhandled exception" row — `request_id`, route, exception type, and
    the internal stack trace via `exc_info`, server-side only) — R12
    (Production Deployment Readiness) completes what R1's own docstring
    here explicitly deferred: the structured-logging call itself, not just
    the safe client-facing envelope R1 already built.
    """
    request_id = _request_id(request)
    logger.error(
        "request.unhandled_exception",
        exc_info=exc,
        extra={"route": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )
