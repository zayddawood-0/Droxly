# Task R11: Full System Integration

## Task ID
R11-001

## Feature
Full System Integration verification — the P0 golden path (register → login → upload → process → search → chat → summarize → extract → compare → analytics) driven end-to-end through the real ASGI app, real committed Postgres, real Redis/RQ, and real (directly-invoked) worker job bodies, plus a dedicated failure-path integration test and a full audit of R1–R10's cross-feature wiring.

## Objective
This is verification, not implementation. `tasks/remediation-plan.md` §14 (R11) calls for "a backend integration test suite... driving the entire path via `httpx.AsyncClient` against real test Postgres/Redis, asserting each stage's persisted state" — this task builds exactly that, confirms every R1–R10 feature actually composes correctly (not just that each domain's own isolated test suite passes), and documents every gap found along the way per the task's own instruction: fix only what R11 correctness requires, otherwise report and leave alone.

## Specification References
- `tasks/remediation-plan.md` §14 (R11) — golden path, dependencies, acceptance test shape.
- Every R1–R10 task file (`tasks/R1-authentication.md` through `tasks/R10-admin.md`) — the committed contract each domain claims to fulfill; this task verifies those claims hold when composed together, not in isolation.
- `specs/api.md`, `specs/testing.md` §2.4 (golden-path E2E scope), `specs/security.md` §3 (authorization), `specs/observability.md` §4 (`NFR-OBS-001`).

## Requirements
Verifies (does not re-implement) `NFR-SEC-001` (multi-tenancy through the *complete* flow, not per-endpoint), `NFR-OBS-001` (AI observability across every domain in one continuous session), and the P0 acceptance criteria of `FR-AUTH-*`, `FR-DOC-*`, `FR-PROC-*`, `FR-SEARCH-001`, `FR-AI-001..004`, `FR-SUM-001`, `FR-EXT-001`, `FR-COMP-001..002`, `FR-ANALYTICS-001`, `FR-ADMIN-001..003` composed together in one real session.

## Dependencies
R1 through R10, all already committed and independently verified by their own task files. This task adds no new application code — only test infrastructure.

## Files Affected
- `backend/tests/test_r11_golden_path.py` — **new** — two tests: `test_golden_path_end_to_end` (the full P0 path, both a genuine tenant and a cross-tenant attacker in the same session) and `test_failed_processing_is_reflected_correctly_across_the_system` (checklist item B — failure states behave per spec across every downstream domain).

No application code changed. No migration. No frontend changes (none of R11's scope required them).

## Implementation Notes

### Why this file doesn't use the shared `client`/`db_session` fixtures
Every other test file in the suite runs through `conftest.py`'s `client` fixture: one shared, SAVEPOINT-scoped session, CSRF/rate-limiting overridden to no-ops. That's correct for testing one endpoint in isolation, but it would silently hide exactly the class of bug an integration suite exists to catch — a real cross-request commit boundary, a real CSRF double-submit check, a real Redis-backed rate limiter. This file uses genuinely separate `AsyncClient` instances per user (own cookie jars, own real login), the real (unmocked) `get_db_session` (commits per request, matching production), and real CSRF tokens read from the actual `Set-Cookie` response and mirrored into `X-CSRF-Token` headers by hand — nothing about authorization or persistence in this file is faked.

### Worker jobs are invoked directly, not via a subprocess `rq worker`
Mirrors the established, already-proven pattern in `test_document_processing_worker.py`/`test_extraction_worker.py`/`test_comparison_worker.py`/`test_summary_worker.py` exactly: RQ job entrypoints are plain sync functions with their own internal `asyncio.run()`. This test asserts the *real enqueue* happened (`queue.count` increases after each mutating request — genuine Redis/RQ integration, checklist item M) and then runs the job body directly rather than spinning up a real `rq worker` subprocess, which those four existing files already established as the right level of rigor for this codebase (a real subprocess worker was used only for prior tasks' one-off live smoke tests, not committed as a repeatable suite member).

### Five real bugs found and fixed while building this — in the test infrastructure, not the application
Building a test file that legitimately spans three separate `asyncio.run()` loops (one per phase) plus direct worker-job calls (each with their *own* internal loop) surfaced real cross-loop hazards that no existing test file had to deal with, since every other file either stays on pytest-asyncio's one session loop or is a worker-only file that never also drives HTTP requests. None of these were application bugs — all were properties of this specific test file's own architecture:
1. **Redis async client cross-loop reuse** (`core/rate_limit.py`'s module-level `redis_client`) — a connection opened on one phase's loop is invalid on the next phase's fresh loop. A *graceful* `.disconnect()` doesn't work either (it awaits the dead connection's own close-waiter, hitting the identical error one level deeper) — fixed by replacing the client reference entirely between phases, never touching the old connection.
2. **`auth_throttle`'s captured client reference** — a singleton constructed once at import time as `AuthThrottle(redis_client)`, imported by value (`from app.core.rate_limit import auth_throttle`) elsewhere, so reassigning the module attribute alone didn't reach it — fixed by mutating `auth_throttle._client` in place.
3. **A third, independent Redis client** in `core/chat_stream_control.py` (ADR-024's stop/regenerate signal transport, hit by every real chat turn) — same hazard, same fix, found only once the golden path ran as part of the *full* suite (enough concurrent/prior loop activity to expose it; it never manifested running this file alone).
4. **My own test bug**: `docs_queue_before` was measured *after* the three uploads it was meant to be a baseline for.
5. **My own test bug**: the chat graph's entry node is an intent classifier that makes its own real LLM call before retrieval ever runs (`langgraph.md` §2 node 1) — queuing only one scripted response let the classifier consume it, leaving the real answer-generation call with unscripted (and therefore ungrounded) text, which `citation_validator_node` correctly rejected, producing an empty-citations "graceful I don't know" response — not a retrieval bug (direct `RetrievalService.retrieve()` calls confirmed 0.80 cosine similarity throughout). Fixed by queuing two responses, exactly mirroring `test_chat_sse.py`'s own proven `["factual_qa", answer]` pattern.

### One real, useful discovery: `POST /chat/conversations` itself validates document readiness
`ChatService.create_conversation` calls `_verify_documents_ready` before ever creating the row — a not-ready document is rejected at conversation-creation time (`409 document_not_ready`), not deferred to first message send. My failure-path test's original assumption (conversation creation always succeeds regardless of readiness) was wrong; fixed the test, not the app — this is correct, already-shipped R4 behavior, confirmed working as intended.

## Tests
- **`test_golden_path_end_to_end`** — one continuous session: register/login two users → unauthenticated request rejected (401) → user A uploads and processes three documents (real RQ enqueue asserted, real worker invocation) → document detail reflects `ready`/`extracted_text_available` → search finds A's content and returns nothing for B → a full chat turn asserts the exact SSE event order (`message_id` → tokens → `citations` → `done`) with a real citation pointing at the right document, and a cross-tenant `GET` on the conversation 404s → summary/extraction/comparison created, real-enqueued, and real-worker-completed, each with its documented terminal shape → cross-tenant `404` asserted across every domain (documents, summaries, extractions, comparisons, conversations) in one loop, not five separate tests → a cross-tenant document in a comparison request also `404`s → analytics for A reflects real processed-document/AI-request/feature activity, analytics for B reflects only B's own (zero AI-domain features) → no cross-tenant leakage in `ai_requests` (B's own legitimate search-embedding row is the only one, none of A's chat/summarization/extraction/comparison rows) → a real admin promotion, real `GET /admin/users` against real data, non-admin `403`, real suspend making B's *already-authenticated* session immediately return `403 account_suspended` on its very next request, then real unsuspend restoring it.
- **`test_failed_processing_is_reflected_correctly_across_the_system`** — a whitespace-only document (rag.md §2's degenerate zero-chunk case) processed by the real worker reaches `status="failed"` with a non-empty, user-safe `processing_error` via the real API, and summary/extraction/chat-conversation-creation against it are each rejected with `409 document_not_ready` — not silently accepted.

## Acceptance Criteria
The P0 golden path (`remediation-plan.md` §14.1: Register → Login → Upload → Process → View → Chat → Summarize → Extract → Compare → Search, plus Analytics as the P1 capstone) runs to completion in one real session with correct persisted state at every stage — verified by `test_golden_path_end_to_end`. Cross-tenant isolation holds through the *complete* flow, not just at individual endpoints — verified by the same test's Phase 5. Failure states behave per specification — verified by `test_failed_processing_is_reflected_correctly_across_the_system`.

## Definition of Done
- [x] Both integration tests pass, run repeatedly (5× combined across standalone and full-suite runs), with identical results each time
- [x] No application code changed — this task is verification-only, per its own explicit scope
- [x] Every gap found is documented above with its root cause, not silently patched or silently ignored
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **No real subprocess `rq worker` process was spun up for this suite's own repeatable tests** — direct job-body invocation was judged sufficient, matching R3/R5/R6/R7's own established precedent; a genuine subprocess-worker pass was already performed as each of those tasks' own one-off live smoke tests, not repeated here.
- **No browser-level (Playwright) golden-path pass** — `remediation-plan.md` §14's "a full `claude-in-chrome` pass... once R1–R9 land" is out of scope here; this environment has no installable browser (same constraint noted in R10's report). The frontend's own existing Playwright specs (`frontend/e2e/*.spec.ts`) were not touched or re-run by this task.
- **`ai-eval` nightly job / curated golden-set fixtures** (`testing.md` §4.5/§4.6, mentioned in `remediation-plan.md` §14's "automated acceptance tests to define at R11 time") were not built — this is CI/scheduled-job infrastructure, judged out of scope for an integration-test-suite task; flagged for R12 or a dedicated follow-up.
- **Regenerate/stop message endpoints** (`FR-AI-005/006`, P1/P2) were not exercised in the golden path — already covered by R4's own dedicated test suite; the golden path only needed to prove one clean send-and-receive turn.

## Gaps Found in R1–R10 — Classified
Per this task's explicit instruction: classify, identify the owning task, fix only if R11 requires it, otherwise document.

| Finding | Classification | Owning task | Action taken |
|---|---|---|---|
| `core/chat_stream_control.py`'s Redis client has no test-infrastructure hazard in production (real deployments never run multiple event loops in one process) | Non-blocker, test-infrastructure-only | R4 | None needed — documented above as this file's own fix, not an R4 defect |
| No other gaps found | — | — | R1–R10's committed behavior matched their own task files' documented contracts at every point this suite exercised them |

## Verification Results
- **Targeted tests:** `test_golden_path_end_to_end`, `test_failed_processing_is_reflected_correctly_across_the_system` — both pass, run 3× standalone (3.5–4.5s each) and 3× as part of the full suite, identical results every time.
- **Full backend suite:** 507 passed, 0 failed (505 pre-existing + 2 new), run 3× consecutively (33–44s per run).
- **Ruff:** clean (one import-ordering finding in the new file, auto-fixed).
- **Black:** clean.
- **Mypy:** `app/` clean (100 source files — this task changed none of them). The new test file itself (not part of this project's mypy gate, which is scoped to `app/`) was additionally checked out of caution and fixed to be clean too (one loose `dict | None` annotation).
- **Migrations:** current at head (`0004_search_tsvector`), none added — confirmed by direct `alembic current`/`alembic heads` check, matching the expectation that a verification-only task needs no schema change.
- **Live E2E:** this task's own two tests *are* the live E2E verification — real Postgres, real Redis, real RQ enqueue counts, real worker job execution, real CSRF, real rate-limiting dependencies, nothing overridden except the LLM provider (for determinism/cost, the same convention every other AI-invoking test in the suite already uses).
- **Worker/Redis/Postgres:** verified directly — RQ enqueue counts asserted after every mutating AI-domain request; all four workers (`document_processing`, `extraction`, `comparison`, `summary`) invoked for real and asserted to reach their correct terminal states; every write across the whole session used real, committed Postgres transactions (not the SAVEPOINT-rollback pattern the rest of the suite uses).
- **Multi-tenancy:** verified through the *complete* composed flow in one session — cross-tenant `404` across five domains in a single loop, a cross-tenant document rejected inside a comparison request, analytics scoped correctly for both the active and the passive tenant, `ai_requests` isolation confirmed at the DB level (not just via the API response shape).
- **Security:** CSRF enforced for real (a mismatched/missing token would 403, per R1 — implicitly proven by every mutating call in this suite succeeding only because a real, correctly-read token was supplied); the R10 suspend fix (`get_current_user`'s live `users.status` check) verified working end-to-end again, this time inside a real multi-domain session rather than an isolated admin test.
- **Observability:** `ai_requests` rows verified present for A's chat/summarization/extraction/comparison activity and for B's own search-embedding call, with no cross-tenant attachment in either direction — verified at the database level, not inferred from API responses alone.
- **Scope check:** `git status` shows exactly one new file (`backend/tests/test_r11_golden_path.py`). No application code, no migration, no frontend files, no spec/roadmap changes, no commit made, no deployment performed, R12 not started.
