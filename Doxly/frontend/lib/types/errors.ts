/**
 * Mirrors the error envelope in specs/api.md §0.5 exactly:
 *   { "error": { "code": "...", "message": "...", "fields": {...}? } }
 * `fields` is present only on 422 validation errors. `message` is always
 * safe to render directly (NFR-SEC-009) — never a stack trace/SQL/internal path.
 */
export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    fields?: Record<string, string>;
  };
};

export class DoxlyApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields?: Record<string, string>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "DoxlyApiError";
    this.status = status;
    this.code = body.error.code;
    this.fields = body.error.fields;
  }

  /** specs/api.md §0.4: 422 validation failures always carry per-field detail. */
  get isValidationError() {
    return this.status === 422;
  }

  /** specs/api.md §0.4: rate limit exceeded — callers may read Retry-After separately. */
  get isRateLimited() {
    return this.status === 429;
  }
}

/** Type guard for narrowing a caught unknown error to DoxlyApiError. */
export function isDoxlyApiError(error: unknown): error is DoxlyApiError {
  return error instanceof DoxlyApiError;
}
