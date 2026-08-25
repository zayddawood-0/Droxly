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
