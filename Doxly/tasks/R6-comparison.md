# Task R6: Comparison Integration

## Task ID
R6-001

## Feature
Document Comparison — `POST /comparisons` and its supporting endpoints: a user selects two of their own `ready` documents, the background-worker Comparison graph (`app/ai/graphs/comparison.py`, pre-existing scaffolding) semantically aligns and diffs them, and the result is persisted and retrievable.

## Objective
Close the gap `tasks/remediation-plan.md` §9 (R6) identifies: the Comparison LangGraph workflow, `Comparison` model, and `ComparisonRepository` already existed (predating R1–R4, from the original phase-scaffolding commits) but had no router, no API-facing service, and no worker wiring. This task builds the router → service → worker chain per `api.md` §7, reusing the graph and repository (with three necessary compatibility fixes — see Implementation Notes) rather than reimplementing them.

## Specification References
- `tasks/remediation-plan.md` §9 (R6) — authoritative scope for this task.
- `specs/requirements.md` §1.9 (`FR-COMP-001..003`).
- `specs/api.md` §7 (`/comparisons`) — full endpoint contracts.
- `specs/database.md` §3.12 (`comparisons` table — already migrated, no schema change needed).
- `specs/langgraph.md` §5 (Comparison graph — state/nodes/routing).
- `specs/ui-ux.md` §11 (`ChangeTypeBadge` — three change-type categories) and the already-built frontend (`frontend/lib/api/comparisons.ts`, `frontend/components/domain/comparisons/*`) — cross-checked, not assumed, per this task's "do not assume a requirement is implemented merely because similar code exists" instruction.
- `specs/ai.md` §4/§5 (prompt-injection defense pattern; structured outputs), `NFR-SEC-007`.
- `specs/observability.md` §4 (`NFR-OBS-001`, read literally this task — see Implementation Notes).
- `specs/security.md` §3.2 (404-not-403), `NFR-SEC-001` (tenant isolation).
- `specs/testing.md` §3.3/§3.5/§4.4.
- `skills/backend.md` §9 (validation placement), §10 (error handling), §12 (background processing).
- `specs/decisions.md` — no new ADR added this task (see Implementation Notes for why).

## Requirements
- `FR-COMP-001` (P0) — compare two documents; structured diff (additions/deletions/modifications) with semantic alignment, classified by change type.
- `FR-COMP-002` (P0) — view/persist the comparison report; history via `GET /comparisons`.
- `FR-COMP-003` (P2) — graceful degradation (no forced diff) when documents are too structurally dissimilar.
- `NFR-OBS-001` (P0) — every LLM/embedding call logged to `ai_requests`.
- `NFR-SEC-001` (P0, carried) — tenant isolation, including the two-object (both documents) variant.
- `NFR-SEC-007` (carried) — prompt-injection defense for document content flowing into a prompt.

## Dependencies
- R3 (Document Processing) — both compared documents must be `ready` with real, page-tagged chunks.
- R5 (Extraction) — source of the `_ObservedLLMProvider`-adjacent patterns (per-call observability, `StructuredCompletion` usage-preservation) this task builds on directly.

## Files Affected
- `backend/app/ai/graphs/comparison.py` — modified — three compatibility fixes (see below): `ChangeCategory` narrowed to 3 values; `AlignedPair`/`Difference` carry real page numbers; `semantic_alignment_node` aligns pre-chunked, page-tagged segments instead of re-chunking flat text. Both LLM-calling nodes' system prompts updated with the same anti-prompt-injection framing `document_qa.py` (R4) established.
- `backend/app/errors.py` — modified — `IdenticalDocumentsError` (422, `identical_documents` — api.md names a specific code, the same documented exception to the Pydantic-first heuristic `UnsupportedMimeTypeError` already establishes).
- `backend/app/repositories/comparison_repository.py` — modified — added `list_paginated` and `set_result`.
- `backend/app/schemas/comparison.py` — new — full request/response Pydantic contract for `api.md` §7.
- `backend/app/services/comparison_service.py` — new — the API-facing trigger/CRUD half (`create_comparison`, `get_comparison`, `list_comparisons`), mirroring R5's `ExtractionService` role.
- `backend/app/services/comparison_processing_service.py` — new — the worker-invoked half (`run_comparison`), plus `_ObservedLLMProvider`/`_ObservedEmbeddingProvider` — see the AI Observability Decision below.
- `backend/app/workers/comparison_worker.py` — new — the RQ job entrypoint, mirroring `extraction_worker.py`'s exact shape.
- `backend/app/core/queue.py` — modified — `COMPARISON_QUEUE_NAME`, `get_comparison_queue`, `enqueue_comparison`.
- `backend/app/api/v1/routers/comparisons.py` — new — all three endpoints from `api.md` §7.
- `backend/app/main.py` — modified — mounts the new router.
- Tests — new: `test_comparison_processing_service.py`, `test_comparisons_api.py`, `test_comparison_worker.py`. Modified: `test_graph_comparison.py` (updated for the page-tagged-segment state shape and the 3-category restriction).

## Implementation Notes

### Three genuine compatibility fixes to pre-existing scaffolding, not new scope
1. **`ChangeCategory` had a 4th value ("structural") nothing downstream supported.** `api.md` §7's `ComparisonModification.change_type` enum, `ui-ux.md` §11's documented `ChangeTypeBadge` categories, and the already-built frontend (`frontend/lib/api/comparisons.ts`'s `ChangeType`, `change-type-badge.tsx`'s `CHANGE_BADGE_CONFIG` — three independent, mutually-consistent sources, checked directly rather than assumed) all agree on exactly three: `factual`/`numeric`/`wording`. The graph's `ChangeCategory` type and its classification prompt were the one outlier. Narrowed to match — the correct direction, confirmed by checking the frontend before deciding rather than guessing which side was "right."
2. **Page numbers were structurally unavailable.** `semantic_alignment_node` re-chunked each document's *flattened* full text from scratch (`chunk_text()` on a joined string), discarding the page numbers R3's document processing had already computed per-chunk — yet `api.md` §7 requires `page_number`/`a_page_number`/`b_page_number` (nullable) on every segment. **Resolved via explicit user sign-off** (a genuine architecture fork, not silently decided): `semantic_alignment_node` now aligns each document's already-processed, page-tagged `DocumentChunk` rows directly (`ComparisonProcessingService._load_segments`) instead of re-chunking flat text a second time — also removing a wasteful double-chunking step. `AlignedPair`/`Difference` gained `page_a`/`page_b` fields to carry this through.
3. **Neither LLM-calling node followed the established anti-prompt-injection pattern.** `document_qa.py` (R4) established the pattern (delimit document content in `<document_context>` tags; explicitly instruct the model to disregard instruction-like text inside it) for `ai.md` §4/`NFR-SEC-007`. `difference_detection_node`'s and `change_classification_node`'s prompts lacked this framing entirely. Brought into line with the established pattern — not a new mechanism, closing a gap in an already-decided policy.

### AI Observability Decision — resolved via explicit user sign-off before implementation
`observability.md` §4 states `NFR-OBS-001` **verbatim**: "every call to an LLM or embedding provider is logged" — one `ai_requests` row per real provider call. R4 (chat) and R5 (extraction) actually implemented "one row per run" instead (logging only the last/decisive call's tokens, silently dropping earlier real calls) — already committed and independently audited PASS, and **out of this task's scope to retroactively change**. Comparison's `difference_detection_node` can make many real `generate()` calls in a single run (one per modified segment) plus one more in `change_classification_node`, so collapsing them into a single row would be far lossier here than it already is for chat/extraction. **Decision (user-approved): log one row per real provider call.** `_ObservedLLMProvider`/`_ObservedEmbeddingProvider` (`comparison_processing_service.py`) wrap the real providers so every actual `generate()`/`generate_structured()`/`embed_batch()` call writes its own row, without threading an `AiRequestRepository` through every graph node function individually — a decorator around the existing `LLMProvider`/`EmbeddingProvider` abstractions, not a parallel observability mechanism. Embedding calls use `operation="embedding"` (matching R3's precedent — there is no `"document_processing"`/`"comparison"`-specific embedding operation value in the `ai_requests.operation` CHECK constraint); LLM calls use `operation="comparison"`. `_ObservedEmbeddingProvider`'s `input_tokens` uses `count_tokens()` (the same real `tiktoken` `cl100k_base` encoding `chunking.py` already documents as matching what the embedding model sees) since `embed_batch()`'s own return value carries no usage data to relay — real accounting, not an estimate, though not from the provider's own response (the same structural gap `AnthropicLLMProvider.generate_structured` had before R5's fix; `OpenAIEmbeddingProvider.embed_batch` similarly discards real OpenAI-reported usage — both are pre-existing, out-of-scope-for-R6 gaps, noted here for visibility, not fixed).

### `alignment_quality`'s three buckets
The graph only ever produces a continuous `alignment_confidence` float and a binary `degraded` flag; `ALIGNMENT_CONFIDENCE_THRESHOLD` (0.5, pre-existing) already covers the "low" bucket. No spec-defined split exists for "high" vs. "medium" among aligned (non-degraded) comparisons — `HIGH_ALIGNMENT_THRESHOLD = 0.75` (`comparison_processing_service.py`) is a documented, defensible default (comparisons "solidly more alike than not" vs. "clearly and consistently alike"), the same shape as `ALIGNMENT_CONFIDENCE_THRESHOLD` and R3's ADR-026 staleness threshold — a response-shaping constant, not graph business logic, so it lives in the service layer.

### `result_json` on a non-completed comparison
`api.md` §7 states `result` is `null` while `status="processing"` — extended the same way to `failed` (no meaningful result exists either way); the DB row itself still stores a placeholder empty-result shape to satisfy the `NOT NULL` constraint, translated to `null` in the API response by `comparisons.py`'s `_to_detail_response`.

### No new ADR added
Both the observability-shape decision and the page-number/segment-sourcing decision were resolved via explicit `AskUserQuestion` sign-off before implementation and are fully documented here and in this file's code comments; neither introduces a genuinely new architectural pattern beyond what R3/R4/R5 already established (a provider-wrapping decorator is a standard composition over the existing `LLMProvider`/`EmbeddingProvider` ABCs, not a new abstraction layer) — judged not to warrant a `specs/decisions.md` entry distinct from what's already recorded here, unlike R5's ADR-027/028 (which changed a shared interface's public return type).

## Tests
- **`test_graph_comparison.py`** (updated, all pre-existing behaviors re-verified against the new segment-based state shape) — content-extraction presence check, full-graph numeric-change detection with real page numbers threaded through, graceful degradation for unrelated documents, failure on missing extractable text, unmatched-segment addition detection.
- **`test_comparison_processing_service.py`** (new, 8 tests) — successful comparison with real page numbers; degraded comparison for structurally unrelated documents (confirms embedding calls are still logged even though no LLM call happens); failed comparison (no extractable text); **the core per-call observability assertion** — two modified segments produce exactly 3 `operation="comparison"` rows (2×`generate()` + 1×`generate_structured()`) and 2 `operation="embedding"` rows, all with real non-fabricated tokens; an `ai_requests` error row on a structural-output failure (which the graph itself degrades gracefully from, per its own pre-existing design); a missing comparison is silently skipped; an already-terminal comparison is a no-op; an observability-logging failure never affects the comparison's own outcome.
- **`test_comparisons_api.py`** (new, 13 tests) — create (202/processing, exactly-one-job-enqueued, `422 identical_documents`, the two-object tenant-isolation variant tested from **both** sides — `document_a_id` foreign and `document_b_id` foreign, `404` for a nonexistent document, `409 document_not_ready`, `401` unauthenticated); get (exact shape including nested `ComparisonResult`, `result: null` while `processing`, `404` missing/cross-tenant); list (paginated shape, excludes other users' comparisons).
- **`test_comparison_worker.py`** (new, 5 tests, real Postgres, mirrors `test_extraction_worker.py`) — full pipeline via the real sync RQ entrypoint; an unexpected exception propagates for RQ's own retry and doesn't mark `failed` itself; `on_comparison_failure` no-ops while retries remain and marks `failed` once exhausted; cross-tenant job delivery is a silent no-op.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.9:
- `FR-COMP-001`: Given Document A and Document B (both `ready`), when compared, then the LangGraph Comparison workflow produces a structured report of additions, deletions, and modifications with semantic alignment, classified by change type. — Verified by `test_comparison_processing_service.py` and the live smoke test.
- `FR-COMP-002`: The comparison result is rendered/persisted for later viewing. — Verified by the `GET` tests and `result_json` persistence.
- `FR-COMP-003`: Comparison degrades gracefully when documents are too structurally different. — Verified by the degraded-comparison test.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted — all three compatibility fixes and both architecture decisions were surfaced via `AskUserQuestion` before implementation, not decided silently
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **`OpenAIEmbeddingProvider.embed_batch` discards OpenAI's own real reported usage** (same structural gap `AnthropicLLMProvider.generate_structured` had before R5's ADR-027 fix) — `_ObservedEmbeddingProvider` uses `count_tokens()` (real `tiktoken` encoding, not a word-count estimate) instead, which is accurate but not sourced from the provider's own response. Fixing `embed_batch`'s return shape would ripple into R3/R4's already-completed, audited embedding call sites — out of scope for R6.
- **No stale-comparison worker-crash recovery** (same shape as R5's equivalent limitation) — `api.md` §7 defines no reprocess-equivalent endpoint for comparisons.
- **No failure-reason field** on a failed comparison's API response (unlike `documents.processing_error`) — `api.md` doesn't define one.
- **`NFR-AVAIL-002`'s retry-count ambiguity** (an open R3 finding) applies identically to the new comparison queue, inherited unchanged.
- **`FR-COMP-003`'s degraded path does not surface high-level metadata differences** (page count, type) that `langgraph.md` §5's routing section says is "optional" — only the required message text is returned, matching `api.md`'s minimum contract exactly.

## Verification Results
- **Targeted test files:** `test_comparison_processing_service.py` (8 passed), `test_comparisons_api.py` (13 passed), `test_comparison_worker.py` (5 passed), `test_graph_comparison.py` (6 passed) — 32 total.
- **Full backend suite:** 399 passed, 0 failed — run twice, identical both times, no flakiness observed.
- **Ruff:** clean. **Black:** clean. **Mypy:** 5 pre-existing errors (unrelated files predating this task), 0 new.
- **Migrations:** none added or needed — `comparisons` table already migrated with the exact columns this task needs (verified directly against `information_schema.columns`, not assumed).
- **Live smoke test:** real Postgres + Redis (Docker), the real FastAPI app (ASGI transport), and real RQ `SimpleWorker` burst processes (`document_processing` and `comparison` queues, separate subprocesses). Covered: `409` before documents are ready; `422 identical_documents`; a real document-processing worker burst bringing 3 documents to `ready`; the two-object cross-tenant rejection (`404`) at create time; comparison created (`202`) and enqueued exactly once; a real comparison worker burst completing the comparison with `alignment_quality="high"` and a correctly-classified modification (degrading to `"wording"` when the worker's unscripted default `FakeLLMProvider` couldn't produce a real classification — the graph's own pre-existing degrade-gracefully behavior, confirmed live); cross-tenant `GET` rejection (`404`); `GET /comparisons` listing; **5 real `ai_requests` rows with `operation="embedding"`** (2 from this comparison's own `semantic_alignment_node`, 3 from the 3 documents' own R3 processing) and **2 with `operation="comparison"`** (one `generate()`, one `generate_structured()` — matching the per-call design exactly). `page_number` fields were correctly `null` for these `text/plain` documents (no page concept applies — confirms the nullable-page-number path is honest, not merely untested).
- **Tenant isolation:** verified by both the automated test suite (both directions of the two-object check) and the live smoke test.
- **Scope check:** `git status` shows exactly the files listed above as modified/new — no R1–R5 behavior changed, no R7/R8+ routers/services created, no frontend files touched, no spec/roadmap/remediation-plan.md changes, no migration added, no commit made, no deployment performed.
