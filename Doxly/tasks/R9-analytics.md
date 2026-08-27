# Task R9: Analytics

## Task ID
R9-001

## Feature
Personal Usage Dashboard — `GET /analytics/dashboard`: read-only aggregate stats (documents processed over time, AI requests over time, storage used, most-used features) computed at query time from `documents` and `ai_requests`, no dedicated analytics table.

## Objective
Closes the gap `tasks/remediation-plan.md` §12 (R9) identifies: no analytics repository, service, or router existed. This task adds them, reusing R2's `documents` table and R4–R7's `ai_requests` volume exactly as those tasks left them — no schema change, no new AI/provider call, purely aggregation over already-persisted data.

## Specification References
- `tasks/remediation-plan.md` §12 (R9) — authoritative scope for this task, including §12.1's mandatory dedicated cross-tenant suite.
- `specs/requirements.md` §1.11 (`FR-ANALYTICS-001..002`).
- `specs/api.md` §9 (`/analytics`) — `GET /analytics/dashboard`'s exact response shape; `GET /analytics/documents/{id}` (`FR-ANALYTICS-002`, P2) is explicitly out of scope for R9 per the remediation plan's endpoint list.
- `specs/database.md` §6 traceability — "computed at query time... no dedicated analytics table for MVP."
- `specs/testing.md` §3.5 — the mandatory cross-tenant test category, sharpened for aggregate queries specifically by remediation-plan.md §12.1.
- `specs/observability.md` — not applicable to this task's own code (R9 makes no LLM/embedding calls; it only reads already-logged `ai_requests` rows other tasks wrote).

## Requirements
- `FR-ANALYTICS-001` (P1) — a user sees: documents processed over time, storage used, AI requests made, most-used features.
- `NFR-SEC-001` (P0, carried) — every aggregate query scoped to `user_id`; `remediation-plan.md` §12.1's explicit concern (a `COUNT(*)` missing its `WHERE user_id` clause silently including every user's rows).

## Dependencies
- R2 (Document Management) — `documents` rows to aggregate.
- R4/R5/R6/R7 (Chat/Extraction/Comparison/Summarization) — real `ai_requests` volume to aggregate.
- R8 (Search) — sequencing only, no code dependency (confirmed unchanged by this task).

## Files Affected
- `backend/app/repositories/analytics_repository.py` — **new** — `AnalyticsRepository`: `documents_processed_by_day`, `ai_requests_by_day`, `most_used_features`, all `user_id`-scoped. Deliberately not a `TenantScopedRepository` subclass (same reasoning as R8's `SearchRepository` — cross-table aggregates, not single-model CRUD).
- `backend/app/schemas/analytics.py` — **new** — `TimeSeriesPoint`/`FeatureUsage`/`AnalyticsDashboardResponse`, matching `api.md` §9 and the already-built frontend contract (`frontend/lib/api/analytics.ts`) exactly.
- `backend/app/services/analytics_service.py` — **new** — `AnalyticsService.get_dashboard`: resolves the period to a rolling window, calls the repository, zero-fills the day-series, reads `users.storage_used_bytes` directly (the existing denormalized counter, not recomputed).
- `backend/app/api/v1/routers/analytics.py` — **new** — `GET /analytics/dashboard`, general rate-limit tier only (`GET`-only, no CSRF).
- `backend/app/main.py` — modified — mounts the new router (2 lines).
- Tests — new: `test_analytics_repository.py` (9 tests), `test_analytics_api.py` (11 tests, including the §12.1 dedicated cross-tenant suite).

No migration — `database.md` §6 traceability and `api.md` §9 both state this explicitly; confirmed no schema change was needed by inspection, not assumed.

## Implementation Notes

### Three spec-gap resolutions, decided and documented rather than silently picked
1. **"Most-used features" excludes the `embedding` operation.** `ai_requests.operation` has five values (`chat`/`summarization`/`extraction`/`comparison`/`embedding`), but `embedding` is an internal implementation detail fired by chat retrieval, document processing, and R8's search — never a feature a user chose to invoke in its own right. Counting it would make every real feature look artificially rare (an embedding call happens on nearly every document upload and every search query). `FEATURE_OPERATIONS` restricts the aggregation to the four user-facing operations.
2. **"Documents processed" means `status='ready'`, not merely uploaded.** The requirement's plain text ("documents processed over time") is read as the meaningful business metric — successfully completed the pipeline — not an upload/attempt count. `documents_processed_by_day` filters `status='ready'` explicitly.
3. **`storage_used_bytes` is the current total, not period-filtered.** Storage is a snapshot, not something that "happened" within a window — recomputing it per period would be both nonsensical (what does "storage used in the last 7 days" mean for a persistent total?) and wasteful (`users.storage_used_bytes` is already a transactionally-maintained denormalized counter, per `database.md` §3.1's own note, reused directly rather than re-summed from `documents`).

### `period` is a rolling window, not a calendar bucket
`since = now - N days`, matching `AiRequestRepository.count_since`'s existing "since" semantic elsewhere in the codebase (R1's usage endpoint) rather than inventing a calendar-aligned scheme. `documents_over_time`/`ai_requests_over_time` zero-fill every day in `[since.date(), today]` inclusive so a chart consuming the response never sees a misleading gap between two non-adjacent data points.

### A real bug caught by mypy before it shipped
Labeling an aggregate column `"count"` and reading it back as `row.count` would have silently returned SQLAlchemy `Row`'s inherited `tuple.count` **method** at runtime, not the integer — Python attribute lookup finds the real inherited method before `Row`'s label-based `__getattr__` fallback ever runs. Caught by `mypy` (`Argument "count" ... has incompatible type "Callable[[Any], int]"`), not by manual review; fixed by renaming the label to `"total"` throughout `analytics_repository.py`.

## Tests
- **`test_analytics_repository.py`** (new, 9 tests) — `documents_processed_by_day` counts only `ready` documents, excludes soft-deleted rows, excludes documents outside the window, is user-scoped; `ai_requests_by_day` groups same-day calls and is user-scoped; `most_used_features` excludes `embedding`, orders by count descending, is user-scoped.
- **`test_analytics_api.py`** (new, 11 tests) — exact documented response shape; default `30d` period (31-day zero-filled series); `7d`/`90d` periods (8/91-day series); `422` for an invalid period; `401` unauthenticated; a brand-new user's all-zero dashboard shape; **the `remediation-plan.md` §12.1 dedicated cross-tenant suite**: document counts scoped to the caller (seeded 5 documents for another user), storage scoped to the caller (another user's 999,999,999-byte counter never leaks), AI request volume and `most_used_features` scoped to the caller, isolation holding under every supported period filter (not just the unfiltered default), `most_used_features` never aggregating across the full user base.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.11:
- `FR-ANALYTICS-001`: A user sees stats — documents processed over time, storage used, AI requests made, most-used features. — Verified by `test_analytics_api.py::test_dashboard_returns_the_exact_documented_shape` and the live smoke test.

## Definition of Done
- [x] Code implements the Objective and satisfies the Acceptance Criteria above
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted — all three spec-gap resolutions above are documented, not silently picked
- [x] No spec file update needed — `database.md` §6 already correctly stated "no dedicated analytics table for MVP" before this task; nothing to reconcile
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **`GET /analytics/documents/{id}` (`FR-ANALYTICS-002`, P2) is not implemented** — explicitly out of scope for R9 per `remediation-plan.md`'s own endpoint list; tracked separately, does not block R9's Definition of Done.
- **No caching** — every dashboard load re-runs the aggregate queries live. `performance.md` was not consulted for a specific budget on this endpoint during this task; if dashboard latency becomes a real concern against a large `ai_requests`/`documents` table, that's a follow-up performance task, not a functional gap.
- **Day-series zero-fill is computed in Python, not SQL** (`generate_series`) — simpler and adequate at MVP's per-user row counts; would need revisiting only if per-user history grows large enough for the Python loop itself to matter, which is far outside the current 7/30/90-day windows this endpoint serves.

## Verification Results
- **Targeted test files:** `test_analytics_repository.py` (9), `test_analytics_api.py` (11) — 20 total, all passed on first run after one real bug (the `row.count`/`tuple.count` collision, caught by mypy) was fixed before any test ran against it.
- **Full backend suite:** 480 passed, 0 failed (460 pre-existing + 20 new) — run three times, identical pass count each time (~31–38s per run).
- **Ruff:** clean (one initial `F401` unused-import finding in a new test file, fixed).
- **Black:** clean.
- **Mypy:** clean (one initial finding — the `row.count`/`tuple.count` label collision described above — fixed by renaming the SQL label to `"total"`, no `# type: ignore` needed).
- **Migrations:** none added — confirmed by inspection that no schema change was needed (`database.md` §6 traceability already stated this), and by `git status` showing no new file under `alembic/versions/`.
- **Live smoke test:** real Postgres (Docker), the real FastAPI app (ASGI transport, no dependency overrides for CSRF/rate-limiting). Covered: a real dashboard load returning `200` with the exact documented shape and a correctly zero-filled 31-day series; `422` for an invalid `period` with the correct `fields` envelope; `401` for an unauthenticated request.
- **Tenant isolation:** verified by both the automated test suite (repository- and API-level, including the §12.1 dedicated suite) and direct code review — every repository method takes `user_id` as its first parameter and filters on it directly, matching `skills/database.md` §10's checklist.
- **AI observability:** not applicable — R9 makes no LLM/embedding provider calls of its own; it only reads `ai_requests` rows other tasks already wrote and log. Confirmed explicitly rather than left unaddressed.
- **Scope check:** `git status` shows exactly the files listed above as modified/new — no R1–R8 behavior changed (R8/Search files untouched), no R10+ code, no frontend files touched (the existing Phase 14 frontend's `lib/api/analytics.ts` contract was matched exactly, not modified), no spec/roadmap changes, no migration added, no commit made, no deployment performed.
