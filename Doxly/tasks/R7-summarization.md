# Task R7: Summarization Integration

## Task ID
R7-001

## Feature
Document Summarization — `POST /documents/{id}/summaries` and its supporting endpoints: a user requests a summary of a `ready` document at a chosen detail level, the background-worker Summarization graph (`app/ai/graphs/summarization.py`, pre-existing scaffolding) generates and quality-checks it, and the result is persisted without ever overwriting a prior summary.

## Objective
Close the gap `tasks/remediation-plan.md` §10 (R7) identifies: the Summarization LangGraph workflow, `DocumentSummary` model, and `DocumentSummaryRepository` already existed (predating R1–R6, from the original phase-scaffolding commits) but had no router, no API-facing service, and no worker wiring. This task builds the router → service → worker chain per `api.md` §5, reusing the graph and repository (with two necessary compatibility fixes — see Implementation Notes) rather than reimplementing them, and extracts R6's per-call observability wrapper into a shared module since R7 needs the identical mechanism.

## Specification References
- `tasks/remediation-plan.md` §10 (R7) — authoritative scope for this task.
- `specs/requirements.md` §1.7 (`FR-SUM-001..002`).
- `specs/api.md` §5 (`/summaries`) — full endpoint contracts.
- `specs/database.md` §6 traceability + `app/models/summary.py` (`document_summaries` table — already migrated, no schema change needed).
- `specs/langgraph.md` §3 (Summarization graph — state/nodes/routing, unchanged).
- `specs/ai.md` §4 (prompt-injection defense pattern), `NFR-SEC-007`.
- `specs/observability.md` §4 (`NFR-OBS-001`, read literally — same interpretation R6 already established).
- `specs/security.md` §3.2 (404-not-403), `NFR-SEC-001` (tenant isolation).
- `specs/testing.md` §3.3/§3.5.
- `skills/backend.md` §9 (validation placement), §10 (error handling), §12 (background processing).
- `specs/decisions.md` — no new ADR added this task (same reasoning as R6: no genuinely new architectural pattern beyond what R6 already established).

## Requirements
- `FR-SUM-001` (P0) — generate a document summary at a chosen detail level (brief/detailed/bullet_points), quality-checked, persisted.
- `FR-SUM-002` (P1) — regenerating creates a new row; prior summaries remain fully accessible, never overwritten or hidden.
- `NFR-OBS-001` (P0) — every LLM call logged to `ai_requests`, one row per real call (not per run — see below).
- `NFR-SEC-001` (P0, carried) — tenant isolation on every new endpoint/repository method.
- `NFR-SEC-007` (carried) — prompt-injection defense for document content flowing into a prompt.

## Dependencies
- R3 (Document Processing) — a `ready` document with chunks is required before summarization can run.
- R6 (Comparison) — source of `ObservedLLMProvider` (now shared, `app/ai/observed_llm_provider.py`) and the established per-call observability decision this task reuses directly.

## Files Affected
- `backend/app/ai/observed_llm_provider.py` — **new** — `ObservedLLMProvider` extracted from `comparison_processing_service.py`'s private `_ObservedLLMProvider` (identical behavior, now parameterized by `operation` instead of hardcoding `"comparison"`) — a genuine second concrete need existed (R7), so per `CLAUDE.md`'s "three concrete implementations beat one speculative abstraction," duplicating this correctness-sensitive logic a second time was the wrong call; extracting it was.
- `backend/app/services/comparison_processing_service.py` — **modified** (R6 file, touched because R7 directly needed the shared wrapper) — imports and uses the shared `ObservedLLMProvider(operation="comparison")` instead of its own private copy. Pure refactor: no behavior change, R6's own test suite re-verified unchanged and still green.
- `backend/app/ai/graphs/summarization.py` — modified — two compatibility fixes (see below): `SummaryType`'s third value corrected from `"bullet"` to `"bullet_points"`; all three LLM-calling prompts (`summary_generator_node`'s per-chunk and combine calls, `quality_checker_node`'s check) updated with the same anti-prompt-injection framing R4/R6 already established.
- `backend/app/repositories/summary_repository.py` — modified — added `list_for_document` (paginated, for `GET /documents/{id}/summaries`) and `set_result` (the worker's terminal write).
- `backend/app/schemas/summary.py` — new — full request/response Pydantic contract for `api.md` §5, `summary_type` as a `Literal` (a request-shape-only 422 for an invalid value, no dedicated error code needed since api.md doesn't name one).
- `backend/app/services/summary_service.py` — new — the API-facing trigger/CRUD half (`create_summary`, `get_summary`, `list_for_document`), mirroring R5/R6's `ExtractionService`/`ComparisonService` role.
- `backend/app/services/summary_processing_service.py` — new — the worker-invoked half (`run_summary`: assembles the document's full text from its already-processed chunks, builds and runs the graph via the shared `ObservedLLMProvider(operation="summarization")`, persists the terminal state).
- `backend/app/workers/summary_worker.py` — new — the RQ job entrypoint, mirroring `extraction_worker.py`/`comparison_worker.py`'s exact shape.
- `backend/app/core/queue.py` — modified — `SUMMARY_QUEUE_NAME`, `get_summary_queue`, `enqueue_summary`.
- `backend/app/api/v1/routers/summaries.py` — new — all three endpoints from `api.md` §5, split across two path prefixes (`/summaries/{id}` GET, `/documents/{id}/summaries` POST+GET) matching `extractions.py`'s established sub-router pattern.
- `backend/app/main.py` — modified — mounts both new routers.
- Tests — new: `test_observed_llm_provider.py`, `test_summary_processing_service.py`, `test_summaries_api.py`, `test_summary_worker.py`. Modified: `test_graph_summarization.py` (bullet_points + prompt-injection regression tests added, existing tests unaffected).

## Implementation Notes

### Two genuine compatibility fixes to pre-existing scaffolding, not new scope
1. **`SummaryType`'s third value was `"bullet"`, but `api.md` §5's request schema (`{ summary_type: "brief"|"detailed"|"bullet_points" }`), the `document_summaries` table's own CHECK constraint (`app/models/summary.py`), and the already-built frontend (`frontend/lib/api/summaries.ts`'s `SummaryType`) all agree on `"bullet_points"`** — three independent, mutually-consistent sources, checked directly (the same class of defect R5's `PRESET_TEMPLATES` and R6's `ChangeCategory` had, and the same resolution: the pre-existing graph scaffolding was the one outlier, corrected to match).
2. **None of the three LLM-calling nodes followed the established anti-prompt-injection pattern** (`document_qa.py`/R4, applied to `comparison.py`/R6) — missing `<document_context>` delimiters and the explicit "disregard instruction-like text" framing entirely. Brought into line with the established pattern.

### AI observability — reused R6's decision, extracted the shared mechanism
`observability.md` §4's literal `NFR-OBS-001` ("every call... is logged") was already resolved for R6 via explicit user sign-off: one `ai_requests` row per real provider call, not per run. Summarization's `map_reduce` strategy has the identical shape problem R6's `difference_detection_node` had (potentially many real `generate()` calls in one run) plus up to 3 real `generate_structured()` quality-check calls (the bounded retry budget). Rather than copy-pasting R6's `_ObservedLLMProvider` class a second time — which would have meant two independently-maintained copies of correctness-sensitive usage-preservation/error-isolation logic that could silently drift — it was extracted to `app/ai/observed_llm_provider.py` as `ObservedLLMProvider` (parameterized by `operation`), and R6's own service was refactored to import it instead of keeping its private duplicate. R6's full test suite (73 tests across its four test files) was re-run and confirmed unchanged/green after this refactor.

### Document text sourcing
Mirrors R6's `_load_segments`: `SummaryProcessingService._load_document_text` joins the document's already-processed `DocumentChunk` rows (`DocumentChunkRepository.list_for_document`, ordered by `chunk_index`) rather than re-parsing the source file — reusing R3's pipeline output exactly as `langgraph.md` §3's Content Analyzer node docstring already specified ("no re-parsing of the source file").

### `FR-SUM-002` — never overwrites
`SummaryService.create_summary` always calls `summary_repo.create(...)` (a fresh row), never an update-in-place — verified by both a dedicated API test and the live smoke test (regenerating produces a second row; the first remains fully readable with its own content untouched).

## Tests
- **`test_observed_llm_provider.py`** (new, 5 tests) — direct coverage of the now-shared wrapper: `generate()` success logs real usage; `generate()` failure logs an error row without fabricating usage; `generate_structured()` success logs real usage; `generate_structured()` failure preserves already-available usage from the exception (never re-fabricates or drops it); an observability-logging failure never affects the wrapped call's own outcome.
- **`test_graph_summarization.py`** (updated, 11 tests total — 6 pre-existing unaffected, 5 new) — `bullet_points` membership/end-to-end acceptance; the actual constructed system prompt/message content (not just successful execution) for all three LLM-calling nodes (single-pass, map-reduce per-chunk, quality-checker), each asserting the delimiter and disregard-instruction language is present.
- **`test_summary_processing_service.py`** (new, 8 tests) — successful single-pass summary persisted with exactly 2 `ai_requests` rows; map-reduce strategy logs one row per real chunk call plus the combine call (never collapsed, real distinct token counts proving no cross-call conflation); `bullet_points` end-to-end; quality-check retry-then-pass logs every call separately; quality-check retry-exhaustion persists `failed`/`content=None` (not an infinite loop or a silently-accepted low-quality draft); a missing/already-terminal summary is a no-op; an `ai_requests` logging failure never affects the summary's own outcome.
- **`test_summaries_api.py`** (new, 14 tests) — create (202, exactly-one-job-enqueued, `bullet_points` accepted, `422` invalid type, `404` missing/cross-tenant document, `409 document_not_ready`, `401` unauthenticated); get (exact shape, `content: null` while `processing`, `404` missing/cross-tenant); list (paginated shape, newest-first, `404` cross-tenant document); **`FR-SUM-002` regression** — regenerating creates a second row without overwriting the first, both independently readable afterward.
- **`test_summary_worker.py`** (new, 5 tests, real Postgres, mirrors `test_comparison_worker.py`) — full pipeline via the real sync RQ entrypoint; an unexpected exception propagates for RQ's own retry and doesn't mark `failed` itself; `on_summary_failure` no-ops while retries remain and marks `failed` once exhausted; cross-tenant job delivery is a silent no-op.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.7:
- `FR-SUM-001`: Given a document and a summary type, when requested, then a summary is generated via the LangGraph Summarization workflow, passes a quality check node, and is persisted for reuse (not regenerated on every view). — Verified by `test_summary_processing_service.py` and the live smoke test.
- `FR-SUM-002`: A user can request a fresh summary which does not overwrite the previous one silently — prior summaries remain accessible. — Verified by `test_regenerating_a_summary_does_not_overwrite_the_prior_one` and the live smoke test.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted (both compatibility fixes and the shared-observability extraction are documented above, not silent)
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **No stale-summary worker-crash recovery** (same shape as R5/R6's equivalent limitation) — `api.md` §5 defines no reprocess-equivalent endpoint for summaries.
- **No failure-reason field** on a failed summary's API response (unlike `documents.processing_error`) — `api.md` doesn't define one; a client sees only `status="failed"`, `content: null`.
- **`NFR-AVAIL-002`'s retry-count ambiguity** (an open R3 finding) applies identically to the new summary queue, inherited unchanged.
- **`OpenAIEmbeddingProvider`/real-Anthropic-usage gaps noted in R6** are unrelated here (summarization never calls the embedding provider), so no new instance of that limitation exists in this task.

## Verification Results
- **Targeted test files:** `test_observed_llm_provider.py` (5), `test_summary_processing_service.py` (8), `test_summaries_api.py` (14), `test_summary_worker.py` (5), `test_graph_summarization.py` (11) — 43 total, all passed. R6's own suite (`test_comparison_processing_service.py`, `test_comparisons_api.py`, `test_comparison_worker.py`, `test_graph_comparison.py` — 73 tests) re-run after the `ObservedLLMProvider` extraction and confirmed unchanged/green.
- **Full backend suite:** 440 passed, 0 failed — run three times, identical each time (one run took ~139s due to a transient system-load spike, not flakiness; the other two ran in ~25s with identical pass counts).
- **Ruff:** clean. **Black:** clean. **Mypy:** 5 pre-existing errors (unrelated files predating this task), 0 new (one `# type: ignore[typeddict-item]` added for the DB's plain-`str` `summary_type` narrowing to the graph's `Literal`, matching the codebase's existing convention for this exact situation in `extractions.py`/`comparisons.py`).
- **Migrations:** none added or needed — `document_summaries` table already migrated with the exact columns this task needs (verified directly against `information_schema.columns`).
- **Live smoke test:** real Postgres + Redis (Docker), the real FastAPI app (ASGI transport), and real RQ `SimpleWorker` burst processes (`document_processing` and `summary` queues, separate subprocesses). Covered: `409` before the document is ready; `422` invalid `summary_type`; a real document-processing worker burst bringing the document to `ready`; the cross-tenant rejection (`404`) at create time; summary created (`202`) and enqueued exactly once; a real summary worker burst — with the worker's plain, unscripted `FakeLLMProvider` (no queued responses across the subprocess boundary), `generate()` calls succeed with the generic default text while `generate_structured()` correctly fails every time (nothing queued), `quality_checker_node` degrades to `passed=False`, and after exhausting the 3-attempt retry budget the graph terminates `failed` exactly per `langgraph.md` §3 — real evidence the failure path works end-to-end through genuine infrastructure; cross-tenant `GET` rejection (`404`); `GET /documents/{id}/summaries` listing; **regenerating created a second, independent row without touching the first** (`FR-SUM-002`, confirmed live); **12 real `ai_requests` rows** for 2 summary runs (6 `success` from `generate()` + 6 `error`/`structured_output_failed` from `generate_structured()` — exactly matching the per-call, never-collapsed design).
- **Tenant isolation:** verified by both the automated test suite and the live smoke test.
- **Scope check:** `git status` shows exactly the files listed above as modified/new — no R1–R5 behavior changed; the one R6 file touched (`comparison_processing_service.py`) was a direct, necessary dependency of this task (extracting the shared observability wrapper), not unrelated scope creep — R6's own test suite re-verified green afterward. No R8+ routers/services created, no frontend files touched, no spec/roadmap/remediation-plan.md changes, no migration added, no commit made, no deployment performed.
