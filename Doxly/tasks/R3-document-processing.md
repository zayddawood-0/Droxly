# Task R3: Document Processing Remediation

## Task ID
R3-001

## Feature
Document Processing — the extract → chunk → embed pipeline: per-MIME-type parsers behind a `DocumentParser` interface, a parser registry, an RQ worker entrypoint, orchestration wiring the existing `chunking.py`/`EmbeddingService` to real parsed content, and the R2→R3 integration (`DocumentService.confirm_upload`/`reprocess_document` actually enqueue a job instead of leaving documents stuck in `queued`).

## Objective
Close the deepest gap identified by the API Router Gap Audit and `tasks/remediation-plan.md` §6 (R3): only `document_processing/chunking.py` existed (tested, but never invoked by anything real). No `DocumentParser` implementations, no worker entrypoint, no `rq` dependency existed. This task builds all of it so a confirmed upload actually reaches `documents.status='ready'` with real, embedded chunks, instead of sitting in `queued` forever (the documented, honest gap R2 left behind).

## Specification References
- `tasks/remediation-plan.md` §6 (R3) — authoritative scope for this task.
- `specs/requirements.md` §1.4 (`FR-PROC-001..005`).
- `specs/document-processing.md` (full) — parsing pipeline, MIME sniffing, per-type failure modes, states, retry policy, storage handoff, parser extensibility contract.
- `specs/rag.md` §2 (Chunking Strategy) — token targets, overlap, CSV row-group chunking, degenerate-input handling (already partially implemented in `chunking.py`).
- `specs/architecture.md` §4 (Document Processing Flow sequence diagram).
- `specs/decisions.md` ADR-008 (RQ/Redis), ADR-009 (StorageProvider), ADR-014 (parsing libraries).
- `specs/database.md` §3.3/§3.4 (`documents`/`document_chunks` — no schema change needed, columns already exist).
- `specs/security.md` §1, §5 (untrusted-input handling, MIME sniffing, sanitized errors), `NFR-SEC-009`.
- `specs/testing.md` §3.1–3.3 (unit/repository/API test conventions).
- `skills/backend.md` §12 (background processing: inline-vs-queued line, worker reuses the same service layer), §13 (async/blocking-call rules), §15 (folder structure: `document_processing/`, `workers/`).

## Requirements
- `FR-PROC-001` (P0) — text extraction (PDF/DOCX/TXT/CSV).
- `FR-PROC-002` (P0) — chunking (reuses existing `chunking.py`; adds CSV row-group chunking, not previously implemented).
- `FR-PROC-003` (P0) — embedding generation (reuses existing `EmbeddingService`/`EmbeddingProvider` unmodified).
- `FR-PROC-004` (P0) — processing failure handling, sanitized errors, never stuck mid-pipeline.
- `FR-PROC-005` (P1) — manual reprocessing (repository/service methods already existed from R2; this task wires the actual enqueue).
- `NFR-AVAIL-002` (P1) — retry up to 3 attempts w/ exponential backoff for transient failures only; permanent/content-inherent failures fail immediately, no retry.
- `NFR-SEC-003`/`NFR-SEC-004` (carried, not re-implemented) — MIME sniffing before parsing, non-guessable storage keys (already satisfied by R2; this task adds the worker-side deeper sniff document-processing.md §1 requires).
- `NFR-SEC-009` — sanitized `processing_error` strings only, never a stack trace/internal path.

## Dependencies
- R2 (Document Management) — `documents`/`document_chunks` schema, `DocumentService`, `StorageProvider` abstraction, SSE status stream (already polls `documents.status`, which this task's worker now actually drives).
- Phase 6 (`chunking.py`, `EmbeddingService`, `EmbeddingProvider`) — reused unmodified except for the CSV row-group addition to `chunking.py`.

## Files Affected
- `backend/app/document_processing/base.py` — new — `DocumentParser` ABC, `ParsedText`/`ParsedCsv` result types, typed `DocumentParseError` hierarchy (permanent vs. retryable).
- `backend/app/document_processing/pdf_parser.py` — new — `pypdf` + `pdfplumber`, page-by-page extraction, password/scanned-image/corrupt detection.
- `backend/app/document_processing/docx_parser.py` — new — `python-docx`, paragraph/heading/table extraction.
- `backend/app/document_processing/txt_parser.py` — new — UTF-8 decode + `charset-normalizer` fallback.
- `backend/app/document_processing/csv_parser.py` — new — `pandas` primary, stdlib `csv` fallback, malformed-CSV detection.
- `backend/app/document_processing/parser_registry.py` — new — MIME type → parser lookup.
- `backend/app/document_processing/chunking.py` — modified — adds `chunk_csv_rows()` (rag.md §2's row-group chunking; did not exist before this task).
- `backend/app/services/document_processing_service.py` — new — orchestrates extract → chunk → embed → status transitions; idempotent retry handling.
- `backend/app/core/queue.py` — new — RQ/Redis enqueue helper (ADR-008), fail-open on Redis unavailability (mirrors ADR-021's precedent, documented as ADR-023).
- `backend/app/workers/__init__.py`, `backend/app/workers/document_processing_worker.py` — new — RQ job entrypoint + `on_failure` callback that marks `failed` only once retries are exhausted.
- `backend/app/services/document_service.py` — modified — `confirm_upload`/`reprocess_document` now call `enqueue_document_processing` instead of leaving the documented gap; `reprocess_document` reuses the new `delete_for_document` repository method instead of a manual loop; `get_content`'s CSV branch fixed to deduplicate the now-repeated-per-chunk header row (see Implementation Notes — a genuine R2 compatibility fix, not new scope).
- `backend/app/repositories/document_repository.py` — modified — adds `DocumentChunkRepository.delete_for_document`.
- `backend/app/core/storage.py` — modified — `StorageProvider.read_object_bytes` promoted from a `LocalFilesystemStorageProvider`-only helper to a real abstract method (parsers need raw bytes; every future cloud provider needs this too, per `document-processing.md` §7).
- `backend/pyproject.toml` — modified — adds `rq`, `pypdf`, `pdfplumber`, `python-docx`, `pandas`, `charset-normalizer`.
- `docker-compose.yml` — modified — adds a `worker` service (RQ consumer, same backend image, different command) per the remediation plan's explicit instruction. Does **not** add a `fastapi-app` service — that gap predates this task (R1/R2 left it) and is out of R3's scope; flagged under Known Limitations.
- `specs/decisions.md` — modified — ADR-023 (RQ enqueue failure mode: fail open, logged warning, mirrors ADR-021).
- Tests — new: `test_pdf_parser.py`, `test_docx_parser.py`, `test_txt_parser.py`, `test_csv_parser.py`, `test_parser_registry.py`, `test_csv_chunking.py`, `test_document_processing_service.py`, `test_document_processing_worker.py`, `test_documents_processing_integration.py`. Modified: `test_chunking.py` (unaffected — additive only), `test_documents_api.py`/`test_documents_sse.py` (add processing-pipeline-driven cases where the existing tests only drove `documents.status` directly).

## Implementation Notes
- **Parser abstraction, not per-type branching in the service:** `DocumentProcessingService` never checks MIME type itself beyond `get_parser(document.mime_type)` — matches `document-processing.md` §8's extensibility contract exactly.
- **Sync parsing libraries run off the event loop:** `pypdf`/`pdfplumber`/`python-docx`/`pandas` are synchronous; `DocumentProcessingService` calls `parser.parse()` via `loop.run_in_executor(None, ...)` per `skills/backend.md` §13.
- **MIME sniff before parse:** each parser exposes `sniff_matches(header_bytes)`; the service checks it before invoking `parse()`, raising `UnsupportedContentError` on mismatch (`document-processing.md` §1) — this is the worker-side deep check; R2's confirm-time check was already a fast, shallow gate.
- **Permanent vs. retryable failures, exactly per §6's table:** `DocumentParseError` subclasses default `retryable=False` (corrupt file, password-protected, no text layer, bad encoding, malformed CSV — fail immediately, no retry, `documents.status=failed` with the exact sanitized message set in `document-processing.md` §3). A distinct `TransientParseError` (and any unexpected non-`DocumentParseError` exception) is `retryable`/propagates uncaught so RQ's own `Retry(max=3, interval=[10,30,60])` (configured at enqueue time, `core/queue.py`) re-invokes the job — `documents.status` is only set to `failed` once retries are exhausted, via the job's `on_failure` callback (`workers/document_processing_worker.py`), never mid-retry (avoids a confusing spurious `failed` SSE event immediately followed by another `extracting`).
- **Idempotency (NFR-AVAIL-002 + FR-PROC-005):** `DocumentProcessingService.process_document` clears any existing `document_chunks` rows for the document (via the new `delete_for_document`) immediately before writing the fresh set — this makes both a manual reprocess and an automatic mid-pipeline retry safe: no run ever appends to a previous run's partial output, and the `(document_id, chunk_index)` unique constraint is never at risk of a retry-triggered violation. A document already `ready` is treated as a no-op by a stray/duplicate job delivery.
- **CSV row-group chunking, not implemented before this task:** `chunk_csv_rows()` packs whole rows into ≤`TARGET_MAX_TOKENS`-token groups (reusing the existing token budget constant rather than inventing a new arbitrary row-count), with the header repeated in each group's stored `content` for context, per `rag.md` §2. `char_start`/`char_end` track offsets into the canonical (non-repeated-header) row-serialized text, kept meaningful rather than left arbitrary.
- **R2 compatibility fix — CSV content reconstruction:** `DocumentService.get_content`'s CSV branch (R2) naively joined every chunk's raw `content` and parsed the result as one CSV — correct only if chunks never repeat the header. Since `rag.md` §2 mandates the header be repeated per chunk (which R2 could not have implemented, as no chunker existed yet), that assumption is now false. Fixed to parse each chunk independently and take the header from the first, rows from every chunk — the "genuine compatibility fix" `CLAUDE.md`'s R1/R2 non-reimplementation rule anticipates, not a reimplementation of R2's own scope.
- **Enqueue failure mode (ADR-023):** `core/queue.py`'s `enqueue_document_processing` fails open (catches `redis.RedisError`, logs a warning, returns) rather than raising into `confirm_upload`/`reprocess_document` — mirrors ADR-021's rate-limiter precedent (`NFR-AVAIL-001`). A document left `queued` with no job enqueued is an operationally-visible gap (the logged warning), not a 500 to the uploading user.
- **Explicitly NOT in scope for this task:** OCR for scanned/image-only PDFs (`decisions.md` OQ-05, out of MVP scope by design — routed to the `NoTextLayerError` user-facing message instead); a `fastapi-app` Docker Compose service (pre-existing R1/R2 gap, not created here); any change to R4–R10 domains; any new Alembic migration (no schema change needed — `documents`/`document_chunks` columns already exist from Phase 3).

## Tests
- **Parser unit tests** (`testing.md` §3.1-shaped, no DB needed) — one golden-sample test per format (valid PDF/DOCX/TXT/CSV → expected text/rows), one corrupt-file test per format where applicable, PDF password-protected detection, PDF scanned/no-text-layer detection, TXT encoding-fallback detection, CSV malformed/inconsistent-column-count detection, MIME-sniff mismatch rejection.
- **`chunk_csv_rows` unit tests** — row-group token budgeting, header repeated per chunk, offset correctness, empty-rows-yields-zero-chunks.
- **`DocumentProcessingService` unit tests** (repositories/storage/embedding provider faked, per `skills/backend.md` §3.1) — full successful pipeline (extracting→chunking→embedding→ready status sequence asserted in order), a permanent parse failure (sanitized message, no retry signal, terminal `failed`), a transient failure (exception propagates, status never set to `failed` by the service itself), idempotent retry (chunks cleared before rewrite, no unique-constraint violation), degenerate/empty-extraction failure routes through `EmptyDocumentError` to `failed`.
- **Worker entrypoint tests** — `on_failure` callback marks `failed` with the generic transient message; a permanent-failure job does not trigger `on_failure` (service already self-terminated without raising).
- **API/integration tests** — `POST /documents/{id}/confirm` triggers a real enqueue (assert the RQ queue received a job, using a real Redis per this codebase's existing rate-limit-test convention); an end-to-end pipeline run against the local storage provider + fake embedding provider reaches `ready` with the expected chunk count for each of the four MIME types; `POST /documents/{id}/reprocess` clears prior chunks and re-enqueues.
- **Cross-tenant test** — `delete_for_document`/`process_document` never touch another user's chunks (mandatory category, `testing.md` §3.5).
- **Regression** — existing `test_documents_sse.py`/`test_documents_api.py`/`test_document_chunk_repository.py` continue passing unmodified in behavior (the SSE stream's contract is unchanged; it now observes a real worker's transitions instead of only test-driven ones).

## Acceptance Criteria
Copied from `specs/requirements.md` §1.4:
- `FR-PROC-001`: Given a valid PDF/DOCX/TXT/CSV, when processed, then extracted text is stored and page numbers (PDF) or row structure (CSV) are preserved as chunk metadata.
- `FR-PROC-002`: Given extracted text, when chunked, then each chunk is within the configured token range and carries `document_id`, `chunk_index`, `page_number` (if applicable), and character offsets.
- `FR-PROC-003`: Given N chunks for a document, when embedding completes, then N rows exist with non-null embeddings of the configured dimension, and `documents.status` transitions to `ready`.
- `FR-PROC-004`: Given a corrupt/password-protected PDF, when processing fails, then `documents.status=failed` and `documents.processing_error` contains a user-safe message (no stack traces/internals).
- `FR-PROC-005`: A user can retry processing for a `failed` document.

## Definition of Done
- [ ] Code implements the Objective and satisfies all Acceptance Criteria
- [ ] Tests listed above are written and passing
- [ ] No requirement silently changed or reinterpreted
- [ ] `specs/decisions.md` updated (ADR-023)
- [ ] Full backend test suite, ruff, black, mypy all green (see Final Report)
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

## Known Limitations (recorded, not silently dropped)
- OCR for scanned/image-only PDFs remains out of scope (`decisions.md` OQ-05).
- No `fastapi-app` Docker Compose service exists yet (pre-existing gap from R1/R2, not introduced or closed by this task).
- CSV row-group size is token-budgeted against the existing `TARGET_MAX_TOKENS` constant; `rag.md` does not specify an exact row-count-per-chunk, so this is a documented, reasonable interpretation, not a spec-mandated number.
- The RQ worker process is not started automatically by any test — worker-side behavior (`document_processing_worker.py`) is tested by invoking its functions directly, not by running a live `rq worker` process against the test Redis instance (no test in this codebase spins up a subprocess).

### Findings from a subsequent independent audit (2026-08-26) — not fixed, recorded here per this task's own "known limitations" discipline

An independent, read-only audit was performed after this task's initial implementation (before R4 started). It found the implementation functionally correct for every tested path, but surfaced gaps neither this task nor any other remediation task explicitly owns. None of these have been fixed as part of this documentation update (see the audit's own "no fixes" scope) — recorded here so they are not silently lost:

1. **No worker-crash recovery path (HIGH).** If the worker process dies mid-job (OOM kill, deploy, host restart — a normal operational event, not a rare edge case), the document is left stuck at a non-terminal `status` forever: RQ's own retry only engages for a Python exception the job raises, never for the process being killed out from under it; `docker-compose.yml`'s `worker` service has no `restart:` policy; and `reprocess_document`'s own guard (`status != "failed"` → `409`) means the one user-facing recovery endpoint this task built is inaccessible for exactly the case that needs it. The SSE stream (`GET .../status/stream`, unmodified R2 code) also has a 10-minute iteration cap that, in this scenario, closes with no terminal event — a literal gap against `api.md`'s "ending with a terminal ready/failed event." This was empirically reproduced during the audit (a real worker crash left a job orphaned in Redis with no `documents.status` update). **Decision needed:** whether a stale-job sweep / dead-letter reconciliation belongs to a future task, or is accepted as a documented production gate item.
2. **`NFR-OBS-001` (P0): embedding calls never write an `ai_requests` row (HIGH).** `database.md` §3.13 and `observability.md` §4 both name `'embedding'` as a valid `ai_requests.operation` value ("every call to an LLM **or embedding provider** is logged"), but `DocumentProcessingService`'s `embed_batch()` call writes nothing. Confirmed by grep: zero references to `ai_requests`/`AiRequestRepository` anywhere in the document-processing code. **This requirement is not assigned to any remediation task** — `tasks/remediation-plan.md` only calls out `ai_requests` logging for R4–R7 (chat/extraction/comparison/summarization), never R3, even though R3 is the only task that invokes an embedding provider. **Decision needed:** assign ownership (most naturally R3, as a follow-up) before any "all P0 requirements verified" claim.
3. **`confirm_upload` has no idempotency guard (MEDIUM, pre-existing from R2, worsened by R3).** Calling `POST /documents/{id}/confirm` twice on the same document double-counts `user.storage_used_bytes` and (since this task added the enqueue call) now also double-enqueues a processing job. Empirically reproduced live. The duplicate-job consequence is self-healing in the realistic sequential case (`process_document`'s "already `ready`" guard makes the second job a no-op — confirmed live, no duplicate chunks resulted); the storage-accounting bug is not self-healing.
4. **Retry count is one more than a literal reading of "max 3 attempts" (MEDIUM).** `core/queue.py`'s `Retry(max=3, ...)` means 3 *retries* (RQ's own documented semantics) = 4 *total* attempts, whereas `NFR-AVAIL-002`/`architecture.md` say "max 3 attempts" — plausibly meaning 3 total. No ADR resolves the ambiguity, and no test asserts the actual retry/backoff configuration reaches `queue.enqueue()` (a regression here would go uncaught).
5. **CSV "beyond a tolerance" wording implemented as zero tolerance (LOW).** `document-processing.md` §3.4 implies some slack for inconsistent column counts; the implementation rejects any mismatch. Defensible (no specific tolerance is defined anywhere), but stricter than the text implies.

#### Remediation ownership decisions (2026-08-26 planning pass — ADR/spec/roadmap left unmodified per instructions)

Full matrix, priority classification, and production-gate impact are recorded in this session's remediation-planning report (not duplicated here in full). Ownership conclusions, for traceability:

- **#1 (worker crash recovery)** — **split.** A minimal R3 follow-up (loosen `reprocess`'s `status != "failed"` guard, or add an equivalent stale-document reset path, so `FR-PROC-004`'s "not left processing forever" holds even after a worker crash) is R3's own gap to close. The broader "detect and alert on a stuck job automatically" capability is `observability.md` §6's own explicitly-named "operational alerting candidate," which maps to **R12** (production readiness) infrastructure, not R3 code. Neither R3 nor R12 nor R10 (`FR-ADMIN-002`, queue-depth *visibility* only) currently owns this pairing explicitly in `tasks/remediation-plan.md` — flagged as a plan gap, same shape as the Summarization omission the plan's own validation pass previously caught.
- **#2 (embedding `ai_requests` observability)** — **R3**, as a dedicated follow-up. `tasks/remediation-plan.md` assigns `ai_requests` logging to R4–R7 by name and never to R3, even though R3 is the only task calling an embedding provider — confirmed also missing from R12 §15.1's own P0 gate line ("every AI-invoking domain (R4/R5/R6/R7)... `NFR-OBS-001`"), which omits R3 there too.
- **#3 (`confirm_upload` idempotency)** — **R2** (the method and the bug both predate R3; R3 only added the enqueue call that makes the duplicate-job consequence real). Coordinate with R3 since the fix's blast radius touches the enqueue call R3 added.
- **#4 (retry-count ambiguity)** — not a code-ownership question; a **product/spec decision** (what "max 3 attempts" means) is needed first, then a trivial R3 code change (`Retry(max=2)` vs. keeping `max=3` with a documented ADR) follows from whichever reading is chosen.
- **#5 (CSV tolerance)** — **R3**, low priority; same shape as #4 (needs a defined tolerance number before a code change is meaningful).

None of these block the core pipeline's correctness for the tested paths (re-confirmed by this update's fresh full-suite + live run, below) — they are availability/observability/idempotency gaps, not data-corruption or cross-tenant risks.

## Verification Results

- **Full backend test suite:** 292 passed, 0 failed (`pytest -q`).
- **Ruff:** clean.
- **Black:** clean.
- **Mypy (`mypy app`):** clean, 68 source files.
- **Alembic migration check:** `alembic upgrade head` applies cleanly against a fresh ephemeral Postgres; no new migration added (none needed — schema unchanged).
- **Live smoke test:** real Postgres + Redis (Docker), real FastAPI process (uvicorn), and a real `rq worker` process (RQ's `SimpleWorker` — see note below) driving the actual queue. Register → login → presign → PUT → confirm → poll `/status` → `ready`, for a real multi-job worker lifetime (a success job followed by a deliberately-corrupt-PDF failure job on the *same* long-lived worker process). Both passed.
  - **Real defect found and fixed by this smoke test, not by pytest:** `workers/document_processing_worker.py`'s `asyncio.run()`-per-job pattern left the shared `engine`'s connection pool holding a connection bound to the previous job's already-closed event loop, breaking every job after the first in a worker's lifetime (observed live: "attached to a different loop"). Fixed by disposing the pool at the end of each entrypoint's own event loop, before it closes. See the module's updated docstring. Confirmed fixed by re-running the two-job live sequence after the fix.
  - **Windows-only note, not a defect:** RQ's default (forking) `Worker` class calls `os.fork()`, unavailable on native Windows — this only affected the ad hoc local smoke test; the real deployment target (`docker-compose.yml`'s `worker` service, a Linux container per `Dockerfile`) has `os.fork()` and is unaffected. `SimpleWorker` was used for the local smoke test only.
- **Security/multi-tenancy:** every repository method takes `user_id` first and filters on it (`DocumentChunkRepository.delete_for_document`, `DocumentProcessingService.process_document`'s `document_repo.get(user_id, ...)` gate); dedicated cross-tenant test (`test_process_document_never_touches_another_users_document`) confirms a wrong-`user_id` call is a silent no-op, never touching another user's document/chunks.
- **SSE verification:** `GET /documents/{id}/status/stream` (R2, unmodified) now observes real worker-driven transitions — confirmed via the existing `test_documents_sse.py` suite continuing to pass unmodified, plus the live smoke test's polling confirming real `queued`→`ready`/`failed` transitions land in the same `documents.status` column that stream already reads.

Full pass/fail detail and the complete file/architecture summary: see the Final Report delivered at the end of this implementation session.

### Re-verification (2026-08-26, post-R4)

Re-run in full after R4 (Chat) landed on top of R3/R2/R1, to confirm R3 still holds under the current `main` HEAD (`3367dd7`), per a request to audit/verify rather than re-implement:

- **Full backend suite:** 329 passed, 0 failed (292 pre-R4 + 37 R4 tests) — R3's own 63 tests (parsers, registry, chunking, service, worker, integration) re-run in isolation: 63 passed. R1/R2 regression suite (161 tests) re-run in isolation: 161 passed.
- **Ruff / Black / Mypy:** all clean, no findings (mypy: 72 source files, 0 issues — there are no pre-existing mypy failures to distinguish from R3-introduced ones; the suite is clean at every commit checked).
- **Migrations:** full chain validated both incrementally (`downgrade -1`/`upgrade head` at `0003`) and completely (`downgrade base` → `upgrade head` through `0001`→`0002`→`0003`), clean both ways.
- **Live end-to-end sanity check** (real Postgres + Redis + a real `rq worker` process, not a mock): register → upload → confirm → worker picks up the job → `ready`, exercised for TXT (success) and CSV (success, correct row/column reconstruction) formats; a deliberately corrupt PDF correctly reached `failed` with the exact sanitized message; `POST /documents/{id}/reprocess` correctly re-queued and (since the underlying bytes were still corrupt) correctly failed again, consistently. All 4 jobs completed cleanly on one long-lived worker process (no crash, matching the earlier-fixed engine-disposal behavior holding up under repeated use).
- **Scope check:** `git status` clean before and after this audit; no source files modified by this pass — only this task file was updated, per the requested "audit/verify, no new parallel implementation" scope.

The findings under "Findings from a subsequent independent audit" above were already known from a prior audit pass in this same effort and are restated here for a single source of truth; this re-verification did not surface any *new* defects.

## Remediation implementation (2026-08-26) — findings #1 and #2 closed

Both HIGH/P0 findings from the audit above (#1 worker crash recovery, #2 embedding `ai_requests` observability) are now implemented, on top of the existing `c7a391d` (R3) / `3367dd7` (R4) commits, per the ownership decisions already recorded above. Findings #3, #4, #5 remain open — explicitly out of scope for this pass (see "Remaining open findings" below).

### Remediation 1 — worker crash recovery (`FR-PROC-005`, `decisions.md` ADR-026)

- **Decision (via explicit user sign-off, not silently chosen):** extend `reprocess`'s existing contract rather than build new stale-job-detection infrastructure. `api.md`'s reprocess entry and `document-processing.md` §6 are both updated to say a document stuck in a non-terminal stage (`queued`/`extracting`/`chunking`/`embedding`) longer than a new, documented threshold is reprocessable, exactly like a `failed` one.
- **Threshold:** `settings.document_processing_stale_threshold_seconds = 900` (15 min), added to `backend/app/core/config.py`. No prior spec defined any threshold; 900s is derived from `performance.md`'s `NFR-PERF-004` (60s p95 for a typical 20-page document) with a 15x margin — full reasoning in `specs/decisions.md` ADR-026, including the accepted residual risk (a purely time-based heuristic can't perfectly distinguish "crashed" from "still legitimately running").
- **Implementation:** `DocumentService.reprocess_document` (`backend/app/services/document_service.py`) gained a `_is_stale_non_terminal()` check using the document's existing `updated_at` (already bumped by every real stage transition via `UpdatedAtMixin` + `DocumentRepository.set_status` — no new column or migration needed). The guard changed from `if document.status != "failed": raise InvalidStatusError()` to also permit a stale non-terminal document. Everything else about `reprocess_document` (chunk deletion, `enqueue_document_processing`, tenant scoping via `document_repo.get(user_id, ...)`) is unchanged.
- **What was deliberately not built:** R12's broader stale-job detection/alerting/health-check/auto-restart infrastructure (`observability.md` §6's "operational alerting candidate") — out of scope per the user's explicit instruction; recorded as a residual gap in ADR-026's Consequences, not silently solved here.

### Remediation 2 — embedding `ai_requests` observability (`NFR-OBS-001`)

- **Implementation:** `DocumentProcessingService` (`backend/app/services/document_processing_service.py`) now takes a 5th constructor argument, `ai_request_repo: AiRequestRepository` (reused unmodified from `app/repositories/observability_repository.py` — the same repository `chat_service.py` already uses for LLM calls, no parallel implementation). The embedding call site is wrapped by `_embed_with_observability`, which times the call, logs one row via `_log_ai_request` in a `finally` block (success and failure both write exactly one row), and re-raises unchanged so the embedding call's own success/failure outcome is never altered by the observability write. `EmbeddingProvider` (both `FakeEmbeddingProvider` and `OpenAIEmbeddingProvider`, `app/ai/embeddings.py`) gained a `provider_name` class attribute mirroring `LLMProvider.provider_name` exactly, so the logged `provider` field has a real value instead of a hardcoded string.
- **Logged fields:** `operation="embedding"`, `provider`/`model` from the provider, `input_tokens` = the real sum of each chunk's already-computed `token_count` (not an estimate), `output_tokens=None` (embeddings have no generated tokens — the column is nullable exactly for this), `latency_ms`, `status` (`success`/`error`), `error_code` (`"embedding_failed"` on failure, `None` on success). No API keys, raw content, or prompts are ever logged — only metadata, per `observability.md`'s Never-Log List.
- **Failure isolation:** `_log_ai_request` catches its own exceptions and only logs a warning (`# noqa: BLE001`, matching the existing justified pattern elsewhere in this codebase) — a failure writing the observability row can never turn a successful embedding call into a failed one, or vice versa. Verified by a dedicated test (`test_ai_request_logging_failure_does_not_affect_document_processing_outcome`).
- **`document_processing_worker.py`** updated to construct the new `AiRequestRepository(session)` dependency alongside the service's existing repositories.

### Tests added

- `backend/tests/test_document_processing_service.py` (unit, fakes only — the 8 pre-existing tests updated for the new constructor arg, unmodified in behavior): 3 new tests — successful embedding call writes exactly one row with correct fields; a failing embedding call writes exactly one row with `status="error"`/`error_code="embedding_failed"` before the exception still propagates; an observability-logging failure does not affect the document's own successful outcome.
- `backend/tests/test_documents_processing_integration.py` (real Postgres/Redis/API, the 3 pre-existing constructions updated for the new constructor arg, unmodified in behavior): 6 new tests — a stale non-terminal document is recoverable via `reprocess` (202, requeued, error cleared); a genuinely active (fresh, non-stale) non-terminal document is correctly rejected (409, untouched, no duplicate enqueue); a recovered stale document, once actually processed, reaches `ready` end-to-end; a stale document cannot be recovered by a different user (404, untouched); a real embedding call writes exactly one `ai_requests` row queryable straight from the table, with the correct `user_id`/`operation`/`provider`/`status`.

### Verification results (this remediation pass)

- **Targeted tests:** `test_document_processing_service.py` — 11 passed. `test_documents_processing_integration.py` — 12 passed. `test_document_processing_worker.py` + `test_documents_api.py` (existing reprocess tests, unmodified) — 46 passed, confirming the extended guard did not change behavior for the pre-existing `failed`/`queued`-fresh cases.
- **Full backend suite:** 337 passed, 0 failed.
- **Ruff:** clean (one self-introduced `RET501`/`PLR1711` finding in a new test fixture was fixed immediately — an unnecessary explicit `return None`, not a design issue).
- **Black:** clean, all files unchanged by `--check`.
- **Mypy:** 5 pre-existing errors, all in files this remediation never touched (`test_require_admin.py`, `test_csrf.py`, `test_users_api.py`, `test_chat_sse.py`, `test_auth_api.py` — all pre-dating this session, confirmed by re-running mypy against the untouched `3367dd7` (R4) HEAD via a temporary `git stash`, which reproduced the identical 5 errors before this remediation's changes were reapplied). **Zero new mypy errors introduced by this remediation.**
- **Migrations:** none added or needed — `document.updated_at` already existed (`UpdatedAtMixin`) and was already being bumped by every stage transition; no schema change required.
- **Live smoke test** (real Postgres + Redis, the real FastAPI app via ASGI transport, and a real RQ `SimpleWorker` burst process — not a mock): (1) a normal upload processed by a real worker burst reached `ready` and logged exactly one `ai_requests` row (`operation=embedding`, `provider=fake`, `status=success`, real `input_tokens`); (2) a second document was backdated to a stale `embedding` state (simulating a crashed worker), successfully recovered via the real `reprocess` endpoint, reprocessed by a real worker burst, and reached `ready`, with exactly one additional `ai_requests` row (two total, no duplicates); (3) a second user's attempt to recover the first user's stale document correctly returned `404` (not `403`, per `NFR-SEC-001`), with no job enqueued and the document left untouched; (4) a `ready` document was correctly rejected (`409`) when reprocess was attempted again. One incidental artifact of the smoke test's own sequencing (the original confirm-time job was still queued when the document was manually backdated, so the worker burst drained both it and the reprocess-triggered job) safely demonstrated the pre-existing "already `ready` is a no-op" idempotency guard: the second, redundant job returned instantly and did not write a second `ai_requests` row — reinforcing, not undermining, the "no uncontrolled duplicate enqueue" requirement.
- **Tenant isolation:** verified both by the new automated tests and the live smoke test above — cross-tenant recovery attempts return `404`, never touch the other user's document, and never enqueue a job.
- **Scope check:** `git status` shows exactly the 11 files listed at the top of this section as modified (5 backend source files, 2 test files, 3 spec files, this task file) — no R4/R5/R2/R12/unrelated files touched, no R5 work started, no commit made, no deployment/docker-compose change made, no new dependency added.

### Remaining open findings (unchanged ownership, still open)

- **#3 `confirm_upload` idempotency (MEDIUM)** — **closed**, see "Remediation implementation (final delivery-readiness pass) — finding #3 closed" below.
- **#4 retry-count ambiguity, "max 3 attempts" vs. RQ's 3-retries-=-4-attempts semantics (MEDIUM)** — needs a product/spec decision before a code change is meaningful. Not addressed this pass.
- **#5 CSV tolerance wording (LOW)** — needs a defined tolerance number before a code change is meaningful. Not addressed this pass.

## Remediation implementation (final delivery-readiness pass) — finding #3 closed

Closes the one remaining MEDIUM finding from the 2026-08-26 audit above (`confirm_upload` has no idempotency guard), per the ownership decision already recorded there ("R2, coordinate with R3"). Triggered by `tasks/final-release-audit.md`'s finding #1.

- **Exact failure mode confirmed by reading the code directly (not re-derived from the audit's description alone):** `DocumentService.confirm_upload` (`backend/app/services/document_service.py`) unconditionally re-read storage metadata, recomputed the checksum, and unconditionally did `user.storage_used_bytes + actual_size` on every call — a second confirm of the same document double-counted the user's own quota usage. The re-enqueue side was already self-healing (`process_document`'s "already `ready`" no-op guard, confirmed live during the original R3 pass) — only the storage-accounting side was a real, non-self-healing bug.
- **No migration needed, and none was invented.** `presign_upload` already writes `checksum_sha256=""` as a real sentinel value at document-creation time (a genuine sha256 hex digest is always 64 characters, never empty) — this existing column already distinguishes "not yet confirmed" from "confirmed" with no schema change.
- **Fix — an atomic, guarded UPDATE, not a plain read-then-write check.** `DocumentRepository.confirm_if_unconfirmed` (new) performs `UPDATE documents SET checksum_sha256=..., size_bytes=... WHERE id=... AND user_id=... AND checksum_sha256=''`, using `.returning(Document)` to report whether it actually matched a row. `confirm_upload` now: (1) fast-path-returns the existing document if a first read already shows it confirmed (the common sequential-retry case, no storage I/O); (2) otherwise verifies/checksums as before, then calls the atomic guard; (3) only increments `storage_used_bytes`/enqueues processing if the guard's own UPDATE actually won (`confirmed is not None`); (4) if it lost the race (a genuinely concurrent duplicate request), re-fetches and returns the winner's already-confirmed document instead. Postgres serializes two concurrent UPDATEs against the same row itself — the second transaction's WHERE clause re-evaluates against the now-already-confirmed row and matches zero rows — so this is safe under real concurrent duplicate requests, not just sequential ones, with no explicit locking (`SELECT FOR UPDATE`) needed.
- **Behavior on a repeat confirm:** idempotent success (the same `202 {id, status}` shape a first-time confirm returns), not a new error code — `api.md` documents no existing error for this case, and inventing one was judged a larger surface change than the smallest-safe-fix instruction called for; a retry silently succeeding without side effects is standard idempotent-POST behavior.
- **Multi-tenant safety:** unaffected by construction — both `document_repo.get(user_id, ...)` (the fast-path read) and `confirm_if_unconfirmed`'s own `WHERE ... AND user_id = ...` clause are tenant-scoped exactly like every other repository method in this codebase; a repeat confirm can only ever touch the confirming user's own row.
- **Tests added:** `backend/tests/test_documents_api.py` — `test_repeated_confirm_does_not_double_count_storage_usage` (sequential duplicate via the real HTTP/CSRF stack, the realistic client-retry case) and `test_repeated_confirm_does_not_reach_another_tenants_quota` (a second user's `storage_used_bytes` is untouched by the first user's repeat confirm). `backend/tests/test_confirm_upload_concurrency.py` (new file) — `test_confirm_if_unconfirmed_is_safe_under_real_concurrent_duplicates`, which deliberately bypasses the shared `client`/`db_session` fixtures (they bind every session in a test to one already-open connection/transaction, so two "sessions" built from them can never actually race against each other) in favor of two real, independently-committing sessions racing via `asyncio.gather` — proving the atomic guard holds under genuine concurrent duplicate requests, not just asserting it does.
- **Verification:** targeted tests (`test_documents_api.py`, `test_confirm_upload_concurrency.py`, `test_document_repository_r2.py`, `test_documents_processing_integration.py`) — 69 passed. Full backend suite — 520 passed (517 + 3 new), run twice, deterministic both times. Ruff/Black/Mypy — all clean (102 source files, mypy). No new dependency, no schema change, no migration.
- **Scope check:** `git status` at the time of this fix showed exactly `document_repository.py`, `document_service.py`, `test_documents_api.py` (2 new tests), `test_confirm_upload_concurrency.py` (new file), and this task file changed — no R1/R4–R12/unrelated file touched, no new R13 task created, no commit made.

### R3 gate recommendation

With both HIGH/P0 findings now closed (worker crash recovery and `NFR-OBS-001` embedding observability), and the three remaining findings all MEDIUM/LOW, non-security, non-corruption gaps with an already-recorded ownership decision, **R3 can now be considered PASS** for its own P0/P1 requirement set. The remaining #3/#4/#5 items are legitimate follow-up work (tracked above) but do not, on their own, block R3's gate — they are the kind of documented, bounded gap `CLAUDE.md`'s own Known-Limitations discipline anticipates recording rather than silently deferring.
