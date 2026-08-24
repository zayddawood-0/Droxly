import uuid


class DoxlyError(Exception):
    """
    Base for all domain-level errors (skills/backend.md §10) — services and
    routers raise these, never a raw HTTPException constructed inline. A
    single global exception handler (app/main.py, added in R1 —
    tasks/remediation-plan.md — the first task with a real router) maps
    every subclass to the api.md §0.5 envelope generically via each
    subclass's `status_code`/`error_code` class attributes, so adding a new
    error type never requires touching the handler itself.
    """

    status_code: int = 500
    error_code: str = "internal_error"
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class NotFoundError(DoxlyError):
    """404 — resource doesn't exist or isn't owned by the caller (security.md §3.2's
    404-not-403 pattern: these two cases are always indistinguishable to the caller)."""

    status_code = 404
    error_code = "not_found"
    default_message = "The requested resource was not found."


class UnauthorizedError(DoxlyError):
    """401 — missing/expired/invalid access token."""

    status_code = 401
    error_code = "unauthorized"
    default_message = "Authentication is required."


class ForbiddenError(DoxlyError):
    """403 — valid token, but the caller's role doesn't permit this endpoint
    (security.md §3.1 — role checks only, never tenant-ownership checks)."""

    status_code = 403
    error_code = "forbidden"
    default_message = "You do not have permission to perform this action."


class ConflictError(DoxlyError):
    """409 — the request conflicts with the resource's current state."""

    status_code = 409
    error_code = "conflict"


class RateLimitedError(DoxlyError):
    """429 — general or AI-tier rate limit exceeded (api.md §0.7). `retry_after_seconds`
    is read by the router to set the Retry-After response header."""

    status_code = 429
    error_code = "rate_limited"
    default_message = "Too many requests. Please try again shortly."

    def __init__(self, retry_after_seconds: int, message: str | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class DailyAiLimitExceededError(RateLimitedError):
    """429 — the AI-tier daily cap (api.md §0.7), distinct error_code from a
    per-minute RateLimitedError so the client can distinguish them."""

    error_code = "daily_ai_limit_exceeded"
    default_message = "Daily AI request limit reached. Try again after midnight UTC."


class CsrfError(DoxlyError):
    """403 — missing or mismatched CSRF double-submit token (security.md §6.3)."""

    status_code = 403
    error_code = "csrf_mismatch"
    default_message = "CSRF validation failed."


class InvalidCredentialsError(DoxlyError):
    """401 — wrong password or unknown email. Deliberately the same message/code
    for both cases (NFR-SEC-006 — never reveals which one was wrong)."""

    status_code = 401
    error_code = "invalid_credentials"
    default_message = "Invalid email or password."


class RegistrationFailedError(DoxlyError):
    """400 — deliberately generic for an already-registered email (api.md §1,
    NFR-SEC-006) — never a distinguishable "email already exists" message."""

    status_code = 400
    error_code = "registration_failed"
    default_message = "Unable to register with the provided details."


class AccountSuspendedError(DoxlyError):
    """403 — login attempt against a users.status='suspended' account (api.md §1)."""

    status_code = 403
    error_code = "account_suspended"
    default_message = "This account has been suspended."


class InvalidOrExpiredTokenError(DoxlyError):
    """400 — an email-verification or password-reset token that doesn't
    resolve to a valid, unexpired, unused record."""

    status_code = 400
    error_code = "invalid_or_expired_token"
    default_message = "This link is invalid or has expired."


class OAuthFailedError(DoxlyError):
    """400 — Google denied consent, or the CSRF-bound `state` parameter
    didn't match (api.md §1)."""

    status_code = 400
    error_code = "oauth_failed"
    default_message = "Google sign-in failed. Please try again."


class OAuthNotConfiguredError(DoxlyError):
    """503 — GOOGLE_OAUTH_CLIENT_ID/SECRET aren't set in this environment
    (core/security.py's google_oauth_client() returns None) — a
    configuration gap, not a client error, so 503 rather than 400/404."""

    status_code = 503
    error_code = "oauth_not_configured"
    default_message = "Google sign-in is not available right now."


class EmptyDocumentError(DoxlyError):
    """
    Raised when chunking a document's extracted text yields zero chunks
    (rag.md §2's degenerate-input case, e.g. a mostly-image PDF with no text
    layer). Recording documents.status='failed' with a user-safe reason is
    FR-PROC-004's concern, owned by whichever caller performed extraction
    (the Phase 5 backend worker) — this error only signals that embedding
    cannot proceed, it does not itself touch document status.
    """

    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(
            f"Document {document_id} produced no chunks from its extracted text."
        )
        self.document_id = document_id
