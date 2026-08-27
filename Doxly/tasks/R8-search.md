# Task R8: Global Search

## Task ID
R8-001

## Feature
Global Search — `GET /search`: corpus-wide, hybrid (full-text + vector) search across a user's own documents, ranked by reciprocal rank fusion, with highlighted snippets and filename matches.

## Objective
Closes the gap `tasks/remediation-plan.md` §11 (R8) identifies: no `tsvector`/GIN migration, repository, service, or router existed for search — only the conversation-scoped vector similarity search built for chat retrieval (`retrieval_service.py`), which is document-selection-scoped, not the corpus-wide search `FR-SEARCH-001` requires. This task adds the missing schema (per `rag.md` §12's already-decided hybrid design), a repository implementing reciprocal rank fusion over Postgres full-text and pgvector cosine similarity, and the API-facing service/router, reusing R3's chunk/embedding infrastructure and R1's auth/rate-limit dependencies unchanged.

## Specification References
- `tasks/remediation-plan.md` §11 (R8) — authoritative scope for this task.
- `specs/requirements.md` §1.10 (`FR-SEARCH-001..003`).
- `specs/api.md` §8 (`/search`) — full endpoint contract, including the offset-based `SearchSnippet` shape the frontend (`frontend/lib/api/search.ts`, Phase 13) already expects verbatim.
- `specs/rag.md` §12 (Hybrid Search) — the RRF formula and dual-tsvector design this task implements exactly as specified, not reinvented.
- `specs/database.md` §3.3/§3.4 — schema sections updated alongside the migration, per remediation-plan.md §11.1's explicit instruction.
- `specs/observability.md` §4 (`NFR-OBS-001`) — every embedding-provider call logged.
- `specs/security.md` §3.2 (404-not-403 — not applicable here, search has no single-resource ownership check, but tenant scoping is still `NFR-SEC-001`-critical), `skills/database.md` §10 (multi-tenant isolation checklist).
- `specs/testing.md` §3.5 (mandatory cross-tenant test category).
- `skills/database.md` §4 (hand-authored generated columns/GIN index), §7 (deliberate indexing).

## Requirements
- `FR-SEARCH-001` (P0) — keyword/semantic search across all owned documents' content and metadata; ranked, highlighted, strictly scoped to the caller.
- `FR-SEARCH-002` (P1) — filter by document type (`mime_type`), tag, date range, and processing status.
- `FR-SEARCH-003` (P1) — hybrid full-text + vector ranking via reciprocal rank fusion.
- `NFR-SEC-001` (P0, carried) — tenant isolation on the new repository method and endpoint.
- `NFR-OBS-001` (P0, carried) — the query-embedding call (the one provider call this endpoint makes) logs an `ai_requests` row, success and failure.

## Dependencies
- R3 (Document Processing) — real, embedded `document_chunks` content to search over.
- R1 (`rate_limit_general`, `get_current_user`) — reused unchanged; no new auth/CSRF pattern needed (`GET`-only, no CSRF dependency per `security.md` §6.3).

## Files Affected
- `backend/alembic/versions/20260827_search_tsvector.py` — **new** — generated `search_vector` `TSVECTOR` columns (`document_chunks.content`, `documents.file_name`) + GIN indexes. Hand-authored (autogenerate cannot express a generated column or a GIN index).
- `backend/app/models/document.py` — modified — `search_vector` mapped on both `Document`/`DocumentChunk` (ORM-awareness only, mirroring the existing HNSW-index convention — the GIN index itself is not declared in `__table_args__`).
- `backend/app/repositories/search_repository.py` — **new** — `SearchRepository.search()`: builds a `filtered_documents` CTE (tenant + `FR-SEARCH-002` filters), a vector-candidate CTE, a fulltext-candidate CTE (content chunks UNION filename matches), fuses both via RRF, returns `(hits, total)`.
- `backend/app/schemas/search.py` — **new** — `SearchSnippet`/`SearchResultItem`/`SearchResponse`, matching `api.md` §8 and the already-built frontend contract exactly.
- `backend/app/services/search_service.py` — **new** — embeds the query (observed), delegates to the repository, builds offset-based snippets/highlights.
- `backend/app/api/v1/routers/search.py` — **new** — `GET /search`, general rate-limit tier only, the `date_from > date_to` 422 check.
- `backend/app/main.py` — modified — mounts the new router.
- `specs/database.md` — modified — §3.3/§3.4 schema tables document the new `search_vector` columns and their GIN indexes (remediation-plan.md §11.1's required spec update, done alongside the migration in this same task).
- Tests — new: `test_search_repository.py` (10 tests), `test_search_api.py` (10 tests).

## Implementation Notes

### Reciprocal rank fusion, built in SQLAlchemy Core, not raw `text()`
`rag.md` §12's formula (`1/(k + rank_vector) + 1/(k + rank_fulltext)`, `k=60`) is implemented as a sequence of CTEs: `filtered_documents` (tenant + filter scoping, applied once, shared by both ranking methods) → `vector_candidates` (top-50 by cosine distance) and `fulltext_ranked` (top-50 by `ts_rank`, itself a `UNION ALL` of chunk-content matches and filename matches) → `combined` (`FULL OUTER JOIN` on a synthetic `match_key`, RRF-scored) → a final join back to `document_chunks`/`filtered_documents` for content/page/file_name. Built entirely with SQLAlchemy Core (`select()`, `.cte()`, `func.row_number().over(...)`, `.join(..., full=True)`) rather than raw `text()` — `skills/database.md` §3 reserves raw SQL for what the ORM genuinely can't express, and `DocumentChunk.embedding.cosine_distance(...)` (the one part that could have forced raw SQL) is the same proven construct `DocumentChunkRepository.similarity_search` already uses.

### Two real defects found and fixed while verifying against live Postgres (not assumed correct)
1. **No relevance floor on vector candidates.** An unfiltered top-k vector search always returns *something* — the least-dissimilar chunk in the corpus — even when nothing is actually relevant. In a small test corpus this let a wholly irrelevant chunk win a fused-ranking tiebreak over a genuine filename match. Fixed by reusing `rag.md` §6's existing relevance-threshold pattern: `VECTOR_MIN_SIMILARITY = 0.75` (the same default `retrieval_service.py` already uses), applied as a `WHERE similarity >= :min_similarity` predicate before a chunk ever enters the candidate pool. Not a new number invented for this task — the existing retrieval threshold, reused.
2. **Filenames with an extension don't tokenize the way a naive `to_tsvector(file_name)` assumes.** Verified directly against Postgres: `to_tsvector('english', 'invoice-march.pdf')` produces exactly one lexeme (`'invoice-march.pdf'`) — Postgres's default parser classifies a `word.ext`-shaped string as a single "file" token and never decomposes it — so a search for "invoice" would never match a real uploaded filename. Fixed by stripping non-alphanumeric characters to spaces before tokenizing: `to_tsvector('english', regexp_replace(file_name, '[^a-zA-Z0-9]+', ' ', 'g'))`, verified live to correctly decompose `'invoice-march.pdf'` → `'invoic'`/`'march'`/`'pdf'`. Documented inline in the migration and the model, per `remediation-plan.md` §11.1's "R8 picks one and documents the choice" instruction — treated as an implementation/schema-expression decision (same weight as the HNSW operator-class choice, which is likewise documented inline rather than as a numbered ADR), not a new architectural pattern warranting a `decisions.md` entry.

### AI observability — the query-embedding call, not a new pattern
Search makes exactly one provider call (embedding the query text) and no LLM call — there is no LangGraph workflow here (`CLAUDE.md` §5's "unnecessary LLM calls" guard: search is one provider call plus a database query, not a stateful multi-step workflow). `SearchService._embed_query_with_observability` mirrors `document_processing_service.py`'s `_embed_with_observability` exactly (`operation="embedding"`, real `input_tokens` via `count_tokens(query)`, `output_tokens=None`, success and failure both logged, a logging failure never affects the search's own outcome) — the same interpretation of `NFR-OBS-001` already established for R3, applied to a second embedding call site rather than reinvented.

### Snippet/highlight construction — offset-based, never markup
`api.md` §8's `SearchSnippet` (`{text, highlights: [{start, end}]}`) was already fixed by the frontend team (Phase 13) specifically to avoid the API ever returning pre-built HTML for untrusted document content. `search_service.build_snippet()` centers a ~160-character excerpt on the first query-term match (case-insensitive, word-tokenized) and computes highlight offsets *into that excerpt*, never into the full content — verified with a live test asserting a chunk containing literal `<script>` text round-trips as plain text, unescaped and untransformed by the backend (escaping/rendering safety is the frontend's job, per the existing Phase 13 design).

### Filename matches have no page
A row produced by a filename-only match (no corresponding `document_chunks` row) has `matched_page: null` and a `snippet.text` equal to the filename itself — `rag.md` §12's "`documents.file_name` for filename matches" — consistent with `api.md` §8's "one row per matching chunk" language extended to the one case where the match isn't a chunk at all.

### No implicit `status='ready'` restriction
Unlike chat retrieval (which implicitly requires `ready`, `rag.md` §7 point 4), Global Search applies `status` only when the caller supplies it as a filter (`FR-SEARCH-002`). A `queued`/`processing` document naturally has no chunks yet, so it can only surface via a filename match — deliberate, so a user can find a just-uploaded file by name before processing completes.

## Tests
- **`test_search_repository.py`** (new, 10 tests) — exact keyword match via content; filename match with `page_number=None`; cross-tenant scoping (`NFR-SEC-001`); soft-deleted documents excluded; no-match returns empty; `mime_type`/`status`/`tag_id`/`date_from` filters each narrow correctly; pagination is deterministic across repeated calls with disjoint pages.
- **`test_search_api.py`** (new, 10 tests) — exact documented response shape (including highlight offsets slicing back to the matched term); `401` unauthenticated; `422` empty `q`; `422` `date_from > date_to`; empty-results shape; cross-tenant isolation at the HTTP layer; filter narrowing; pagination envelope; exactly one `ai_requests` row (`operation="embedding"`, `status="success"`, real `input_tokens`) per search call; snippet text is never HTML-escaped or transformed server-side.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.10:
- `FR-SEARCH-001`: Given a query, when submitted, then results include matching documents ranked by relevance with highlighted snippets, scoped strictly to the requesting user. — Verified by `test_search_api.py::test_search_returns_the_exact_documented_shape` and `test_search_never_returns_another_users_documents`.
- `FR-SEARCH-002`: Search results can be filtered by document type, tag, date range, and processing status. — Verified by the four filter tests in both test files.
- `FR-SEARCH-003`: Search combines full-text (`tsvector`) and vector similarity. — Verified by `test_search_repository.py::test_search_finds_exact_keyword_match_via_content` (full-text signal) and the repository's RRF fusion logic (vector signal contributes via `VECTOR_MIN_SIMILARITY`-gated candidates); both defects found while verifying this against live Postgres are documented above, not silently left broken.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted — both real defects found during verification (vector relevance floor, filename tokenization) are documented above with their fixes, not silently patched
- [x] `specs/database.md` updated — the one spec change this task required (§11.1), with rationale
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **Snippet excerpt windowing does not respect word boundaries** — a ~160-character crop can begin/end mid-word. `api.md` §8 doesn't require word-boundary trimming, and the frontend doesn't render an ellipsis marker, so this was treated as acceptable for MVP rather than added complexity.
- **`VECTOR_MIN_SIMILARITY = 0.75` and `CANDIDATE_POOL = 50` are not yet empirically tuned** against a real corpus/query distribution — `skills/database.md` §2 explicitly flags `ef_search`-style tuning as "not a value to guess at implementation time... tune it empirically against `performance.md`'s budgets once real corpus/query patterns exist." Same caveat applies here; both are the same order-of-magnitude defaults `retrieval_service.py` already uses, not arbitrary.
- **No result-count cap per document** — a document with many matching chunks can occupy many rows of one page; `api.md` §8 explicitly assigns this grouping to the client (`ui-ux.md` §12, already built in Phase 13), so this is by design, not an oversight.
- **The pre-existing `alembic check` drift** (missing `CheckConstraint`/HNSW-index declarations across several models, present on `main` before this task) is unrelated to R8 and was not touched — confirmed by running `alembic check` against `main` before this task's changes and observing the identical drift.

## Verification Results
- **Targeted test files:** `test_search_repository.py` (10), `test_search_api.py` (10) — 20 total, all passed on first run after two real defects (found via live-Postgres verification, not assumed) were fixed: the vector relevance floor and the filename-tokenization expression, both documented above.
- **Full backend suite:** 460 passed, 0 failed (440 pre-existing + 20 new) — run three times, identical pass count each time (~33–40s per run).
- **Ruff:** clean (one initial `DTZ011` finding in a new test file, fixed by using `datetime.now(UTC).date()` instead of `date.today()`, matching the codebase's existing convention elsewhere).
- **Black:** clean.
- **Mypy:** clean (one initial finding — a CTE/Select type-narrowing false-positive from reassigning one variable across an incompatible SQLAlchemy Core type; fixed by using a distinct variable name for the pre-CTE `Select`, no `# type: ignore` needed).
- **Migrations:** one added (`0004_search_tsvector`), applied cleanly (`alembic upgrade head`) and downgraded/re-upgraded once during development to correct the filename-tokenization expression before this report. `alembic check` shows only the pre-existing, unrelated drift already present on `main` (confirmed by running it against `main` before this task's changes).
- **Live smoke test:** real Postgres (Docker), the real FastAPI app (ASGI transport, no dependency overrides for CSRF/rate-limiting). Covered: a real search returning `200` with the exact documented shape and correct highlight offsets; `422` for an empty `q` with the correct `fields` envelope; `401` for an unauthenticated request.
- **Tenant isolation:** verified by both the automated test suite (repository- and API-level) and direct code review — every filter is applied to `filtered_documents`, which is scoped by `user_id` before either ranking method runs.
- **AI observability:** verified — `test_search_logs_one_ai_requests_row_for_the_embedding_call` asserts exactly one `ai_requests` row (`operation="embedding"`, `status="success"`, real `input_tokens`) per search call.
- **Scope check:** `git status` shows exactly the files listed above as modified/new — no R1–R7 behavior changed, no R9+ code, no frontend files touched (the existing Phase 13 frontend's `lib/api/search.ts` contract was matched exactly, not modified), no unrelated spec changes, no commit made, no deployment performed.
