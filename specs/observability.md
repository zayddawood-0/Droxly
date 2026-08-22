# Doxly — Observability Specification

> Defines how Doxly's three services (Next.js BFF, FastAPI backend, Background Worker — `architecture.md` §2) are logged, monitored, and traced, so operators can debug a slow AI workflow, a stuck document, or an error spike **without ever needing to look at a user's document or chat content to do so**. Expands `NFR-OBS-001` and `NFR-OBS-002` (`requirements.md` §2.7). This file owns the exhaustive, canonical **Never-Log List** — `security.md` and `privacy.md` state the governing principle (`NFR-PRIV-001`, `NFR-SEC-008`) and defer the full enumeration here; `testing.md` and `ai.md` reference this list rather than redefining it. `database.md` §3.13 (`ai_requests`) and §3.14 (`audit_logs`) are the two tables that embody this file's principles in schema form — this file explains why those tables are shaped the way they are and what surrounds them operationally.

---

## 1. The Never-Log List (Authoritative)

**This is the definitive list.** No other spec file redefines it — `security.md` §12, `privacy.md` §8, `testing.md`, and `ai.md` all point here. If a new data type is identified as sensitive after this file is written, it is added here first, then referenced elsewhere.

**Rule:** if a value could let someone reconstruct a user's document content, chat content, or credentials from a log entry, it does not go in a log — in any environment, including local development and debug-level logging. Logging code is written so the sensitive value is structurally unavailable at the log call site (passed a redacted DTO, not the raw object with a "just don't log this field" convention), not filtered by discipline alone.

| # | Never log | Why | Log this instead |
|---|---|---|---|
| 1 | Raw document content (extracted text or original file bytes) | Core content-privacy boundary (`NFR-PRIV-001`) | `document_id`, `size_bytes`, `mime_type`, `page_count`, processing stage |
| 2 | Chat message content (user or assistant turns) | Same content boundary; chat is user-authored + AI-generated content about the user's documents | `conversation_id`, `message_id`, `role`, `token_count` |
| 3 | LLM prompts and completions — system prompts, user queries as sent to the model, retrieved context injected into the prompt, model responses | Prompts embed document/chat content plus Doxly's proprietary prompt engineering (`NFR-SEC-008`) | `operation`, `provider`, `model`, `input_tokens`, `output_tokens`, `status` (i.e., the `ai_requests` row — §4) |
| 4 | Extracted structured field **values** (`extractions.result_json` content) | The values are the user's document content in structured form | `extraction_id`, `document_id`, the field **schema**/field **names** (`schema_json` keys are debugging-safe; the *values* found are not), per-field `status` (`found`/`not_found`) |
| 5 | Passwords — plaintext **or hashed** | A logged hash is still a credential artifact that should never leave the `users` table; logging it (even "for debugging") creates an unnecessary copy outside the access controls that protect that column | Nothing. Password verification outcome is `login_success`/`login_failed` in `audit_logs` — never the value on either side of the comparison |
| 5b | Raw JWT access tokens or refresh tokens | A logged token is a usable credential until it expires/is revoked (`security.md` §2.2) | A **token ID or hash reference** only, and only when needed to debug revocation (e.g., "revoked refresh token id=`abc123`" — never the token value itself, matching `refresh_tokens.token_hash`'s own never-store-raw rule) |
| 6 | API keys / secrets (LLM provider keys, embedding provider keys, DB credentials, OAuth client secrets, JWT signing secret) | `security.md` §8 — these must never leave server-side environment variables | Which secret/provider was *used* (e.g., `provider=anthropic`), never its value. Startup logs confirm a secret was *loaded*, never print it |
| 7 | Full request or response bodies for any endpoint that carries user content (chat messages, extraction schemas/results, comparison results, document uploads, profile fields) | Body logging is the single easiest way to accidentally capture every item on this list at once | Method, route (with path params as IDs, not resolved content), status code, duration — see §2 |
| 8 | Citation snippet text (`citations.snippet`) | The snippet **is** a quoted fragment of document content | `citation_id`, `document_chunk_id`, `document_id`, `page_number`, `relevance_score` |
| 9 | Full embedding vectors | High-dimensional vectors can approximately reconstruct semantic content and are large/noisy in logs regardless | `embedding_model`, `embedding_dim`, chunk `token_count` |
| 10 | Internal stack traces, raw exception messages, SQL text/fragments, internal file paths, library/framework version strings — **in any client-facing response** | `NFR-SEC-009` (`security.md` §11.2) — this is a *response* rule, not a *server-log* rule | These ARE logged server-side (§2.2) for debugging, tagged with the same `request_id` returned to the client, so support can correlate without exposing internals |
| 11 | Raw IP + email combinations beyond what `audit_logs`/`refresh_tokens` already store for their stated purpose | Avoid duplicating PII into a second, less access-controlled system (operational logs) alongside the tables designed to hold it under tighter retention/access rules (§9) | Reference the `user_id`; look up account/IP detail in `audit_logs`/`refresh_tokens` when an investigation actually needs it |

**Enforcement note:** log statements are code-reviewed against this list the same way SQL string interpolation is reviewed against `NFR-SEC-005` (`security.md` §6.1) — a blanket rule enforced structurally (helper functions that accept only allow-listed metadata fields for AI/document/chat-adjacent log call sites), not a per-statement judgment call. `testing.md` (parallel effort) is expected to include log-output assertions (e.g., a test that runs a chat turn through the system and greps captured log output for the message content, asserting it never appears) as a regression guard on this list.

---

## 2. Logging Principles

### 2.1 Structured logging
All three services (Next.js BFF, FastAPI, Worker — `architecture.md` §2) emit **structured JSON logs**, one JSON object per log line, never free-text string concatenation. A common minimum field set is enforced across all services:

```
{
  "timestamp": "...",
  "level": "info | warn | error",
  "service": "web | api | worker",
  "request_id": "...",
  "user_id": "... | null",
  "event": "request.completed",
  "...event-specific allow-listed fields..."
}
```

Structured logs are what make the Never-Log List (§1) enforceable in practice: because every log call goes through a small set of typed helper functions with a fixed field allow-list, there is no free-text field where a developer could accidentally interpolate a document snippet or a prompt "just this once."

### 2.2 Correlation across services
A single user action (e.g., "ask a question about a document") crosses Next.js → FastAPI → possibly the Worker (`architecture.md` §3–5). To trace that one action end-to-end without exposing content:

- A **`request_id`** (UUID) is generated at the Next.js BFF route handler — the edge of the system closest to the browser — for every incoming request that doesn't already carry one.
- It is forwarded to FastAPI as a request header (e.g., `X-Request-ID`) on every proxied call.
- FastAPI includes it in every log line emitted while handling that request, and returns it in the response (including error responses, per `security.md` §11.2 — this is the mechanism that lets a support interaction reference "request `abc-123`" without exposing internals).
- When FastAPI enqueues a job to Redis (`ADR-008`), `request_id` (and, where applicable, `document_id`/`conversation_id`) is included in the job payload's metadata — never document/chat content, per §1.
- The Worker logs using the same `request_id` for every log line tied to that job, so a single trace can be reconstructed by filtering logs on `request_id` alone across all three services, even though the actual processing may complete seconds or minutes after the originating HTTP request returned.
- Where a job is not tied to a single originating request (e.g., a scheduled purge job), a fresh `request_id` is generated at the job's entrypoint so it still has a stable trace key.

This gives engineering a way to answer "what happened to this user's action" by `request_id` lookup alone — the trace shows *which stages ran, in what order, how long each took, and whether each succeeded* — never *what the content was*.

---

## 3. Application Logging

What's logged at each layer, by event type:

| Event | Logged at | Fields (allow-listed; never body content) |
|---|---|---|
| Request received / completed | Next.js BFF, FastAPI | `request_id`, `method`, `route` (templated, e.g. `/documents/{id}`, not the resolved content), `status_code`, `duration_ms`, `user_id` |
| Unhandled exception | FastAPI, Worker | `request_id`, `route` or `job_name`, exception **type** and internal stack trace (server-side only — never returned to the client, per `NFR-SEC-009`; see `security.md` §11.2) |
| Document status transition | Worker, FastAPI | `document_id`, `user_id`, `from_status`, `to_status`, `duration_in_prior_stage_ms` (§8) |
| Job start / complete / fail | Worker | `job_id`, `job_type`, `request_id`, `status`, `duration_ms`, `retry_count` |
| Auth events (login, logout, token refresh, revocation) | FastAPI | mirrors `audit_logs` (§7) for the security-relevant subset; operational-only auth log lines (e.g., a token-refresh timing log) carry `user_id`, never the token value (§1 item 5b) |

**No request or response body is logged by default** for any route (§1 item 7). Where a specific field genuinely aids debugging (e.g., a validation error's field name and error code), it is added to the allow-list for that log call explicitly — never by logging the whole payload "for now."

---

## 4. API Logging — Every AI Request (`NFR-OBS-001`)

Every call to an LLM or embedding provider is logged with **latency, token counts, provider/model, and success/failure** — this is `NFR-OBS-001` verbatim, and it maps directly onto the `ai_requests` table (`database.md` §3.13), which is both the persisted record and the source for this logging:

| Log field | `ai_requests` column |
|---|---|
| `operation` | `operation` (`chat`/`summarization`/`extraction`/`comparison`/`embedding`) |
| `provider` | `provider` |
| `model` | `model` |
| `input_tokens` | `input_tokens` |
| `output_tokens` | `output_tokens` |
| `latency_ms` | `latency_ms` |
| `status` | `status` (`success`/`error`/`timeout`) |
| `error_code` | `error_code` |
| `user_id`, `request_id` | `user_id` (correlation via `created_at`/request context) |

**Prompt text and response text are never included in the `ai_requests` row or in any log record derived from it** (`database.md` §3.13's own note; restated here as the authoritative source per §1 item 3). A row/log entry answers "how expensive/slow/successful was this call," never "what was said."

An `ai_requests` row (and its mirrored log line) is written for **every** provider call, success or failure, including calls that time out or error before returning any tokens — a failed call is exactly the case an engineer most needs latency/error-code visibility into, so it is never silently dropped from logging because it didn't complete.

---

## 5. AI Logging — Beyond `ai_requests`

`ai_requests` captures the provider-call boundary. Debugging a stuck or slow LangGraph workflow (`decisions.md` ADR-004, `langgraph.md`) needs visibility **inside** a graph run — which node is running, how long each took, which conditional edge was taken — without ever surfacing what the node read or produced.

**Logged per LangGraph node execution:**
- `request_id`, `conversation_id` or `document_id` (whichever scopes the run)
- Node **name** (e.g., `classifier`, `retriever`, `answer_generator`, `citation_validator`)
- Node **duration**
- Which **conditional branch** was taken at a routing node (e.g., `retrieval_sufficient=true → answer_generator`, not the query or the retrieved content that produced that decision)
- Node outcome (`success`/`retry`/`error`)

**Never logged at the node level** (restating §1 in this specific context): the node's input state (query text, retrieved chunk content, conversation history) or output (generated text, reasoning/scratchpad content — `security.md` §9 already establishes that chain-of-thought is never persisted beyond `messages.content`'s final turn, and it is equally never logged).

This is sufficient to answer the operational questions that actually come up — "why is this chat request taking 12 seconds," "which node is this stuck job retrying on," "is the classifier misrouting a disproportionate share of requests to the wrong branch" — from node name + timing + branch alone, without any engineer with log-viewer access ever seeing a user's document or question. A log viewer accessible to on-call engineering therefore never becomes a de facto content-access surface, which is the property `NFR-PRIV-004` and `FR-ADMIN-001` require of *admin* tooling and that this section extends to *engineering* tooling as a design goal, not just a policy statement.

---

## 6. Error Tracking

**Tool category:** a Sentry-style error tracking service (frontend + backend SDKs, error grouping, release tracking, breadcrumbs) is recommended for both the Next.js frontend and the FastAPI/Worker backend. The specific vendor is an implementation detail; the configuration requirements below are not optional regardless of vendor choice.

**Required scrubbing configuration** — error tracking SDKs capture request context (headers, request body, local variables in a stack frame) automatically by default, which would otherwise silently defeat the Never-Log List. Before enabling error tracking in any environment:

- Request/response **body capture is disabled**, or an explicit scrubbing hook strips known content-bearing fields (chat `content`, extraction `result_json`, document text) before an event is sent — never sent-then-redacted-at-the-vendor, since that still transmits the raw content off-infrastructure.
- Cookie and Authorization header capture is disabled or scrubbed (session cookies / bearer tokens are credentials per §1 item 5b).
- Local-variable/stack-frame capture on exceptions is reviewed for any code path that could hold document/chat content in scope at the point of failure (e.g., an exception thrown inside the parsing or LLM-call path) — scrubbed by variable name pattern or disabled for those modules if the SDK can't selectively scrub.
- User context attached to an error event is limited to `user_id` (and `email` only if the tool is genuinely used for support triage and access to it is restricted per §9 — otherwise `user_id` alone, looked up separately when needed).

Error tracking captures unhandled exceptions and unexpected error-rate spikes as a complement to the structured application logs in §2–3 — logs answer "what happened in this specific request," error tracking answers "is this failure new/regressed/spiking across many requests," with grouping/deduplication logs alone don't provide.

---

## 7. Metrics

Aggregate, non-per-user-identifiable metrics (counters/histograms, not individual log lines tied to a specific user's identity beyond what's needed for the underlying query) tracked for operational and product-health visibility:

| Metric | Source |
|---|---|
| Request rate, latency (p50/p95), error rate — per endpoint | FastAPI/Next.js request logs (§3), aggregated |
| Queue depth, job processing time — per job type | Redis/RQ instrumentation |
| AI request volume, cost (derived from token counts × provider pricing), latency — by `operation` type | `ai_requests` table (§4) |
| Document processing success/failure rate | `documents.status` transitions (§8), aggregated |

These aggregate metrics — never raw per-user logs — are what feeds the admin **system health & processing queue visibility** view (`FR-ADMIN-002`, `requirements.md` §1.14): an admin sees "312 documents processed today, 98.7% success rate, p95 chat latency 2.1s," never a list of which user's document failed or what a failed extraction contained. This is the same content/metadata boundary `NFR-PRIV-004` draws for `FR-ADMIN-001`'s user directory, applied to the operational-health surface.

---

## 8. Processing Monitoring (`NFR-OBS-002`)

Every document's pipeline stage transition (`queued → extracting → chunking → embedding → ready`, or `→ failed` at any stage — `documents.status`, `database.md` §3.3, `FR-PROC-*`) is logged with:

- `document_id`, `user_id`
- `from_status`, `to_status`
- **Timestamp** of the transition
- **Duration in the prior stage** (time spent in `from_status` before transitioning)

This is enough to detect a document **stuck** in a stage beyond an expected threshold (e.g., "extracting" for over 5 minutes on a 10-page PDF is anomalous) purely from stage/duration data — an operational alerting candidate (alert on `p95` stage duration exceeded, or on a document remaining in a non-terminal stage past a fixed ceiling) without inspecting the document's actual content at any point. The same log stream is the basis for `FR-DOC-008`'s UI-facing progress indicator (the user-facing status is a read of the same underlying transitions, filtered to their own document) and for `FR-PROC-004`'s failure surfacing (`processing_error` is a separate, user-safe sanitized string — §1 item 10's server/client split applies here too: the internal cause of a stage failure is logged in full server-side, only a sanitized reason reaches `documents.processing_error`).

---

## 9. Audit Logs (expands `database.md` §3.14)

`audit_logs` is the **security-event trail**: a fixed, append-only vocabulary of WHAT happened, never document or chat CONTENT (`security.md` §12 already states this boundary; this section is the operational-logging counterpart).

**Fixed action vocabulary** (non-exhaustive core set; new actions are added to this enum deliberately, not ad hoc):

`login_success`, `login_failed`, `logout`, `password_reset`, `password_changed`, `email_changed`, `session_revoked`, `oauth_linked`, `account_created`, `account_deletion_requested`, `account_deleted`, `document_deleted`, `admin_suspend_user`, `admin_reinstate_user`

Each entry records actor (`user_id`), subject (`target_user_id`, for admin actions), the `action`, `ip_address`, and non-sensitive `metadata_json` (e.g., `{"document_id": "..."}` for `document_deleted` — never a filename or content) — never a value from the Never-Log List (§1).

**Retention is deliberately asymmetric from user content**, and this is a *repeat*, not a new decision: `privacy.md` §3 already establishes that `audit_logs` is retained for **~1 year**, independent of and longer than a user's document/account content retention (30 days post-deletion, per `privacy.md` §3/§5), because the audit trail contains no document content and its purpose — reconstructing a possible security incident — outlives the deleted account. This file's operational logs (§10) are shorter-lived still, since they're a debugging aid, not a security record.

---

## 10. Log Access Control & Retention

**Who can view logs:** operational logs (§2–3, §5, §8) and error-tracking data (§6) are accessible to **engineering / on-call only** — never exposed through customer-support tooling or the admin panel (`FR-ADMIN-001`). This mirrors and extends `NFR-PRIV-004`'s "admin tooling never exposes content" rule: admin tooling doesn't get a raw log viewer at all, because even a content-scrubbed log stream carries more operational surface (internal error detail, infrastructure identifiers) than a support workflow needs. Support/admin staff who need to investigate a specific user's issue work through `FR-ADMIN-001`'s account/operational-metadata view and, if genuinely necessary, request an engineering-mediated log lookup by `request_id` — never direct log-store access.

**Retention — time-bounded, distinct from `audit_logs`:**

| Log category | Retention | Rationale |
|---|---|---|
| Operational application/API/worker logs (§2–3, §5, §8) | **30–90 days** | Debugging window for recent incidents; no security/compliance reason to hold longer, and shorter retention reduces the blast radius of a log-store compromise |
| Error-tracking events (§6) | Per vendor default within the same 30–90 day order of magnitude, scrubbed per §6 regardless of the vendor's own default retention | Same debugging-window rationale |
| `ai_requests` (`database.md` §3.13) | **~90 days** (`privacy.md` §3) | Cost/abuse investigation window — metadata only, already content-free by design (§4) |
| `audit_logs` (`database.md` §3.14) | **~1 year** (`privacy.md` §3) | Security incident trail — intentionally the longest-lived log-like table, since it's the one built to outlive deleted accounts |

Operational logs are never retained "indefinitely by default" the way `audit_logs` and content tables have explicit, deliberate retention policies — a fixed, automated expiry (log-platform TTL or scheduled purge) is a required configuration item in `deployment.md`'s environment setup, not left to accumulate unbounded in the log store.

---

## 11. Traceability

| Requirement | Section(s) |
|---|---|
| NFR-OBS-001 | §4 |
| NFR-OBS-002 | §8 |
| NFR-PRIV-001 | §1, §3 |
| NFR-PRIV-004 | §5, §7, §10 |
| NFR-SEC-008 | §1 (items 3, 5b, 6) |
| NFR-SEC-009 | §1 (item 10), §3 |
| FR-ADMIN-001 | §5, §10 |
| FR-ADMIN-002 | §7 |
| FR-PROC-004, FR-DOC-008 | §8 |
| `database.md` §3.13 (`ai_requests`) | §1, §4 |
| `database.md` §3.14 (`audit_logs`) | §1, §9 |
| `security.md` §12 (audit logging) | §9 |
| `privacy.md` §3 (retention), §8 (logging restrictions) | §9, §10 |
