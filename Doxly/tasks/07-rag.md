# Task 07: RAG — Query Processing, Context Assembly, Citations (Backend)

## Task ID
P07-001

## Feature
RAG — Query Processing, Context Assembly, Retrieval-Failure Handling, Citation Population

## Objective
Complete the non-generative half of RAG per `roadmap.md` Phase 7: wrap Phase 6's raw similarity search with query embedding + document-scope filtering, assemble the ranked/deduped/budget-trimmed context block, and provide the mechanism to persist citation rows — all ready to be called by a LangGraph node (Phase 8), which makes no LLM call itself. No frontend deliverable (confirmed with the user as the same backend-only exception used for Phases 3 and 6).

## Specification References
- `rag.md` §6–11 — this task's exact scope: similarity search (reused from Phase 6), metadata filtering, context assembly, citation model, retrieval-failure handling, retrieval-side hallucination prevention.
- `database.md` §3.10 — `citations` schema (already existed from Phase 3, unchanged).
- `requirements.md` `FR-RAG-001` (complete), `FR-RAG-003`.
- `testing.md` §4.2 (RAG/retrieval tests), §4.3 (citation tests).
- `skills/backend.md` — service-layer orchestration, constructor-injected DI, typed results.

## Requirements
- `FR-RAG-001` (P0, now complete): semantic retrieval scoped to a document, a document set, or the user's whole `ready` corpus — never another user's chunks.
- `FR-RAG-003` (P0): when no chunk clears the relevance threshold, the system signals "cannot answer from available documents" as a success path, not a fallback to ungrounded generation and not an exception.

## Dependencies
- Phase 6 (Embeddings & Vector Search) — `DocumentChunkRepository.similarity_search`, `EmbeddingProvider`, `document_chunks`. This task extends `similarity_search` (added `document_ids` for multi-document scope) and `TenantScopedRepository` (added `get_many` for provenance title lookups) rather than duplicating either.

## Files Affected
- `app/repositories/base.py` — modified — added `get_many()`.
- `app/repositories/document_repository.py` — modified — `similarity_search()` gained `document_ids` for multi-document scope.
- `app/services/retrieval_service.py` — new — `RetrievalService`, `ContextItem`, `AssembledContext`.
- `app/services/citation_service.py` — new — `CitationService`, `CitationInput`.
- `tests/test_retrieval_service.py`, `tests/test_citation_service.py` — new.

## Implementation Notes
- Tag/date-range filters (rag.md §7 point 3) are **not implemented** here — the spec explicitly assigns them to Global Search (Phase 13) only, not chat's retrieval path.
- `similarity_search`'s relevance threshold (already applied in Phase 6) is what produces `FR-RAG-003`'s empty result; `AssembledContext.is_empty` is the typed signal a future LangGraph node checks — modeled as an empty list, not an exception, since rag.md §10 is explicit this is "a success path for the system, not an error."
- `CitationService.record_citations` takes an already-created `message_id` as an explicit parameter rather than creating the `Conversation`/`Message` rows itself — `citations.message_id` is `NOT NULL`, and owning that lifecycle is Chat's (Phase 9's) job. Same "take the missing upstream stage as a parameter" pattern Phase 6's `EmbeddingService` used for text extraction.
- Deduping (rag.md §8 point 1) uses `difflib.SequenceMatcher` on chunk content directly — no new dependency, adequate at the small top-k candidate-set sizes this operates on.
- **Observed but not resolved this task:** `rag.md` §10 describes a retrieval-failure event as "logged as `ai_requests.status = 'success'` with a flag indicating zero-context response," but `database.md` §3.13's `ai_requests` schema has no such flag column. Not fixed here because nothing in this task actually writes to `ai_requests` — no LLM/chat request cycle exists yet to log against (that's Phase 9). Flagged explicitly in the completion report's Remaining Issues so it isn't silently lost; whichever phase first implements that logging call needs to add the column to `database.md` §3.13 and a migration at that time.

## Tests
- Integration, real test Postgres+pgvector (`test_retrieval_service.py`): provenance attachment (document title/page), `FR-RAG-003`'s empty-context success path, mandatory cross-tenant isolation at the service level, dedup collapsing near-identical chunks, token-budget trimming, single- vs multi-document `k` selection.
- Unit, faked repository (`test_citation_service.py`, skills/backend.md §3 pattern): citation persistence pass-through, empty-input no-op, the `ContextItem → CitationInput` convenience conversion (default and overridden snippet).
- Citation FK/constraint correctness was already covered by `test_constraints.py` (Phase 3) — not duplicated here.

## Acceptance Criteria
(Adapted from `requirements.md` §1.5, this task's scope)
- Given a query and a target document, only chunks from that document (and that user) are candidates.
- Given a query with no document filter, candidates are drawn only from the user's own documents.
- Given a query, the expected chunks are retrieved, ranked by similarity, deduped, and trimmed to the configured token budget.
- Given a query with no chunks above the relevance threshold, the result is an explicit empty/zero-context signal, not an exception and not a fallback to ungrounded generation.
- Given a message and a set of context items, citation rows are persisted with the correct `document_chunk_id`/`document_id`/`page_number`/`snippet`/`relevance_score` shape.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (49/49 backend pytest)
- [x] No requirement silently changed or reinterpreted — tag/date filtering and the `ai_requests` zero-context flag gap are explicitly called out as deferred, not silently dropped
- [x] No spec file required a change — `rag.md`/`database.md` were followed as written for everything this task actually implements
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)
