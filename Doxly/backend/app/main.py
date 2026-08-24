import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.routers import auth, users
from app.core.database import engine
from app.errors import DoxlyError

app = FastAPI(title="Doxly API")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")


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
    requires touching this function.
    """
    request_id = _request_id(request)
    headers = {"X-Request-ID": request_id}
    retry_after = getattr(exc, "retry_after_seconds", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": str(exc),
                "request_id": request_id,
            }
        },
        headers=headers,
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
