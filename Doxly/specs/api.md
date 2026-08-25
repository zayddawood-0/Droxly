# Doxly — API Specification

> Defines the complete REST contract between the Next.js frontend (BFF) and the FastAPI backend. This is a **contract specification**, not an implementation — no route handlers, no Pydantic model code, no business logic. Every endpoint traces to a requirement ID in `requirements.md`; every request/response field traces to a column in `database.md`. Deep mechanics that belong to other specs are referenced by filename, not restated: prompt-injection defense, token/refresh-rotation internals, and header hardening live in `security.md`; LLM provider selection and prompting live in `ai.md`; workflow node graphs live in `langgraph.md`; retrieval/ranking mechanics live in `rag.md`. This file owns the **HTTP contract only** — method, path, auth, request/response shape, validation, status codes.

## 0. Conventions

### 0.1 Base URL & versioning
All endpoints are prefixed `/api/v1` (`decisions.md` ADR-005). Breaking changes (removed/renamed fields, changed semantics) require a new prefix (`/api/v2`) with the old version kept live through a documented deprecation window; additive changes (new optional request fields, new response fields, new endpoints) ship in place without a version bump.

### 0.2 Transport
HTTPS only. `Content-Type: application/json` for all request/response bodies, with two documented exceptions: file upload bytes never pass through this API at all (direct browser-to-storage via presigned URL, ADR-009, `architecture.md` §4), and chat message responses stream as `text/event-stream` (SSE, `architecture.md` §5).

### 0.3 Authentication
Every endpoint requires a valid `access_token` httpOnly cookie (ADR-010) **except**: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh` (reads `refresh_token` instead), `GET /auth/oauth/google`, `GET /auth/oauth/google/callback`, `POST /auth/password-reset/request`, `POST /auth/password-reset/confirm`, and `POST /auth/verify-email`. Cookies are set by FastAPI's `Set-Cookie` header and relayed unmodified by the Next.js BFF route handlers that proxy every call — Next.js never mints or inspects tokens itself (`architecture.md` §2.1). CSRF protection on state-changing cookie-authenticated requests is enforced per `NFR-SEC-010` (mechanism in `security.md`); it applies to every endpoint below and is not repeated per-route.

### 0.4 Status code meanings (used consistently across every endpoint)
- **`401 Unauthorized`** — access token missing, expired, or invalid signature. Client should attempt `POST /auth/refresh` then retry once.
- **`403 Forbidden`** — token is valid but the authenticated user's **role** doesn't permit the action (e.g., non-admin calling `/admin/*`). Reserved for role checks only, **never** for tenant-ownership checks.
- **`404 Not Found`** — token is valid, but the requested resource either doesn't exist or is not owned by the authenticated user. Cross-tenant access to any resource ID **always** returns `404`, never `403` and never a distinguishable error, so the existence of another user's resource is never leaked (`NFR-SEC-001`, mirrors the `FR-DOC-005` acceptance criterion applied system-wide).
- **`422 Unprocessable Entity`** — request body/query fails Pydantic validation; response lists per-field errors.
- **`429 Too Many Requests`** — rate limit exceeded; see §0.7.
- **`402`** is used narrowly, only for plan-quota exhaustion (storage/document/AI-request caps), distinct from `422` (malformed request) and `429` (rate, not quota).

### 0.5 Error envelope
Every non-2xx JSON response body has the shape:
```
{ "error": { "code": "<machine_readable_snake_case>", "message": "<user_safe_message>", "fields": { "<field_name>": "<detail>" }? } }
```
`fields` is present only on `422` validation errors. `message` is always safe to render directly to the end user (`NFR-SEC-009`) — never a stack trace, SQL fragment, internal file path, or library version. Internal exception detail is captured server-side only, per `observability.md`.

### 0.6 Pagination
**Offset-based**, uniformly: `limit` (default 20, max 100) and `offset` (default 0) query params on every list endpoint; response wraps items as:
```
{ "items": [...], "total": <int>, "limit": <int>, "offset": <int> }
```
Chosen over cursor pagination for MVP: per-user collections (documents, conversations, extractions) are expected in the hundreds, not millions, so offset's O(n) skip cost is negligible, and offset gives free "jump to page N" / total-count UI that a cursor scheme would have to work around. Revisit as a cursor scheme only if a specific collection's per-user scale later warrants it (`performance.md`).

### 0.7 Rate limiting
Two tiers, enforced by Redis token-bucket middleware (`decisions.md` OQ-08, `architecture.md` §2.5):
- **General API:** 60 requests/minute/user, applies to every endpoint below by default.
- **AI-invoking endpoints — stricter limit:** 10 requests/minute/user, plus a daily cap (Free: 30 AI requests/day, Pro: 500/day). This tier applies specifically to: `POST /chat/conversations/{id}/messages`, `POST /documents/{id}/summaries`, `POST /extractions`, `POST /comparisons`, and `POST /documents/{id}/reprocess` (each retriggers the AI-backed processing pipeline). Every such endpoint is marked **"AI rate limit"** in its entry below.
- Unauthenticated auth endpoints (`register`, `login`, password reset) carry their own per-IP-and-per-account limiting on top of the general tier, for credential-stuffing/enumeration resistance (`NFR-SEC-002`).
- On `429`, the response carries a `Retry-After` header (seconds until the bucket next admits a request) and body `{"error":{"code":"rate_limited","message":"..."}}`; daily-cap exhaustion instead returns `{"error":{"code":"daily_ai_limit_exceeded","message":"..."}}` with `Retry-After` set to seconds-until-midnight-UTC.

### 0.8 Timestamps & IDs
Timestamps: ISO 8601 UTC, e.g. `2026-08-19T14:30:00Z`. IDs: UUIDv4 strings everywhere, matching `database.md` primary keys.

---

## 1. `/auth`

### `POST /api/v1/auth/register`
- **Auth:** none. **Fulfills:** `FR-AUTH-001`.
- **Request:** `{ email: string (valid format), password: string (min 8 chars, ≥1 letter + ≥1 number), display_name: string }`.
- **Response 201:** `{ id: uuid, email: string, display_name: string, email_verified: false }`.
- **Validation:** email format and password strength checked before any DB write (`422` on failure, no partial account created).
- **Errors:** `422` invalid email or weak password | `400 registration_failed` — deliberately generic for an already-registered email, same message class as any other registration failure so account existence is never revealed (`NFR-SEC-006`).
- **Side effects:** creates `users` row (`plan=free`, `password_hash` set via argon2), queues a verification email (`FR-AUTH-002`).

### `POST /api/v1/auth/verify-email`
- **Auth:** none (the token itself authenticates the action). **Fulfills:** `FR-AUTH-002`.
- **Request:** `{ token: string }`. The emailed link opens a Next.js page that extracts the token and POSTs it here (BFF pattern — the raw link never hits the API directly).
- **Response 200:** `{ verified: true }`. Sets `users.email_verified_at`.
- **Errors:** `400 invalid_or_expired_token`.

### `POST /api/v1/auth/verify-email/resend`
- **Auth:** required (unverified user). **Fulfills:** `FR-AUTH-002`.
- **Response 202.** Queues a fresh verification email invalidating the prior token. Rate-limited to 1 per 5 minutes per account to prevent email-bombing (independent of the general per-minute limit).

### `GET /api/v1/auth/oauth/google`
- **Auth:** none. **Fulfills:** `FR-AUTH-003`.
- **Response 302:** redirect to Google's OAuth2 consent screen with a CSRF-bound `state` parameter.

### `GET /api/v1/auth/oauth/google/callback`
- **Auth:** none (the OAuth `code` authenticates the action). **Fulfills:** `FR-AUTH-003`.
- **Query params:** `code`, `state`.
- **Response 302:** redirect into the app with `access_token`/`refresh_token` cookies set on success.
- **Errors:** `400 oauth_failed` if `state` doesn't match or Google denies consent.
- **Side effects:** first-time Google sign-in creates a `users` row with `email_verified_at` set immediately (Google already verified it) and no `password_hash`; if the same email already exists from password signup, the Google identity is linked to that existing account rather than creating a duplicate (`FR-AUTH-003` acceptance criteria).

### `POST /api/v1/auth/login`
- **Auth:** none. **Fulfills:** `FR-AUTH-004`.
- **Request:** `{ email: string, password: string }`.
- **Response 200:** `{ id: uuid, email: string, display_name: string, role: string, plan: string }`, sets `access_token` (15 min) + `refresh_token` (30 days) httpOnly cookies.
- **Errors:** `401 invalid_credentials` — identical message whether the email doesn't exist or the password is wrong (`NFR-SEC-006`) | `429` after repeated failures, with progressive backoff (`NFR-SEC-002`) | `403 account_suspended` if `users.status='suspended'`.

### `POST /api/v1/auth/refresh`
- **Auth:** valid `refresh_token` cookie only (not `access_token`). **Fulfills:** `FR-AUTH-005`.
- **Request:** none (cookie-driven).
- **Response 200:** new `access_token` cookie issued; `refresh_token` cookie rotated per the rotation policy in `security.md`.
- **Errors:** `401` if the refresh token is expired, revoked, or reused after having already been rotated (reuse triggers revocation of the entire token family — `security.md`).

### `POST /api/v1/auth/logout`
- **Auth:** required. **Fulfills:** `FR-AUTH-006`.
- **Response 204.** Clears both cookies; revokes the current `refresh_tokens` row server-side.

### `POST /api/v1/auth/password-reset/request`
- **Auth:** none. **Fulfills:** `FR-AUTH-007`.
- **Request:** `{ email: string }`.
- **Response 202** unconditionally, whether or not the email is registered (`NFR-SEC-006`).

### `POST /api/v1/auth/password-reset/confirm`
- **Auth:** none (token authenticates the action). **Fulfills:** `FR-AUTH-007`.
- **Request:** `{ token: string, new_password: string (same strength rule as registration) }`.
- **Response 200:** `{ reset: true }`.
- **Errors:** `400 invalid_or_expired_token` | `422` weak password.
- **Side effects:** revokes **all** existing `refresh_tokens` for the account, forcing re-login on every device (`FR-AUTH-007` acceptance criteria).

### `GET /api/v1/auth/sessions`
- **Auth:** required. **Fulfills:** `FR-AUTH-008`.
- **Response 200:** `{ items: [{ id: uuid, device_label: string|null, ip_address: string|null, created_at, expires_at, is_current: bool }] }` — one entry per non-revoked `refresh_tokens` row belonging to the caller.

### `DELETE /api/v1/auth/sessions/{session_id}`
- **Auth:** required. **Fulfills:** `FR-AUTH-008`.
- **Response 204.** Revokes that `refresh_tokens` row only (other sessions unaffected).
- **Errors:** `404` if `session_id` doesn't belong to the caller.

---

## 2. `/users`

### `GET /api/v1/users/me`
- **Auth:** required. **Fulfills:** `FR-USER-001`.
- **Response 200:** `{ id, email, display_name, avatar_url: string|null, role, plan, email_verified: bool, storage_used_bytes: int, created_at }`.

### `PATCH /api/v1/users/me`
- **Auth:** required. **Fulfills:** `FR-USER-001`.
- **Request (all optional):** `{ display_name?: string, avatar_url?: string, email?: string }`.
- **Response 200:** updated profile (same shape as `GET`).
- **Validation:** non-empty `display_name` if provided; valid email format if provided.
- **Errors:** `422` invalid email format or empty display name.
- **Side effects:** changing `email` clears `email_verified_at` and re-triggers verification (`FR-AUTH-002`).

### `DELETE /api/v1/users/me`
- **Auth:** required. **Fulfills:** `FR-USER-002`.
- **Request:** `{ confirmation_email: string }` — must exactly match the caller's own current email (typed-confirmation pattern for a destructive, irreversible action; a `DELETE` verb with a body is used deliberately here rather than a POST-to-a-verb route, since the resource being deleted genuinely is `/users/me`).
- **Response 202:** `{ status: "pending_deletion", purge_scheduled_after_days: 30 }`.
- **Errors:** `422 confirmation_mismatch` if `confirmation_email` doesn't match.
- **Side effects:** sets `users.status='pending_deletion'` (login disabled immediately), revokes all sessions, queues the 30-day hard-purge background job (cascades to documents, chunks, embeddings, conversations, extractions, comparisons per `privacy.md` retention policy).

### `GET /api/v1/users/me/usage`
- **Auth:** required. **Fulfills:** `FR-USER-003`.
- **Response 200:** `{ plan: string, storage_used_bytes: int, storage_quota_bytes: int, document_count: int, document_quota: int|null, ai_requests_today: int, ai_requests_daily_limit: int }` — computed live off `users.storage_used_bytes` and a same-day count against `ai_requests`, never stale beyond the acceptance criterion's "few seconds" bound.

---

## 3. `/documents`

### `POST /api/v1/documents/presign`
- **Auth:** required (verified user). **Fulfills:** `FR-DOC-001` (upload flow step 1 of 3, `architecture.md` §4).
- **Request:** `{ file_name: string, mime_type: string (one of: application/pdf, the DOCX OOXML type, text/plain, text/csv), size_bytes: int }`.
- **Response 201:** `{ document_id: uuid, upload_url: string, upload_method: "PUT", upload_headers: object, expires_in: int }`. A `documents` row is created immediately with `status="queued"` and a generated, non-guessable `storage_key` (`NFR-SEC-004`) — before the browser has uploaded anything — so the client has a stable ID to track from step 1.
- **Validation:** `mime_type` must content-type-match one of the four supported types; `size_bytes` checked against the per-file cap (25 MB default, `decisions.md` OQ-06) and against remaining `storage_used_bytes` quota headroom (OQ-07) **before** a presigned URL is issued.
- **Errors:** `422 unsupported_mime_type` | `422` missing/invalid fields | `402 quota_exceeded` if the file would exceed storage quota or the per-file size cap | `401` unauthenticated.

### `POST /api/v1/documents/{id}/confirm`
- **Auth:** required. **Fulfills:** `FR-DOC-001` (step 3, after the browser's direct PUT to storage per `architecture.md` §4).
- **Request:** none.
- **Response 202:** `{ id: uuid, status: "queued" }`. Backend verifies the object exists in storage and its actual size/content-sniffed MIME type matches what was declared at presign time, computes `checksum_sha256`, then enqueues `process_document(document_id)` to the Redis queue (`FR-PROC-001`, ADR-008).
- **Errors:** `404` if `id` not owned by caller, or the presign window expired without a confirming upload | `400 upload_mismatch` if the stored object's real size/MIME doesn't match the declared values (`NFR-SEC-003`).

### `GET /api/v1/documents`
- **Auth:** required. **Fulfills:** `FR-DOC-002`.
- **Query params:** `limit`, `offset` (§0.6) · `status` (optional: `queued|extracting|chunking|embedding|ready|failed`) · `tag_id` (optional, UUID) · `mime_type` (optional) · `sort` (optional: `created_at_desc` default, `created_at_asc`, `name_asc`, `size_desc`).
- **Response 200:** paginated envelope (§0.6) of `{ id, file_name, mime_type, size_bytes, status, page_count: int|null, tags: [{id, name, color}], created_at, updated_at }`. Always scoped to the caller's own, non-deleted documents (`NFR-SEC-001`).

### `GET /api/v1/documents/{id}`
- **Auth:** required. **Fulfills:** `FR-DOC-003`.
- **Response 200:** all list fields plus `checksum_sha256`, `processing_error: string|null` (populated only if `status=failed`, sanitized per `NFR-SEC-009`), `extracted_text_available: bool`.
- **Errors:** `404` if not found or not owned.

### `GET /api/v1/documents/{id}/download`
- **Auth:** required. **Fulfills:** `FR-DOC-003`.
- **Response 200:** `{ download_url: string, expires_in: int }` — short-lived presigned GET URL to the original file in object storage (never a redirect that leaks the permanent storage key).
- **Errors:** `404`.

### `GET /api/v1/documents/{id}/content`
- **Auth:** required. **Fulfills:** `FR-DOC-003` (in-app viewer).
- **Query params:** `page` (optional int, for paginated PDF viewing).
- **Response 200:** `{ pages: [{ page_number: int, text: string }] }` for PDF/DOCX, `{ text: string }` for TXT, or `{ rows: [...], columns: [...] }` for CSV — always the extracted/stored content, never a re-parse of the raw file per request.
- **Errors:** `404` | `409 not_ready` if `status != ready`.

### `PATCH /api/v1/documents/{id}`
- **Auth:** required. **Fulfills:** `FR-DOC-004` (rename), `FR-DOC-006` (tag assignment).
- **Request (all optional):** `{ file_name?: string (non-empty), tag_ids?: [uuid, ...] }`. Renaming only changes the display name (`documents.file_name`), never the underlying `storage_key`. Supplying `tag_ids` replaces the document's full tag set (create new tags first via `POST /tags`).
- **Response 200:** updated document (same shape as `GET /documents/{id}`).
- **Errors:** `404` document, or any `tag_id`, not owned by caller | `422` empty `file_name`.

### `DELETE /api/v1/documents/{id}`
- **Auth:** required. **Fulfills:** `FR-DOC-005`.
- **Response 204.** Sets `documents.deleted_at` immediately — excluded from all list/detail/search/RAG-retrieval queries from that point on. Hard deletion (object storage + `document_chunks` + citations) runs via a background job within the retention window (`privacy.md`).
- **Errors:** `404` if the document doesn't exist **or** isn't owned by the caller — identical response either way, so existence of another user's document is never leaked (`FR-DOC-005` acceptance criteria, `NFR-SEC-001`).

### `POST /api/v1/documents/{id}/reprocess`
- **Auth:** required. **AI rate limit** (§0.7). **Fulfills:** `FR-PROC-005`.
- **Request:** none.
- **Response 202:** `{ id: uuid, status: "queued" }`. Re-enqueues the full extract → chunk → embed pipeline; prior chunks/embeddings for the document are discarded and replaced, not appended.
- **Errors:** `404` | `409 invalid_status` if current `status` is not `failed` AND the document is not a stale non-terminal document (in a processing state for longer than the configured staleness threshold — see `decisions.md` ADR-026). A stale non-terminal document is treated as reprocessable the same as a failed one (reprocessing a healthy `ready` document is a distinct, explicit action a user shouldn't trigger accidentally via this route — re-running on a `ready` doc is out of scope for MVP).

### `GET /api/v1/documents/{id}/status`
- **Auth:** required. **Fulfills:** `FR-DOC-008`.
- **Response 200:** `{ status: string, processing_error: string|null }` — lightweight, cheap to poll.
- **Streaming alternative:** `GET /api/v1/documents/{id}/status/stream` (same auth/ownership rules, `text/event-stream`) pushes `event: status` (`data: {"status": "..."}`) on every stage transition, ending with a terminal `ready`/`failed` event — the frontend uses SSE where supported and falls back to polling `GET .../status`, per `FR-DOC-008`'s "polling or SSE" acceptance criterion.
- **Errors:** `404`.

### `POST /api/v1/documents/bulk`
- **Auth:** required. **Fulfills:** `FR-DOC-007` (P2).
- **Request:** `{ document_ids: [uuid, ...], action: "delete"|"tag", tag_ids?: [uuid, ...] (required if action="tag") }`.
- **Response 200:** `{ affected: int, skipped: int }`. Any `document_id` not owned by the caller is silently excluded from processing and counted in `skipped`, never surfaced as a partial error (avoids existence leakage across a batch).
- **Errors:** `422` if `action="tag"` and `tag_ids` is missing/empty, or if `tag_ids` contains an ID not owned by the caller.

### `GET /api/v1/tags`
- **Auth:** required. **Fulfills:** `FR-DOC-006`.
- **Response 200:** `{ items: [{ id, name, color: string|null }] }` — all of the caller's tags (not paginated; tag counts per user are small).

### `POST /api/v1/tags`
- **Auth:** required. **Fulfills:** `FR-DOC-006`.
- **Request:** `{ name: string (non-empty), color?: string }`.
- **Response 201:** `{ id, name, color }`.
- **Errors:** `409 tag_already_exists` if `(user_id, name)` already exists | `422` empty name.

### `DELETE /api/v1/tags/{id}`
- **Auth:** required. **Fulfills:** `FR-DOC-006`.
- **Response 204.** Cascades to remove the tag from every `document_tags` row it appeared in.
- **Errors:** `404` if not owned.

---

## 4. `/chat`

### `POST /api/v1/chat/conversations`
- **Auth:** required. **Fulfills:** `FR-AI-001`, `FR-AI-002`.
- **Request:** `{ document_ids: [uuid, ...] }` — one ID → `scope_type="single_document"`; two or more → `"multi_document"`; omitted/empty → `"workspace"` (spans all of the caller's `ready` documents, per `FR-AI-002`).
- **Response 201:** `{ id: uuid, scope_type: string, document_ids: [uuid, ...], title: null, created_at }`.
- **Errors:** `404` if any `document_id` isn't owned by the caller | `409 document_not_ready` if any referenced document has `status != ready`.

### `GET /api/v1/chat/conversations`
- **Auth:** required. **Fulfills:** `FR-AI-003`.
- **Query params:** `limit`, `offset`.
- **Response 200:** paginated `{ id, title: string|null, scope_type, document_ids: [uuid,...], updated_at }`, sorted by `updated_at desc`.

### `GET /api/v1/chat/conversations/{id}`
- **Auth:** required. **Fulfills:** `FR-AI-003`.
- **Response 200:** conversation detail plus `{ messages: [{ id, role: "user"|"assistant", content: string, citations: [{ document_id, page_number: int|null, snippet, relevance_score: float|null }], created_at }] }`, ordered oldest-first.
- **Errors:** `404`.

### `DELETE /api/v1/chat/conversations/{id}`
- **Auth:** required. **Fulfills:** `FR-AI-003` (cleanup).
- **Response 204.** Soft-deletes (`deleted_at`).
- **Errors:** `404`.

### `POST /api/v1/chat/conversations/{id}/messages`
- **Auth:** required. **AI rate limit** (§0.7). **Fulfills:** `FR-AI-001`, `FR-AI-003`, `FR-AI-004`, `FR-AI-005`, `FR-RAG-001`, `FR-RAG-002`.
- **Request:** `{ content: string (required, non-empty, length-capped per `security.md` input limits) }`.
- **Response 200, `Content-Type: text/event-stream`:** the request runs synchronously inline (not queued — this is the one workflow that streams token-by-token, `architecture.md` §5) and returns an SSE stream, **not** a single JSON body:
  - `event: message_id` → `data: {"message_id": uuid}` (the persisted user-message ID, sent first)
  - `event: token` → `data: {"text": "..."}`, repeated per generated token
  - `event: citations` → `data: {"citations": [...]}`, sent once after generation completes
  - `event: done` → `data: {"message_id": uuid}` (the persisted assistant-message ID)
  - `event: error` → `data: {"code": "...", "message": "..."}` on mid-stream failure; the stream then closes and any partial assistant output generated so far is persisted, flagged incomplete, rather than discarded.
  - LangGraph node sequence (classifier → retriever → context analyzer → answer generator → citation validator), prompt-injection handling, and the "graceful I don't know" behavior (`FR-AI-004`) are defined in `langgraph.md` and `security.md` — this endpoint only owns the transport contract above.
- **Errors (returned as standard JSON before the stream opens, not as an SSE event):** `404` conversation not found/owned | `409 document_not_ready` if a referenced document is no longer `ready` (e.g., deleted mid-conversation) | `429` AI rate limit exceeded.

### `POST /api/v1/chat/conversations/{id}/messages/{message_id}/stop`
- **Auth:** required. **Fulfills:** `FR-AI-006`.
- **Request:** none.
- **Response 200:** `{ message_id: uuid, status: "stopped" }`. Signals the in-flight LangGraph run for `message_id` to halt after its current node; the assistant message is persisted with whatever partial content had streamed so far, marked `status="stopped"` so the UI can distinguish a user-initiated stop from a failure.
- **Errors:** `404` if `message_id` doesn't belong to the caller or the conversation | `409 not_in_progress` if the message has already completed or was never streaming.

### `POST /api/v1/chat/conversations/{id}/messages/{message_id}/regenerate`
- **Auth:** required. **AI rate limit** (§0.7). **Fulfills:** `FR-AI-006` ("Regenerate" — added at Phase 9 implementation time; `ui-ux.md` §8 documented this interaction but no endpoint existed for it, a gap resolved here per `CLAUDE.md`'s SDD rules rather than left implicit).
- **Path param:** `message_id` — an existing **assistant** message in this conversation whose turn is being re-run.
- **Request:** none. The preceding user message (found by walking back from `message_id` to the nearest prior `role="user"` message) supplies the query — regenerating never creates a duplicate user turn.
- **Response 200, `Content-Type: text/event-stream`:** identical event contract to `POST .../messages` (`event: message_id` → `data: {"message_id": uuid}`, then `token`/`citations`/`done`/`error`), except the initial `message_id` event echoes the **existing** user message's ID rather than a newly created one. The regenerated answer is persisted as a **new** `messages` row appended to the conversation (the schema is append-only; no message is edited or superseded in place) — the UI decides how to present the newest attempt relative to prior ones.
- **Errors (returned as standard JSON before the stream opens):** `404` if `message_id` doesn't belong to the caller/conversation, isn't an assistant message, or has no preceding user message | `409 document_not_ready` if a referenced document is no longer `ready` | `429` AI rate limit exceeded.

---

## 5. `/summaries`

Summaries are generated asynchronously on the background worker (`ai.md` §2 — summarization is a queued workflow, not inline like chat) and persisted for reuse rather than regenerated on every view (`FR-SUM-001` acceptance criteria), backed by the `document_summaries` table (`database.md` §6 traceability).

### `POST /api/v1/documents/{id}/summaries`
- **Auth:** required. **AI rate limit** (§0.7). **Fulfills:** `FR-SUM-001`.
- **Request:** `{ summary_type: "brief"|"detailed"|"bullet_points" }`.
- **Response 202:** `{ id: uuid, document_id: uuid, summary_type: string, status: "processing" }`. Enqueues the LangGraph Summarization workflow (`langgraph.md`); client polls `GET /summaries/{id}` or the document's status stream for completion.
- **Errors:** `404` document not owned | `409 document_not_ready` if `status != ready` | `422` invalid `summary_type`.

### `GET /api/v1/documents/{id}/summaries`
- **Auth:** required. **Fulfills:** `FR-SUM-002`.
- **Query params:** `limit`, `offset`.
- **Response 200:** paginated `{ id, summary_type, status, created_at }` for every summary ever generated for the document, newest first — regenerating a summary never overwrites or hides a prior one (`FR-SUM-002`).
- **Errors:** `404` document not owned.

### `GET /api/v1/summaries/{id}`
- **Auth:** required. **Fulfills:** `FR-SUM-001`, `FR-SUM-002`.
- **Response 200:** `{ id, document_id, summary_type, status, content: string|null, created_at }` (`content` is `null` while `status="processing"`).
- **Errors:** `404`.

---

## 6. `/extractions`

### `GET /api/v1/extractions/templates`
- **Auth:** required. **Fulfills:** `FR-EXT-002`.
- **Response 200:** `{ items: [{ key: string, name: string, description: string, fields: [{ name, type, description, required: bool }] }] }` — preset schemas (`invoice`, `contract`, `resume`, `research_paper`) so users aren't required to hand-define a schema.

### `POST /api/v1/extractions`
- **Auth:** required. **AI rate limit** (§0.7). **Fulfills:** `FR-EXT-001`.
- **Request:** `{ document_id: uuid, template_key?: string, schema?: [{ name, type, description?, required: bool }] }` — exactly one of `template_key` or `schema` must be present.
- **Response 202:** `{ id: uuid, status: "processing" }`. Runs on the background worker (`langgraph.md` Extraction graph); client polls `GET /extractions/{id}`.
- **Errors:** `404` document not owned | `409 document_not_ready` if `status != ready` | `422` if neither or both of `template_key`/`schema` are provided, or `template_key` doesn't match a known template.

### `GET /api/v1/extractions/{id}`
- **Auth:** required. **Fulfills:** `FR-EXT-001`, `FR-EXT-003`.
- **Response 200:** `{ id, document_id, template_key: string|null, schema: [...], status, result: [{ field: string, value: any|null, confidence: float|null, not_found_reason: string|null, corrected: bool, citation: { page_number: int|null, snippet: string }|null }], created_at }`. A field the model couldn't locate is returned as `value: null` with a populated `not_found_reason` — never a fabricated placeholder (`FR-EXT-003`).
- **Errors:** `404`.

### `GET /api/v1/documents/{document_id}/extractions`
- **Auth:** required. **Fulfills:** `FR-EXT-001` (history for a document).
- **Query params:** `limit`, `offset`.
- **Response 200:** paginated extraction summaries `{ id, template_key, status, created_at }` for that document.
- **Errors:** `404` document not owned.

### `PATCH /api/v1/extractions/{id}`
- **Auth:** required. **Fulfills:** `FR-EXT-004` (P2).
- **Request:** `{ corrections: [{ field: string, value: any }] }`.
- **Response 200:** updated extraction (same shape as `GET /extractions/{id}`) with each corrected field's `value` replaced and `corrected: true`; the model's original value is retained internally in `result_json` for audit purposes but not surfaced in this response.
- **Errors:** `404` | `422` if any `field` name isn't present in the extraction's `schema`.

---

## 7. `/comparisons`

### `POST /api/v1/comparisons`
- **Auth:** required. **AI rate limit** (§0.7). **Fulfills:** `FR-COMP-001`.
- **Request:** `{ document_a_id: uuid, document_b_id: uuid }`.
- **Response 202:** `{ id: uuid, status: "processing" }`. Runs on the background worker (`langgraph.md` Comparison graph).
- **Errors:** `404` if either document isn't owned by the caller | `409 document_not_ready` if either isn't `status=ready` | `422 identical_documents` if `document_a_id == document_b_id` (mirrors the DB `CHECK` constraint in `database.md` §3.12).

### `GET /api/v1/comparisons/{id}`
- **Auth:** required. **Fulfills:** `FR-COMP-002`.
- **Response 200:** `{ id, document_a_id, document_b_id, status, result: ComparisonResult|null, created_at }`. `result` is `null` while `status="processing"`.
  - `ComparisonResult`: `{ alignment_quality: "high"|"medium"|"low", message: string|null, additions: ComparisonSegment[], deletions: ComparisonSegment[], modifications: ComparisonModification[] }`. When the two documents are too structurally dissimilar for meaningful semantic alignment (`FR-COMP-003`), `alignment_quality="low"`, `message` carries the explanatory text, and `additions`/`deletions`/`modifications` are empty arrays instead of a forced diff.
  - `ComparisonSegment` (a pure addition or deletion — content on only one side): `{ document: "a"|"b", page_number: int|null, excerpt: string }`.
  - `ComparisonModification` (an aligned pair with a detected change on both sides): `{ change_type: "factual"|"numeric"|"wording", a_page_number: int|null, a_excerpt: string, b_page_number: int|null, b_excerpt: string, explanation: string }` — the three categories `ui-ux.md` §11's `ChangeTypeBadge` renders (`langgraph.md` §5's Change Classification node lists these as its concrete categories).
- **Errors:** `404`.

### `GET /api/v1/comparisons`
- **Auth:** required. **Fulfills:** `FR-COMP-002` (history).
- **Query params:** `limit`, `offset`.
- **Response 200:** paginated `{ id, document_a_id, document_b_id, status, created_at }` for the caller's past comparisons.

---

## 8. `/search`

### `GET /api/v1/search`
- **Auth:** required. **Fulfills:** `FR-SEARCH-001`, `FR-SEARCH-002`, `FR-SEARCH-003`.
- **Query params:** `q` (required, string, min 1 char) · `limit`, `offset` · `mime_type` (optional filter, `FR-SEARCH-002`) · `tag_id` (optional) · `status` (optional) · `date_from`/`date_to` (optional, ISO 8601 date).
- **Response 200:** paginated `{ document_id, file_name, snippet: SearchSnippet, relevance_score: float, matched_page: int|null }`, one row per matching chunk (a document with several matching chunks yields several rows sharing the same `document_id` — the client groups these into one result card, per `ui-ux.md` §12's "potentially multiple snippets per document"). Ranked by the hybrid keyword (Postgres `tsvector`) + vector similarity score defined in `rag.md` §Hybrid Search (`FR-SEARCH-003`). Always scoped to the caller's own, non-deleted documents (`NFR-SEC-001`).
  - `SearchSnippet`: `{ text: string, highlights: [{ start: int, end: int }] }` — `text` is the raw excerpt (plain text, taken verbatim from the document — untrusted per `CLAUDE.md` §6) and `highlights` are character-offset ranges into `text` marking the matched term(s). Offsets, not embedded markup: document content is untrusted input, so the API never returns pre-built HTML/`<mark>` tags for the client to inject — the client wraps each `[start, end)` range in a real `<mark>` element itself over the escaped text, satisfying `ui-ux.md` §12's "`<mark>` semantics" requirement without ever rendering document-derived text as markup.
- **Errors:** `422` if `q` is empty or `date_from` > `date_to`.

---

## 9. `/analytics`

### `GET /api/v1/analytics/dashboard`
- **Auth:** required. **Fulfills:** `FR-ANALYTICS-001`.
- **Query params:** `period` (optional: `7d`|`30d`|`90d`, default `30d`).
- **Response 200:** `{ documents_processed: int, documents_over_time: [{ date, count }], ai_requests: int, ai_requests_over_time: [{ date, count }], storage_used_bytes: int, most_used_features: [{ feature: string, count: int }] }`. Computed at query time from `documents` and `ai_requests` (no dedicated analytics table for MVP — `database.md` §6 traceability).

### `GET /api/v1/analytics/documents/{id}`
- **Auth:** required. **Fulfills:** `FR-ANALYTICS-002` (P2).
- **Response 200:** `{ document_id, view_count: int, chat_message_count: int, extraction_count: int, comparison_count: int, last_accessed_at: ts|null }`.
- **Errors:** `404`.

---

## 10. `/export`

### `POST /api/v1/export/summaries/{summary_id}`
- **Auth:** required. **Fulfills:** `FR-EXPORT-001`.
- **Request:** `{ format: "pdf"|"markdown" }`.
- **Response 200:** `{ download_url: string, expires_in: int }` — generated synchronously (small, fast artifact; not queued like the full account export).
- **Errors:** `404` summary not owned | `422 unsupported_format`.

### `POST /api/v1/export/extractions/{extraction_id}`
- **Auth:** required. **Fulfills:** `FR-EXPORT-001` (extraction results, same requirement as summary export).
- **Request:** `{ format: "pdf"|"markdown" }`.
- **Response 200:** `{ download_url: string, expires_in: int }`.
- **Errors:** `404` | `422 unsupported_format`.

### `POST /api/v1/export/comparisons/{id}`
- **Auth:** required. **Fulfills:** `FR-EXPORT-002` (P2).
- **Request:** `{ format: "pdf" }` (comparison export is PDF-only per requirement scope).
- **Response 200:** `{ download_url: string, expires_in: int }`.
- **Errors:** `404` | `409 not_completed` if `comparisons.status != completed`.

### `POST /api/v1/export/conversations/{id}`
- **Auth:** required. **Fulfills:** `FR-EXPORT-003` (P2).
- **Request:** `{ format: "markdown" }` (conversation export is Markdown-only, preserving citations inline).
- **Response 200:** `{ download_url: string, expires_in: int }`.
- **Errors:** `404`.

### `POST /api/v1/export/account`
- **Auth:** required. **AI rate limit does not apply** (not AI-invoking); general limit only. **Fulfills:** `FR-EXPORT-004`.
- **Request:** none.
- **Response 202:** `{ export_id: uuid, status: "processing" }` — a background job assembles a machine-readable JSON bundle of the caller's documents metadata, extractions, comparisons, and conversation transcripts (raw document files excluded by default per `privacy.md` §6 data-portability scope).

### `GET /api/v1/export/account/{export_id}`
- **Auth:** required. **Fulfills:** `FR-EXPORT-004`.
- **Response 200:** `{ status: "processing"|"ready"|"failed", download_url: string|null, expires_in: int|null }`.
- **Errors:** `404`.

---

## 11. `/settings`

### `GET /api/v1/settings/notifications`
- **Auth:** required. **Fulfills:** `FR-SETTINGS-001` (P2).
- **Response 200:** `{ processing_complete_email: bool, weekly_digest_email: bool }`.

### `PATCH /api/v1/settings/notifications`
- **Auth:** required. **Fulfills:** `FR-SETTINGS-001` (P2).
- **Request (partial):** `{ processing_complete_email?: bool, weekly_digest_email?: bool }`.
- **Response 200:** updated preferences (same shape as `GET`).

### `GET /api/v1/settings/api-keys` · `POST /api/v1/settings/api-keys` · `DELETE /api/v1/settings/api-keys/{id}`
- **Auth:** required. **Fulfills:** `FR-SETTINGS-002` (P2 — **Post-MVP per `requirements.md` priority**; contract reserved here so the frontend can build against a stable shape, but every route in this group returns `501 Not Implemented` with `{"error":{"code":"not_implemented","message":"API keys are not yet available."}}` until the Post-MVP phase that implements them, per `roadmap.md`).

---

## 12. `/admin`

Every route in this section requires `role="admin"` on the authenticated user; a non-admin caller (valid token, wrong role) gets `403` — this is the one place in the API where `403` is the correct code, since it's a role check rather than a tenant-ownership check (§0.4). Per `NFR-PRIV-004`, no admin route ever returns document content, chat content, or extracted field values — account/operational metadata only.

### `GET /api/v1/admin/users`
- **Auth:** required, admin. **Fulfills:** `FR-ADMIN-001`.
- **Query params:** `limit`, `offset` · `status` (optional) · `plan` (optional).
- **Response 200:** paginated `{ id, email, display_name, plan, status, role, created_at }`.

### `GET /api/v1/admin/system/health`
- **Auth:** required, admin. **Fulfills:** `FR-ADMIN-002`.
- **Response 200:** `{ queue_depth: int, processing_failure_rate_24h: float, ai_requests_24h: int, ai_error_rate_24h: float }` — aggregate operational metrics only, sourced from `ai_requests` and the RQ queue (`observability.md`).

### `POST /api/v1/admin/users/{id}/suspend`
- **Auth:** required, admin. **Fulfills:** `FR-ADMIN-003`.
- **Request:** `{ reason: string }`.
- **Response 200:** `{ id, status: "suspended" }`.
- **Side effects:** sets `users.status='suspended'`, revokes all of that user's `refresh_tokens` immediately (login blocked without touching their data), writes an `audit_logs` row (`action="admin_suspend_user"`, `user_id`=admin actor, `target_user_id`=suspended user, `metadata_json`={reason}).
- **Errors:** `404` unknown `id`.

### `POST /api/v1/admin/users/{id}/unsuspend`
- **Auth:** required, admin. **Fulfills:** `FR-ADMIN-003`.
- **Response 200:** `{ id, status: "active" }`. Writes an `audit_logs` row (`action="admin_unsuspend_user"`).
- **Errors:** `404` unknown `id`, `409 not_suspended` if the account isn't currently suspended.

---

## 13. Traceability

Every endpoint above cites its fulfilled requirement ID(s) inline. `ui-ux.md` pages reference these endpoint paths rather than re-describing request/response shapes. `security.md` and `testing.md` treat this file as the definitive list of authenticated surfaces requiring authorization tests — the standard suite per resource-owning endpoint is one happy-path test, one cross-tenant-404 test, and one unauthenticated-401 test (`testing.md` §Backend Testing). `ai.md`/`langgraph.md`/`rag.md` own everything that happens *inside* the AI-invoking endpoints (`/chat/*/messages`, `/summaries`, `/extractions`, `/comparisons`) once the request has passed this contract's validation.
