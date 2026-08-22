# Task 06: Embeddings & Vector Search (Backend)

## Task ID
P06-001

## Feature
Embeddings & Vector Search — Chunking, Embedding Generation, pgvector Storage, Raw Similarity Search

## Objective
Deliver the actual RAG indexing mechanics per `roadmap.md` Phase 6: split extracted text into retrieval-sized chunks, embed them through a swappable `EmbeddingProvider`, persist them into `document_chunks`, and provide a tenant-scoped, HNSW-indexed similarity search repository method. No frontend deliverable (confirmed with the user — same zero-frontend-deliverable situation as Phase 3, resolved the same way: build the real backend). No LLM answer generation, query-processing, or context assembly — that's Phase 7.

## Specification References
- `rag.md` §1–6 — pipeline overview, chunking strategy, chunk metadata, embeddings, vector dimensions, similarity search (this task's exact scope).
- `database.md` §3.4 — `document_chunks` schema (already existed from Phase 3; unchanged).
- `decisions.md` ADR-012, OQ-03 — `EmbeddingProvider` abstraction, resolved this task (see decisions.md's updated OQ-03 status).
- `performance.md` §6 — `NFR-PERF-005`, the join-free tenant-filter-first query design this task's `similarity_search` implements exactly.
- `skills/backend.md` — layering (repository-only queries, service-layer orchestration, constructor-injected DI), `app/ai/`/`app/document_processing/`/`app/services/` folder ownership.
- `specs/testing.md` §4 — RAG-layer test requirements: deterministic fixed test embeddings, tenant-isolation-under-adversarial-conditions, relevance-ordering.

## Requirements
- `FR-PROC-002` (P0): Chunking — recursive paragraph→sentence→hard-cut cascade, 500–800 target tokens, ~100-token overlap, `chunk_index`/`page_number`/`char_start`/`char_end` populated.
- `FR-PROC-003` (P0): Embedding generation — every chunk embedded (1536-dim, configured provider), `documents.status` transitions to `ready` once persisted.
- `FR-RAG-001` (P0, retrieval-mechanics half only): tenant-scoped, HNSW-indexed similarity search returning relevance-ordered, threshold-filtered results; the LLM-facing query-processing/context-assembly half is Phase 7.

## Dependencies
- Phase 3 (Database) — `document_chunks` schema, HNSW index, and `DocumentChunkRepository` stub already existed; this task fills in the methods that stub explicitly deferred.
- Phase 5 backend (Document Processing / text extraction) — **not built** (Phase 5 in this session was executed as a frontend-only status-UI slice). `EmbeddingService.process_extracted_text` therefore takes already-extracted plain text as an input parameter rather than performing extraction itself — the natural handoff point for whenever a real extraction worker lands.

## Files Affected
- `pyproject.toml` — modified — added `tiktoken` (real BPE token counting) and promoted `httpx` from dev-only to a main dependency.
- `app/core/config.py` — modified — added `embedding_provider`/`openai_api_key` settings.
- `app/errors.py` — new — `DoxlyError` base + `EmptyDocumentError`.
- `app/ai/__init__.py`, `app/ai/embeddings.py` — new — `EmbeddingProvider` ABC, `FakeEmbeddingProvider` (active default), `OpenAIEmbeddingProvider`, `get_embedding_provider()`.
- `app/document_processing/__init__.py`, `app/document_processing/chunking.py` — new — `chunk_text()`, `count_tokens()`.
- `app/repositories/document_repository.py` — modified — `DocumentRepository.set_status()`, `DocumentChunkRepository.bulk_create()`/`similarity_search()`, `ChunkSearchResult` DTO.
- `app/services/__init__.py`, `app/services/embedding_service.py` — new — `EmbeddingService.process_extracted_text()`.
- `tests/test_chunking.py`, `tests/test_embeddings.py`, `tests/test_document_chunk_repository.py`, `tests/test_embedding_service.py` — new.
- `specs/decisions.md` — modified — OQ-03 status resolved from "Assumption — confirm before Phase 6" to "Decided."

## Implementation Notes
- CSV's row-group chunking variant (rag.md §2) is **not implemented** — it needs structured row input a plain-text extractor doesn't produce, and no CSV parser exists yet. `chunk_text()` covers the PDF/DOCX/TXT plain-text case; CSV chunking is deferred to whenever Phase 5's backend CSV parsing lands.
- `similarity_search()` deliberately does **not** join to `documents` to enforce `status='ready'` — rag.md §7 assigns that filter to the metadata-filtering pipeline (Phase 7), and `performance.md` §6 is explicit that the denormalized `user_id` exists specifically so this query never needs a join back to `documents`. Adding one now would reintroduce the join-tax the design avoids.
- `EmbeddingService` raises `EmptyDocumentError` on zero chunks rather than itself recording `documents.status='failed'` — full `FR-PROC-004` failure-handling (sanitized user-facing messages, etc.) belongs to whichever caller performs extraction, which doesn't exist yet.
- The fake embedding provider uses feature hashing (word → dimension + sign, L2-normalized), not random noise, specifically so cosine similarity between texts sharing words is meaningfully higher than between unrelated texts — this is what makes ranking-order tests possible without a live API call.

## Tests
- Unit (pure, no DB) — `test_chunking.py`: empty/degenerate input, token-window adherence, overlap, hard-split fallback, page attribution. `test_embeddings.py`: dimension, determinism, relevance-preserving similarity, `get_embedding_provider()` config branching.
- Unit, service layer with faked repositories (skills/backend.md §3) — `test_embedding_service.py`: chunk→embed→persist→ready happy path, `EmptyDocumentError` on degenerate input never marks ready, chunk order preserved.
- Integration, real test Postgres+pgvector (testing.md's stated approach — query correctness isn't mockable) — `test_document_chunk_repository.py`: `user_id` denormalization sync, relevance-ordered results, **mandatory cross-tenant isolation** (a query for User A never returns User B's chunks), relevance-threshold filtering, single-document scoping, `k` limit, owner-scoped `set_status`.
- Manual/representative-scale verification (not part of the automated suite — a full 50k-chunk `NFR-PERF-005` load test is too slow for routine CI): 3,000-chunk insert + `EXPLAIN ANALYZE` confirmed the HNSW index (`ix_document_chunks_embedding_hnsw`) is genuinely selected by the planner (post-`ANALYZE`) and `similarity_search` returns in ~41ms, well within the 200ms budget.

## Acceptance Criteria
(Adapted from `requirements.md` §1.3/§1.4/§1.5, this task's scope)
- Given extracted text, when chunked, then each chunk is within the configured token range (with overlap) and carries `document_id`, `chunk_index`, `page_number` (if applicable), and character offsets.
- Given N chunks for a document, when embedding completes, then N rows exist with non-null embeddings of the configured dimension, and `documents.status` transitions to `ready`.
- Given a query and a target document, then only chunks from that document (and that user) are candidates. Given a query with no document filter, candidates are drawn only from the user's own chunks.
- Given a query, the expected chunks are retrieved, ranked by similarity, per rag.md §6.
- Given a corpus-wide query for User A, User B's chunks are never returned, including under adversarial ID-guessing conditions.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (38/38 backend pytest)
- [x] No requirement silently changed or reinterpreted — CSV chunking and the `status='ready'` join are explicitly called out as deferred, not silently dropped
- [x] `specs/decisions.md` updated (OQ-03 resolved) — the one spec change this task required
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)
