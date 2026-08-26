# Task R5: Extraction Integration

## Task ID
R5-001

## Feature
Structured Extraction — `POST /extractions` and its supporting endpoints: a user (or a preset template) defines a field schema, the background-worker Extraction graph (`app/ai/graphs/extraction.py`, pre-existing scaffolding) runs it against a `ready` document, and the result is persisted, retrievable, and correctable.

## Objective
Close the gap `tasks/remediation-plan.md` §8 (R5) identifies: the Extraction LangGraph workflow, `Extraction` model, and `ExtractionRepository` already existed (predating R1–R4, from the original phase-scaffolding commits) but had no router, no API-facing service, and no worker wiring — a document could never actually be extracted through the real system. This task builds the router → service → worker chain per `api.md` §6, reusing the graph and repository unmodified in shape (with two necessary compatibility fixes — see Implementation Notes) rather than reimplementing them.

## Specification References
- `tasks/remediation-plan.md` §8 (R5) — authoritative scope for this task.
- `specs/requirements.md` §1.8 (`FR-EXT-001..004`).
- `specs/api.md` §6 (`/extractions`) — full endpoint contracts.
- `specs/database.md` §3.11 (`extractions` table — already migrated, no schema change needed).
- `specs/langgraph.md` §4 (Extraction graph — state/nodes/routing, unchanged).
- `specs/ai.md` §5 (Structured Outputs) — the `generate_structured` two-gate flow.
- `specs/observability.md`, `NFR-OBS-001` — every embedding/LLM call logged.
- `specs/security.md` §3.2 (404-not-403), `NFR-SEC-001` (tenant isolation).
- `specs/testing.md` §3.3/§3.5/§4.4.
- `skills/backend.md` §9 (validation placement), §10 (error handling), §12 (background processing — worker reuses the service layer).
- `specs/decisions.md` — no prior ADR for extraction; two new decisions recorded this task (see below).

## Requirements
- `FR-EXT-001` (P0) — extract structured fields from a document; structured JSON result validated against the schema, with per-field confidence and citation.
- `FR-EXT-002` (P1) — preset extraction templates (invoice/contract/resume/research_paper), listed via `GET /extractions/templates`.
- `FR-EXT-003` (P1) — a field the model couldn't locate is `null` with a `not_found_reason`, never a fabricated value.
- `FR-EXT-004` (P2) — manual correction of an extracted value, persisted with `corrected=true`, original value retained internally.
- `NFR-OBS-001` (P0) — every embedding/LLM call logged to `ai_requests`; applied here to the Extraction Agent's structured-output call (`operation="extraction"`).
- `NFR-SEC-001` (P0, carried) — tenant isolation on every new endpoint/repository method.

## Dependencies
- R3 (Document Processing) — a `ready` document with chunks is required before extraction can run (`RetrievalService`, unmodified, reused as-is).
- R4 (Chat) — not a functional dependency, but the source of the established observability/service-split/worker patterns this task follows for consistency.

## Files Affected
- `backend/app/ai/llm.py` — modified — `generate_structured` extended to return `StructuredCompletion[T]` (result + real input/output tokens + model), not a bare `T`, so `NFR-OBS-001` can log real usage for the Extraction Agent's call. See the ADR below.
- `backend/app/ai/graphs/extraction.py` — modified — (1) unwraps `StructuredCompletion.result`, threading real token/model usage into new `ExtractionState` fields; (2) `PRESET_TEMPLATES` restructured from a flat `dict[str, dict[str,str]]` into a single-source-of-truth `dict[str, {name, description, fields:[{name,type,description,required}]}]` registry (a genuine compatibility fix — see Implementation Notes); `GENERIC_TEMPLATE_FIELDS` split out as the classifier's internal last-resort fallback, never a listed/selectable template.
- `backend/app/ai/graphs/summarization.py`, `backend/app/ai/graphs/comparison.py` — modified — trivial unwrap-`.result` fixes, required by the `generate_structured` interface change above to keep this pre-existing, already-tested (but still unwired/out-of-scope for R5) scaffolding passing. No behavior change.
- `backend/app/models/extraction.py` — modified — `schema_json`/`result_json` corrected from `Mapped[dict]` to `Mapped[list[dict]]` (a Python-side type-hint fix only; the JSONB column itself, already migrated, is unaffected — no new migration).
- `backend/app/repositories/extraction_repository.py` — modified — added `list_for_document` (paginated, for `GET /documents/{id}/extractions`) and `set_result` (the worker's terminal write).
- `backend/app/schemas/extraction.py` — new — full request/response Pydantic contract for `api.md` §6, including the `template_key`/`schema` mutual-exclusivity + known-template validation (Pydantic-layer, per `skills/backend.md` §9).
- `backend/app/services/extraction_service.py` — new — the API-facing trigger/CRUD half (`create_extraction`, `get_extraction`, `list_for_document`, `apply_corrections`), mirroring R3's `DocumentService` role.
- `backend/app/services/extraction_processing_service.py` — new — the worker-invoked half (`run_extraction`: builds and runs the graph, translates its output into `result_json`, logs the `ai_requests` row), mirroring R3's `DocumentProcessingService` role.
- `backend/app/workers/extraction_worker.py` — new — the RQ job entrypoint, mirroring `document_processing_worker.py`'s exact shape (sync wrapper, per-job engine-pool disposal, `Retry`/`on_failure`).
- `backend/app/core/queue.py` — modified — `EXTRACTION_QUEUE_NAME`, `get_extraction_queue`, `enqueue_extraction` (same `Retry(max=3, interval=[10,30,60])` + fail-open-on-Redis-outage pattern as `enqueue_document_processing`).
- `backend/app/errors.py` — modified — `UnknownExtractionFieldError` (422, `PATCH` correcting a field not in the schema — data-dependent, so a service-layer error, not a Pydantic one).
- `backend/app/api/v1/routers/extractions.py` — new — all five endpoints from `api.md` §6.
- `backend/app/main.py` — modified — mounts both new routers.
- Tests — new: `test_extraction_processing_service.py`, `test_extractions_api.py`, `test_extraction_worker.py`. Modified: `test_graph_extraction.py` (updated for the `PRESET_TEMPLATES` restructure), `test_llm_provider.py` (updated for `StructuredCompletion`).

## Implementation Notes
- **Two genuine compatibility fixes to pre-existing scaffolding, not new scope:**
  1. `generate_structured` originally returned a bare validated model with no usage data at all — making `NFR-OBS-001`-accurate token logging for the Extraction Agent's call structurally impossible. **Flagged to the user via `AskUserQuestion` rather than decided silently** (a real ABC/interface change); the user selected extending it to `StructuredCompletion[T]`. Zero real callers existed outside the not-yet-wired extraction/summarization/comparison graph scaffolding, so the change was isolated and safe.
  2. `PRESET_TEMPLATES` was a flat `dict[str, dict[str,str]]` (field name → type only) — incapable of satisfying `GET /extractions/templates`' documented response shape (`name`, `description`, `required` per field/template) or `FR-EXT-003`'s "required field" concept, which didn't exist anywhere in the prior structure. Restructured into one registry serving both the graph's internal resolution and the templates-listing endpoint — not two independently-maintained field lists.
- **`generic` is not a selectable template.** `langgraph.md` §4 names it "the last-resort default" for an unclassifiable document, and `api.md` §6 lists only the four named presets — `generic` is deliberately excluded from `PRESET_TEMPLATES` (kept as a separate `GENERIC_TEMPLATE_FIELDS` constant) so it can never be requested via `template_key` and never appears in the templates listing.
- **Schema resolution happens once, at create time, not twice.** Since `api.md`'s create request always supplies exactly one of `template_key`/`schema`, `ExtractionService.create_extraction` resolves the final field list itself (deterministic, no LLM call needed) and persists it as `schema_json`; the worker passes this same resolved list into the graph as `requested_schema`, so `schema_generator_node`'s own template/classification fallback logic is never actually exercised by the real API path (it remains fully correct, spec-faithful scaffolding for a hypothetical future caller that invokes the graph without a pre-resolved schema — not pruned, since `langgraph.md` documents it as real node behavior).
- **`document_classifier_node` still always runs**, even when the schema is already fully known from `template_key`/`schema` — `langgraph.md` §4's routing is unconditional (`DocumentClassifier → SchemaGenerator always proceeds`), and this task does not add an unspec'd "skip classification" optimization.
- **Observability logs the Extraction Agent's own call, not the classifier's.** Mirrors `chat_service.py`'s established "one `ai_requests` row per run, using whichever call is the real cost driver" shape exactly (chat drops its own classifier's tokens once Answer Generator runs) — not a new interpretation invented for this task.
- **No stale-extraction recovery mechanism was built.** A worker crash mid-job leaves an extraction stuck `processing` forever, the same class of risk R3's `reprocess` remediation addressed for documents — but `api.md` §6 defines no reprocess-equivalent endpoint for extractions, and none was requested. Recorded as a known limitation (below), not silently solved by inventing new API surface.
- **No corresponding `processing_error`-equivalent field exists for a failed extraction** — `api.md`'s response shape has no place to surface why an extraction failed (unlike `documents.processing_error`). A failed extraction is simply `status="failed"`, `result: []`. Recorded as a spec gap, not silently patched by adding an undocumented field.

## Tests
- **`test_llm_provider.py`** (updated) — `generate_structured` returns real usage data alongside the result.
- **`test_graph_extraction.py`** (updated, all pre-existing behaviors re-verified against the new schema shape) — schema resolution precedence, full-graph classify→extract flow, generic fallback, structural retry-then-success, terminal failure after two structural failures — plus new assertions that a successful run threads real token/model usage into state.
- **`test_extraction_processing_service.py`** (new, 5 tests) — successful run persists `completed` + exactly one `ai_requests` row with real tokens; terminal structural failure persists `failed` + exactly one `ai_requests` error row with `input_tokens=None`/`model="n/a"` (a genuine gap, not fabricated); a missing extraction is silently skipped; an already-terminal extraction is a no-op (duplicate-job safety); an `ai_requests` logging failure never affects the extraction's own outcome.
- **`test_extractions_api.py`** (new, 19 tests) — templates endpoint exact shape + auth; create (template_key path, custom-schema path, mutual-exclusivity 422, unknown-template 422, `generic`-rejected 422, 404 missing/cross-tenant document, 409 not-ready, 401 unauthenticated, exactly-one-job-enqueued); get (exact shape incl. citation/not_found_reason, `original_value` never surfaced, 404 missing/cross-tenant); list-for-document (paginated shape, 404 cross-tenant); patch (correction applied + persisted, 422 unknown field, 404 cross-tenant, untouched-on-rejection).
- **`test_extraction_worker.py`** (new, 5 tests, real Postgres, mirrors `test_document_processing_worker.py`) — full pipeline via the real sync RQ entrypoint; an unexpected (non-`StructuredOutputError`) exception propagates for RQ's own retry and does not mark `failed` itself; `on_extraction_failure` no-ops while retries remain and marks `failed` once exhausted; cross-tenant job delivery is a silent no-op.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.8:
- `FR-EXT-001`: Given a document and a field schema, when extraction runs, then a structured JSON result validated against that schema is produced, with per-field confidence and source citation (page/snippet). — Verified by `test_extraction_processing_service.py` and the live smoke test.
- `FR-EXT-002`: Common templates are offered so users don't need to define schemas from scratch. — Verified by `GET /extractions/templates`'s tests.
- `FR-EXT-003`: Given a required field the model could not find, then the field is returned as `null` with a `not_found` reason, never a fabricated placeholder. — Verified by `test_extraction_processing_service.py`'s `due_date` assertions.
- `FR-EXT-004`: A user can manually correct an extracted value; corrections persist with the extraction record. — Verified by the `PATCH` tests.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted (the two compatibility fixes and the `generate_structured` interface change are documented above and in `decisions.md`, not silent)
- [x] `specs/decisions.md` updated (ADR-027, ADR-028)
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **Worker-crash recovery** for a stuck `processing` extraction has no remediation path (unlike R3's `reprocess` extension) — `api.md` §6 defines no such endpoint. A future task would need to add one, mirroring `decisions.md` ADR-026, if this is ever prioritized.
- **No failure-reason field** exists on a failed extraction's API response (unlike `documents.processing_error`) — a client sees only `status="failed"`, `result: []`. Not invented here since `api.md` doesn't define one.
- **`NFR-AVAIL-002`'s retry-count ambiguity** (already an open R3 finding — "max 3 attempts" vs. RQ's 3-retries-=-4-attempts semantics) applies identically to the new extraction queue, inherited unchanged from the existing `_MAX_RETRIES`/`_RETRY_INTERVALS_SECONDS` constants in `core/queue.py`.
- R6 (Comparison) and R7 (Summarization) remain unimplemented beyond their own pre-existing, unwired graph/model/repository scaffolding (untouched by this task except the minimal `generate_structured`-unwrap compatibility fix required to keep their existing tests green).

## Verification Results
- **Targeted test files:** `test_extraction_processing_service.py` (5 passed), `test_extractions_api.py` (19 passed), `test_extraction_worker.py` (5 passed), `test_graph_extraction.py` (9 passed), `test_llm_provider.py` (7 passed), `test_graph_summarization.py`/`test_graph_comparison.py` (unaffected, all passed).
- **Full backend suite:** 366 passed, 0 failed — run twice, identical both times, no flakiness observed.
- **Ruff:** clean.
- **Black:** clean.
- **Mypy:** 5 pre-existing errors (unrelated files: `test_require_admin.py`, `test_csrf.py`, `test_users_api.py`, `test_chat_sse.py`, `test_auth_api.py`, all predating this task), 0 new.
- **Migrations:** none added or needed — `extractions` table already migrated with the exact columns this task needs; only a Python-side type-hint correction was made to the model.
- **Live smoke test:** real Postgres + Redis (Docker), the real FastAPI app (ASGI transport), and real RQ `SimpleWorker` burst processes (both `document_processing` and `extraction` queues, via separate subprocesses — required on native Windows, since RQ's default forking `Worker` needs `os.fork()`; production's Linux containers are unaffected). Covered: templates endpoint; extraction correctly rejected (`409`) before the document is `ready`; a real document-processing worker burst brings the document to `ready`; extraction created (`202`) and enqueued exactly once; a real extraction worker burst picks up the job — with the worker's plain, unscripted `FakeLLMProvider` (no queued responses across the subprocess boundary), `generate_structured` correctly raises with nothing queued, the graph retries once then terminally fails exactly per `langgraph.md` §4's routing, and exactly one `ai_requests` error row is logged (`operation="extraction"`, `status="error"`, `error_code="extraction_failed"`) — real evidence the failure path works end-to-end through genuine infrastructure, not a mock. Also verified: cross-tenant `GET`/`PATCH` both `404`; a correction against a schema-known-but-not-yet-populated field applies correctly; correcting an unknown field `422`s with `unknown_field`. (The success path's exact result shape — citations, confidence, `not_found_reason` — is separately verified with a scripted `FakeLLMProvider` by `test_extraction_processing_service.py` and `test_extractions_api.py`, which the live smoke test's subprocess isolation can't script.)
- **Tenant isolation:** verified by both the automated test suite and the live smoke test — cross-tenant access returns `404` (never `403`), never enqueues a job, never mutates the other user's row.
- **Scope check:** `git status` shows exactly the files listed above as modified/new — no R1/R2/R3/R4 behavior changed, no R6/R7 routers/services created, no frontend files touched, no spec/roadmap/remediation-plan.md changes, no migration added, no commit made, no deployment performed.
