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


class RequestValidationFailedError(DoxlyError):
    """
    422 — request body/query fails Pydantic validation (api.md §0.5's
    `fields` case). R1 remediation (audit finding S1): wraps FastAPI's own
    RequestValidationError so every 422 goes through the same single
    envelope-construction path as every other DoxlyError, rather than
    shipping FastAPI's default `{"detail": [...]}` shape unchanged
    (main.py's RequestValidationError handler does the conversion). Named
    distinctly from a hypothetical *domain*-level "ValidationError" some
    future service-layer check might raise (skills/backend.md §10 lists
    `ValidationError` as its own example, `domain-level, distinct from
    Pydantic's own request-validation errors`) — this class is specifically
    the Pydantic-boundary one.
    """

    status_code = 422
    error_code = "validation_error"
    default_message = "The request could not be validated."

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__()
        self.fields = fields


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


# --- R2 (tasks/remediation-plan.md) — documents ---


class QuotaExceededError(DoxlyError):
    """402 — api.md §3 /documents/presign: "the file would exceed storage
    quota or the per-file size cap" — one shared code for both cases, per
    api.md's own text."""

    status_code = 402
    error_code = "quota_exceeded"
    default_message = "This upload would exceed your storage quota."


class UnsupportedMimeTypeError(DoxlyError):
    """
    422 — api.md names this as a *specific* error code, distinct from a
    generic validation failure. Deliberately raised from the service layer
    rather than a Pydantic field_validator on PresignRequest.mime_type: per
    skills/backend.md §9, "if the check can be expressed purely from the
    shape of the request body ... it belongs in a Pydantic schema" would
    normally put an enum-membership check like this one in Pydantic, but
    doing so would produce R1's generic `validation_error` code (S1's
    RequestValidationFailedError) — api.md's own contract explicitly wants
    `unsupported_mime_type` here, which only a raised DoxlyError subclass
    can produce. A deliberate, documented exception to the usual heuristic.
    """

    status_code = 422
    error_code = "unsupported_mime_type"
    default_message = "This file type is not supported."


class UploadMismatchError(DoxlyError):
    """400 — api.md's POST /documents/{id}/confirm: the stored object's
    real size/MIME doesn't match what was declared at presign time
    (NFR-SEC-003)."""

    status_code = 400
    error_code = "upload_mismatch"
    default_message = "The uploaded file doesn't match what was declared."


class NotReadyError(DoxlyError):
    """409 — api.md's GET /documents/{id}/content: the document hasn't
    finished processing yet."""

    status_code = 409
    error_code = "not_ready"
    default_message = "This document isn't ready yet."


class InvalidStatusError(DoxlyError):
    """409 — api.md's POST /documents/{id}/reprocess: only a `failed`
    document may be reprocessed via this route."""

    status_code = 409
    error_code = "invalid_status"
    default_message = "This action isn't valid for the document's current status."


class TagAlreadyExistsError(DoxlyError):
    """409 — api.md's POST /tags: (user_id, name) already exists."""

    status_code = 409
    error_code = "tag_already_exists"
    default_message = "A tag with this name already exists."


class ConfirmationMismatchError(DoxlyError):
    """422 — api.md's DELETE /users/me: confirmation_email must exactly
    match the caller's own current email (FR-USER-002's typed-confirmation
    pattern for a destructive, irreversible action)."""

    status_code = 422
    error_code = "confirmation_mismatch"
    default_message = "The confirmation email doesn't match your account."


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


# --- R4 (tasks/remediation-plan.md) — chat ---


class DocumentNotReadyError(DoxlyError):
    """409 — api.md §4: a document referenced by a conversation/message is
    no longer `status=ready` (e.g., deleted or still processing mid-conversation).
    Distinct error_code from R2's generic `not_ready` (api.md names this one
    specifically for chat's endpoints)."""

    status_code = 409
    error_code = "document_not_ready"
    default_message = "One of the referenced documents isn't ready yet."


class MessageNotInProgressError(DoxlyError):
    """409 — api.md's POST .../messages/{id}/stop: the message has already
    completed or was never streaming."""

    status_code = 409
    error_code = "not_in_progress"
    default_message = "This message isn't currently generating."


# --- R5 (tasks/remediation-plan.md) — extraction ---


class UnknownExtractionFieldError(DoxlyError):
    """
    422 — api.md's PATCH /extractions/{id}: a correction's `field` name
    isn't present in the extraction's own `schema` (data-dependent — the
    schema lives on the specific extraction row, not the request body's own
    shape, so per skills/backend.md §9 this is a service-layer check, not a
    Pydantic one).
    """

    status_code = 422
    error_code = "unknown_field"
    default_message = (
        "One or more corrected fields aren't part of this extraction's schema."
    )


# --- R6 (tasks/remediation-plan.md) — comparison ---


class IdenticalDocumentsError(DoxlyError):
    """
    422 — api.md's POST /comparisons: `document_a_id == document_b_id`
    (mirrors `comparisons`' own `CHECK (document_a_id <> document_b_id)`,
    `database.md` §3.12). Expressible purely from the request body's own
    shape (skills/backend.md §9 would normally put this in a Pydantic
    `model_validator`), but api.md names a *specific* error code
    (`identical_documents`) rather than the generic `validation_error` a
    Pydantic-layer check would produce — the same documented exception to
    the usual heuristic `UnsupportedMimeTypeError` already establishes.
    """

    status_code = 422
    error_code = "identical_documents"
    default_message = "The two documents to compare must be different."


# --- R10 (tasks/remediation-plan.md) — admin ---


class NotSuspendedError(DoxlyError):
    """409 — api.md's POST /admin/users/{id}/unsuspend: the account isn't
    currently suspended."""

    status_code = 409
    error_code = "not_suspended"
    default_message = "This account is not currently suspended."
