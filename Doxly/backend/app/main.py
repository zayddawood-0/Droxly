import uuid
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.routers import (
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
from app.errors import DoxlyError, RequestValidationFailedError

app = FastAPI(title="Doxly API")

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
    "request abc-123" without exposing internals (security.md §11.2). Falls
    back to a fresh ID for the (should-be-rare) case of a direct call that
    skipped the BFF, rather than omitting it from the envelope.
    """
    return request.headers.get("x-request-id", str(uuid.uuid4()))


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
    Full detail is logged server-side (observability.md), not in scope for
    this endpoint's own error handling since structured logging is R12's
    (Production Deployment Readiness) deliverable, not R1's — this handler
    still returns the safe, request-ID-correlated envelope regardless.
    """
    request_id = _request_id(request)
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
