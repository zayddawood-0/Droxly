# Doxly — Requirements Specification

> Source of truth for **what Doxly must do**. Every requirement has a unique, stable ID. Other specs (`design.md`, `architecture.md`, `api.md`, `ui-ux.md`, `ai.md`, `langgraph.md`, `rag.md`, `security.md`, `testing.md`) MUST reference these IDs rather than restating requirements. See `roadmap.md` for phase-to-requirement mapping and `testing.md` for requirement-to-test mapping.

## ID scheme

| Prefix | Domain |
|---|---|
| `FR-AUTH-xxx` | Authentication & session management |
| `FR-USER-xxx` | User profile & account management |
| `FR-DOC-xxx` | Document upload & management |
| `FR-PROC-xxx` | Document processing pipeline |
| `FR-RAG-xxx` | Retrieval-augmented generation (indexing & retrieval mechanics) |
| `FR-AI-xxx` | AI chat / conversational Q&A |
| `FR-SUM-xxx` | Summarization |
| `FR-EXT-xxx` | Structured extraction |
| `FR-COMP-xxx` | Document comparison |
| `FR-SEARCH-xxx` | Global search |
| `FR-ANALYTICS-xxx` | Analytics & usage insights |
| `FR-EXPORT-xxx` | Export |
| `FR-SETTINGS-xxx` | Settings |
| `FR-ADMIN-xxx` | Administration |
| `NFR-PERF-xxx` | Performance |
| `NFR-SEC-xxx` | Security |
| `NFR-PRIV-xxx` | Privacy |
| `NFR-AVAIL-xxx` | Availability & reliability |
| `NFR-SCALE-xxx` | Scalability |
| `NFR-A11Y-xxx` | Accessibility |
| `NFR-OBS-xxx` | Observability |
| `NFR-MAINT-xxx` | Maintainability |

Priority scale: **P0** (MVP-blocking) · **P1** (important, can trail P0 by one phase) · **P2** (post-MVP nice-to-have, included here for completeness/roadmap planning).

---

## 1. Functional Requirements

### 1.1 Authentication (`FR-AUTH`)

#### FR-AUTH-001 — Email/password registration
- **Priority:** P0
- **Description:** A visitor can create an account with email + password.
- **Preconditions:** Email is not already registered.
- **Expected behavior:** System validates email format, password strength (min 8 chars, at least one letter and one number), hashes password with argon2, creates a `users` row with `plan=free`, sends a verification email.
- **Acceptance criteria:**
  - Given a valid, unused email and a compliant password, when the user submits registration, then a user record is created and a verification email is queued.
  - Given an already-registered email, when registration is submitted, then the request fails with a generic "unable to register" error (does not reveal account existence — see `NFR-SEC-006`).
  - Given a weak password, when registration is submitted, then a field-level validation error is returned before any DB write.

#### FR-AUTH-002 — Email verification
- **Priority:** P1
- **Description:** A newly registered user must verify their email before full access.
- **Expected behavior:** Verification link/token expires after 24 hours; unverified users can log in but see a persistent verification banner and cannot upload documents.
- **Acceptance criteria:** Given a valid unexpired token, when visited, then `users.email_verified_at` is set. Given an expired token, then the user can request a new one.

#### FR-AUTH-003 — Google OAuth login
- **Priority:** P0 (see `decisions.md` OQ-01)
- **Description:** A user can register/log in via Google OAuth2.
- **Expected behavior:** On first OAuth login, a `users` row is created with `email_verified_at` set immediately (Google-verified) and no password hash. Subsequent logins match on provider + provider account ID.
- **Acceptance criteria:** Given a Google account not previously seen, when OAuth completes, then a new user is created and logged in. Given an email that already exists via password signup, when the same email completes Google OAuth, then the accounts are linked, not duplicated.

#### FR-AUTH-004 — Login (email/password)
- **Priority:** P0
- **Description:** A registered user logs in with email + password.
- **Expected behavior:** On success, backend issues an access token (15 min) and refresh token (30 days) as httpOnly cookies. On failure, a generic "invalid credentials" error is returned, with progressive rate limiting after repeated failures (`NFR-SEC-002`).
- **Acceptance criteria:** Given correct credentials, then cookies are set and the user is redirected to the dashboard. Given 5 failed attempts within 10 minutes, then further attempts are throttled for that account/IP pair.

#### FR-AUTH-005 — Session refresh
- **Priority:** P0
- **Description:** Access tokens are silently refreshed using the refresh token before expiry.
- **Acceptance criteria:** Given a valid, non-revoked refresh token and an expired access token, when any API call is made, then a new access token is issued transparently without the user re-entering credentials.

#### FR-AUTH-006 — Logout
- **Priority:** P0
- **Description:** A user can end their session on the current device.
- **Acceptance criteria:** Given an active session, when logout is triggered, then both cookies are cleared and the refresh token is revoked server-side.

#### FR-AUTH-007 — Password reset
- **Priority:** P0
- **Description:** A user who forgot their password can reset it via emailed link.
- **Acceptance criteria:** Given a valid unexpired reset token, when a new password is submitted, then the password hash is updated and all existing refresh tokens for the account are revoked (forces re-login everywhere).

#### FR-AUTH-008 — Session/device management
- **Priority:** P1
- **Description:** A user can view active sessions and revoke individual ones.
- **Acceptance criteria:** Given multiple active refresh tokens, when the user views Settings → Security, then each session shows device/browser and last-active time; revoking one invalidates that refresh token only.

### 1.2 User & Account Management (`FR-USER`)

#### FR-USER-001 — View/edit profile
- **Priority:** P0
- **Description:** A user can view and edit display name, avatar, and email (email change requires re-verification).
- **Acceptance criteria:** Given a profile edit, when saved, then changes persist and are reflected immediately in the UI.

#### FR-USER-002 — Account deletion
- **Priority:** P0
- **Description:** A user can permanently delete their account and all associated data.
- **Preconditions:** User confirms via a typed confirmation (e.g., typing their email) — see `NFR-SEC` on destructive actions.
- **Expected behavior:** Soft-deletes the user record immediately (login disabled), hard-deletes all documents, chunks, embeddings, conversations, extractions within 30 days per `privacy.md` retention policy, cascades to object storage.
- **Acceptance criteria:** Given confirmed deletion, then the user cannot log in immediately, and a background job purges all owned data within the retention window.

#### FR-USER-003 — View plan & usage
- **Priority:** P1
- **Description:** A user can see their current plan (free/pro), storage used vs. quota, and AI request usage vs. daily limit.
- **Acceptance criteria:** Given any authenticated user, when viewing Settings → Plan, then current usage figures are accurate as of the last completed action (not stale beyond a few seconds).

### 1.3 Document Upload & Management (`FR-DOC`)

#### FR-DOC-001 — Upload a document
- **Priority:** P0
- **Description:** A user uploads a PDF, DOCX, TXT, or CSV file.
- **Preconditions:** User is authenticated and verified; file size ≤ per-plan limit (`decisions.md` OQ-06); user has not exceeded storage quota (OQ-07).
- **Expected behavior:** Client requests a presigned upload URL, uploads directly to object storage, then confirms upload to the backend, which creates a `documents` row with `status=queued` and enqueues processing (`FR-PROC-001`).
- **Acceptance criteria:**
  - Given a supported file type under the size limit, when uploaded, then a `documents` row is created with the correct `status`, `mime_type`, `size_bytes`, and `checksum`.
  - Given an unsupported file type, then the upload is rejected client-side and server-side (MIME sniffing, not just extension — see `NFR-SEC-004`).
  - Given a file that would exceed the user's storage quota, then the upload is rejected with a clear quota error before any storage write.

#### FR-DOC-002 — List documents
- **Priority:** P0
- **Description:** A user views all their documents with status, type, size, upload date, and tags.
- **Acceptance criteria:** Given N owned documents, when the list is requested, then only that user's documents are returned (never another user's — `NFR-SEC-001`), paginated, sortable by date/name/size, filterable by status/tag/type.

#### FR-DOC-003 — View document detail / viewer
- **Priority:** P0
- **Description:** A user opens a document to view its content, metadata, and processing status.
- **Acceptance criteria:** Given a `ready` document, then the viewer renders extracted text/pages with the original file available for download. Given a `processing` document, then a progress indicator is shown instead of content.

#### FR-DOC-004 — Rename document
- **Priority:** P1
- **Acceptance criteria:** Given a new non-empty name, when saved, then the display name updates without affecting the underlying stored file.

#### FR-DOC-005 — Delete document
- **Priority:** P0
- **Description:** A user deletes a document they own.
- **Expected behavior:** Soft-delete (`deleted_at` set) immediately removes it from all lists/search/RAG retrieval; hard-delete (object storage + chunks + embeddings) runs via background job within the retention window.
- **Acceptance criteria:** Given a delete request on an owned document, then it disappears from all queries immediately and is unrecoverable via the UI. Given a delete request on a document not owned by the requester, then the request is rejected with 404 (not 403, to avoid existence leakage).

#### FR-DOC-006 — Tag documents
- **Priority:** P1
- **Description:** A user can create tags and apply multiple tags to a document.
- **Acceptance criteria:** Given a new tag name, when applied, then it is created (if new) scoped to that user and associated with the document via `document_tags`.

#### FR-DOC-007 — Bulk actions
- **Priority:** P2
- **Description:** A user can select multiple documents and delete or tag them in one action.

#### FR-DOC-008 — Upload progress & processing status visibility
- **Priority:** P0
- **Description:** The UI reflects real-time (or near-real-time) processing status: `queued → extracting → chunking → embedding → ready` or `failed`.
- **Acceptance criteria:** Given a document mid-pipeline, when the user views it, then the current stage is shown and updates without a full page reload (polling or SSE).

### 1.4 Document Processing (`FR-PROC`)

#### FR-PROC-001 — Text extraction
- **Priority:** P0
- **Description:** Extract clean text (plus page/section metadata where applicable) from an uploaded file per `document-processing.md`.
- **Acceptance criteria:** Given a valid PDF/DOCX/TXT/CSV, when processed, then extracted text is stored and page numbers (PDF) or row structure (CSV) are preserved as chunk metadata.

#### FR-PROC-002 — Chunking
- **Priority:** P0
- **Description:** Extracted text is split into retrieval-sized chunks with overlap, per the chunking strategy in `rag.md`.
- **Acceptance criteria:** Given extracted text, when chunked, then each chunk is within the configured token range and carries `document_id`, `chunk_index`, `page_number` (if applicable), and character offsets.

#### FR-PROC-003 — Embedding generation
- **Priority:** P0
- **Description:** Each chunk is embedded and stored in `document_chunks.embedding` (pgvector).
- **Acceptance criteria:** Given N chunks for a document, when embedding completes, then N rows exist with non-null embeddings of the configured dimension, and `documents.status` transitions to `ready`.

#### FR-PROC-004 — Processing failure handling
- **Priority:** P0
- **Description:** If any pipeline stage fails (corrupt file, unsupported encoding, empty extractable text), the document is marked `failed` with a user-facing reason, not left `processing` forever.
- **Acceptance criteria:** Given a corrupt/password-protected PDF, when processing fails, then `documents.status=failed` and `documents.processing_error` contains a user-safe message (no stack traces / internals — `NFR-SEC-009`).

#### FR-PROC-005 — Reprocessing
- **Priority:** P1
- **Description:** A user can retry processing for a `failed` document (e.g., after the transient cause is resolved).

### 1.5 RAG / Retrieval (`FR-RAG`)

#### FR-RAG-001 — Semantic retrieval for a query
- **Priority:** P0
- **Description:** Given a natural-language query scoped to a document or the user's whole corpus, retrieve the top-k most relevant chunks via vector similarity, filtered to the requesting user's own documents.
- **Acceptance criteria:** Given a query and a target document, then only chunks from that document (and that user) are candidates. Given a query with no document filter ("ask across all my docs"), then candidates are drawn only from the user's own `ready` documents.

#### FR-RAG-002 — Citation grounding
- **Priority:** P0
- **Description:** Every AI answer that draws on retrieved chunks must reference which chunk(s)/document(s)/page(s) it used.
- **Acceptance criteria:** Given a generated answer, then each factual claim maps to at least one citation with `document_id`, `page_number` (if applicable), and a snippet; answers with zero relevant retrieved context say so explicitly rather than fabricating an answer (`FR-AI-004`).

#### FR-RAG-003 — Retrieval failure / empty corpus handling
- **Priority:** P0
- **Description:** If retrieval returns no chunks above a relevance threshold, the system responds that it cannot answer from the available documents rather than falling back to ungrounded generation.

### 1.6 AI Chat (`FR-AI`)

#### FR-AI-001 — Start a conversation about a document
- **Priority:** P0
- **Description:** A user opens a chat scoped to a specific document and asks questions.
- **Acceptance criteria:** Given a `ready` document, when the user sends a message, then a `conversations` row (if new) and a `messages` row are created, the LangGraph Document Q&A workflow runs, and a grounded, cited response streams back.

#### FR-AI-002 — Multi-document / workspace-wide chat
- **Priority:** P1
- **Description:** A user can ask a question across all (or a selected subset of) their documents.
- **Acceptance criteria:** Given multiple selected documents, then retrieval spans only those documents and citations disambiguate which document each fact came from.

#### FR-AI-003 — Conversation history
- **Priority:** P0
- **Description:** Past messages in a conversation persist and are used as context for follow-up questions.
- **Acceptance criteria:** Given a follow-up question referring to a prior answer ("what about section 3?"), then the workflow has access to prior turns (bounded by the context window strategy in `ai.md`).

#### FR-AI-004 — Graceful "I don't know"
- **Priority:** P0
- **Description:** When the answer isn't supported by retrieved content, the assistant says so instead of hallucinating.
- **Acceptance criteria:** Given a question unrelated to the document's content, then the response explicitly states the document doesn't contain that information, with no fabricated citation.

#### FR-AI-005 — Streaming responses
- **Priority:** P1
- **Description:** Chat responses stream token-by-token to the UI rather than waiting for full completion.

#### FR-AI-006 — Regenerate / stop response
- **Priority:** P2
- **Description:** A user can stop an in-progress generation or regenerate the last answer.

### 1.7 Summarization (`FR-SUM`)

#### FR-SUM-001 — Generate document summary
- **Priority:** P0
- **Description:** A user requests a summary of a `ready` document at a chosen length/detail level (brief / detailed / bullet points).
- **Acceptance criteria:** Given a document and a summary type, when requested, then a summary is generated via the LangGraph Summarization workflow, passes a quality check node, and is persisted for reuse (not regenerated on every view).

#### FR-SUM-002 — Re-generate summary
- **Priority:** P1
- **Description:** A user can request a fresh summary (e.g., different length) which does not overwrite the previous one silently — prior summaries remain accessible.

### 1.8 Structured Extraction (`FR-EXT`)

#### FR-EXT-001 — Extract structured fields from a document
- **Priority:** P0
- **Description:** A user defines (or selects a preset) schema of fields to extract (e.g., invoice number, dates, parties, amounts) and runs extraction.
- **Acceptance criteria:** Given a document and a field schema, when extraction runs, then a structured JSON result validated against that schema is produced, with per-field confidence and source citation (page/snippet).

#### FR-EXT-002 — Preset extraction templates
- **Priority:** P1
- **Description:** Common templates (invoice, contract, resume, research paper) are offered so users don't need to define schemas from scratch.

#### FR-EXT-003 — Extraction validation & correction
- **Priority:** P1
- **Description:** Extracted fields that fail schema validation (wrong type, missing required field) are flagged rather than silently returned as if correct.
- **Acceptance criteria:** Given a required field the model could not find, then the field is returned as `null` with a `not_found` reason, never a fabricated placeholder value.

#### FR-EXT-004 — Edit extracted values
- **Priority:** P2
- **Description:** A user can manually correct an extracted value; corrections persist with the extraction record.

### 1.9 Document Comparison (`FR-COMP`)

#### FR-COMP-001 — Compare two documents
- **Priority:** P0
- **Description:** A user selects two documents (or two versions) and requests a comparison.
- **Acceptance criteria:** Given Document A and Document B (both `ready`), when compared, then the LangGraph Comparison workflow produces a structured report of additions, deletions, and modifications with semantic alignment (not naive line diff), classified by change type (e.g., factual change, wording change, numeric change).

#### FR-COMP-002 — View comparison report
- **Priority:** P0
- **Description:** The comparison result is rendered with side-by-side or unified diff-style highlighting, and is persisted for later viewing.

#### FR-COMP-003 — Compare documents of different types/lengths
- **Priority:** P2
- **Description:** Comparison degrades gracefully (clear messaging) when documents are too structurally different for meaningful alignment (e.g., a resume vs. a contract).

### 1.10 Global Search (`FR-SEARCH`)

#### FR-SEARCH-001 — Search across all owned documents
- **Priority:** P0
- **Description:** A user searches by keyword/semantic query across all their documents' content and metadata.
- **Acceptance criteria:** Given a query, when submitted, then results include matching documents ranked by relevance with highlighted snippets, scoped strictly to the requesting user.

#### FR-SEARCH-002 — Filter search results
- **Priority:** P1
- **Description:** Search results can be filtered by document type, tag, date range, and processing status.

#### FR-SEARCH-003 — Hybrid search (keyword + semantic)
- **Priority:** P1
- **Description:** Search combines full-text (Postgres `tsvector`) and vector similarity for both precision on exact terms and recall on semantic matches. See `rag.md` §Hybrid Search.

### 1.11 Analytics (`FR-ANALYTICS`)

#### FR-ANALYTICS-001 — Personal usage dashboard
- **Priority:** P1
- **Description:** A user sees stats: documents processed over time, storage used, AI requests made, most-used features.

#### FR-ANALYTICS-002 — Document insights
- **Priority:** P2
- **Description:** Per-document stats: times viewed, times asked-about, last accessed.

### 1.12 Export (`FR-EXPORT`)

#### FR-EXPORT-001 — Export summary/extraction as PDF or Markdown
- **Priority:** P1
- **Description:** A user exports a generated summary or extraction result as a downloadable file.

#### FR-EXPORT-002 — Export comparison report
- **Priority:** P2
- **Description:** A user exports a comparison report as PDF.

#### FR-EXPORT-003 — Export chat conversation
- **Priority:** P2
- **Description:** A user exports a chat transcript (with citations) as Markdown.

#### FR-EXPORT-004 — Full account data export
- **Priority:** P1
- **Description:** A user can request a machine-readable export of all their data (documents metadata, extractions, conversations) per `privacy.md` data portability requirements.

### 1.13 Settings (`FR-SETTINGS`)

#### FR-SETTINGS-001 — Notification preferences
- **Priority:** P2
- **Description:** A user configures which email notifications they receive (processing complete, weekly digest, etc.).

#### FR-SETTINGS-002 — API key management (future public API)
- **Priority:** P2
- **Description:** A user can generate/revoke personal API keys for programmatic access. Marked P2/Post-MVP — see `roadmap.md`.

### 1.14 Administration (`FR-ADMIN`)

#### FR-ADMIN-001 — Admin user directory
- **Priority:** P1
- **Description:** An internal admin (role `admin`) can view a list of users, plan, signup date, and account status, for support purposes — never document content.
- **Acceptance criteria:** Given an admin session, when viewing the admin user list, then no document content, chat content, or extracted field values are visible — only account/operational metadata (`NFR-PRIV-004`).

#### FR-ADMIN-002 — System health & processing queue visibility
- **Priority:** P1
- **Description:** An admin can see aggregate processing queue depth, failure rates, and AI request volume (see `observability.md`).

#### FR-ADMIN-003 — Suspend a user account
- **Priority:** P1
- **Description:** An admin can suspend an account (e.g., abuse/ToS violation), immediately revoking all sessions and blocking login, without deleting data.

---

## 2. Non-Functional Requirements

### 2.1 Performance (`NFR-PERF`) — detailed budgets in `performance.md`

- **NFR-PERF-001** (P0): First Contentful Paint on dashboard ≤ 1.5s on a warm cache, broadband connection.
- **NFR-PERF-002** (P0): Standard CRUD API endpoints (non-AI) respond within 300ms p95.
- **NFR-PERF-003** (P0): AI chat first-token latency ≤ 3s p95 for documents under 50 pages.
- **NFR-PERF-004** (P1): A 20-page PDF completes the full processing pipeline (extract → chunk → embed → ready) within 60s p95.
- **NFR-PERF-005** (P1): Vector similarity search over a single user's corpus returns within 200ms p95 at up to 50,000 chunks.

### 2.2 Security (`NFR-SEC`) — detailed in `security.md`

- **NFR-SEC-001** (P0): A user can never read, modify, or delete another user's documents, conversations, extractions, comparisons, or embeddings, under any code path (enforced at the repository layer, not just the API layer).
- **NFR-SEC-002** (P0): Authentication endpoints are rate-limited and apply progressive backoff on repeated failures.
- **NFR-SEC-003** (P0): All uploaded files are treated as untrusted: validated by content-sniffed MIME type (not just extension/declared content-type), scanned for size limits before processing, and never executed or served with an executable content-type.
- **NFR-SEC-004** (P0): File uploads are stored with generated, non-guessable storage keys (never derived from user-supplied filenames) to prevent path traversal.
- **NFR-SEC-005** (P0): All database queries use parameterized statements (SQLAlchemy ORM/Core) — no raw string-interpolated SQL.
- **NFR-SEC-006** (P0): Auth error messages never reveal whether an email exists in the system.
- **NFR-SEC-007** (P0): The system defends against prompt injection from document content: extracted document text is never concatenated into a system-level/instruction-privileged position in the prompt; content injected via documents cannot alter the assistant's tool-use permissions or safety behavior. See `security.md` §AI Prompt Injection Defense.
- **NFR-SEC-008** (P0): LLM/system prompts, internal chain-of-thought, and API keys/secrets are never exposed in any API response or client-visible log.
- **NFR-SEC-009** (P0): Error responses to clients never include stack traces, SQL, internal file paths, or library version details.
- **NFR-SEC-010** (P1): CSRF protection on all state-changing cookie-authenticated requests.
- **NFR-SEC-011** (P1): Standard security headers (CSP, X-Content-Type-Options, X-Frame-Options/frame-ancestors, Strict-Transport-Security) are set on all responses.

### 2.3 Privacy (`NFR-PRIV`) — detailed in `privacy.md`

- **NFR-PRIV-001** (P0): Document content and chat content are never logged in plaintext in application logs (`observability.md` §Never-Log List).
- **NFR-PRIV-002** (P0): A user's account deletion request triggers irreversible purge of their content within the documented retention window.
- **NFR-PRIV-003** (P0): Data sent to third-party LLM/embedding providers is limited to what's necessary for the requested operation; provider data-retention settings are configured to the most restrictive option the provider offers (e.g., zero-retention/no-training APIs where available).
- **NFR-PRIV-004** (P0): Administrative tooling never exposes document content, extracted values, or chat content to admins — only operational metadata.

### 2.4 Availability & Reliability (`NFR-AVAIL`)

- **NFR-AVAIL-001** (P1): Core document CRUD and chat remain available even if the LangGraph/AI subsystem is degraded (fails closed with a clear "AI temporarily unavailable" state, not a hard crash of the whole page).
- **NFR-AVAIL-002** (P1): Background job failures are retried with exponential backoff (max 3 attempts) before being marked `failed` for user visibility.

### 2.5 Scalability (`NFR-SCALE`)

- **NFR-SCALE-001** (P1): The backend is horizontally scalable (stateless API containers behind a load balancer; session state lives in JWT/DB, not in-process memory).
- **NFR-SCALE-002** (P1): The worker pool scales independently from the API (separate container/process count) since processing load and request load do not correlate 1:1.

### 2.6 Accessibility (`NFR-A11Y`) — detailed in `ui-ux.md`

- **NFR-A11Y-001** (P1): All primary flows (auth, upload, chat, search) meet WCAG 2.1 AA: keyboard navigable, screen-reader labeled, sufficient color contrast.
- **NFR-A11Y-002** (P2): Reduced-motion preference is respected for animated UI elements.

### 2.7 Observability (`NFR-OBS`) — detailed in `observability.md`

- **NFR-OBS-001** (P0): Every AI request is logged with latency, token counts, provider/model used, and success/failure — never the prompt/response content itself in default logs.
- **NFR-OBS-002** (P1): Processing pipeline stage transitions are logged for every document to support debugging stuck/failed jobs.

### 2.8 Maintainability (`NFR-MAINT`)

- **NFR-MAINT-001** (P1): Backend code is organized into API / service / repository / AI / document-processing layers with no layer skipping (API routes never touch the DB directly — see `skills/backend.md`).
- **NFR-MAINT-002** (P1): Every LangGraph node is independently unit-testable with the LLM call mocked.

---

## 3. Traceability

See `roadmap.md` for the phase in which each requirement is implemented, and `testing.md` for the test(s) that verify each P0/P1 requirement. `api.md` and `ui-ux.md` reference these IDs directly in their endpoint/page specs rather than re-deriving behavior.
