# Task R10: Admin Integration

## Task ID
R10-001

## Feature
Admin Integration — `GET /admin/users`, `GET /admin/system/health`, `POST /admin/users/{id}/suspend`, `POST /admin/users/{id}/unsuspend`, plus the frontend wiring that makes the existing `(admin)/admin/*` pages real (they were static placeholders with zero API calls before this task).

## Objective
Closes the gap `tasks/remediation-plan.md` §13 (R10) identifies: `require_admin` existed since R1 with no consumer, and no admin router/service/repository or frontend client existed. This task builds the full backend chain, reuses R1's session-revocation infrastructure directly, and — per this task's explicit scope decision (see below) — wires the frontend admin pages to real data for the first time in this remediation sequence.

## Specification References
- `tasks/remediation-plan.md` §13 (R10) — authoritative scope for this task.
- `specs/requirements.md` §1.14 (`FR-ADMIN-001..003`).
- `specs/api.md` §12 (`/admin`) — full endpoint contracts; §0.4's "403 is the one deliberate exception to 404-not-403" rule, restated at §12's own top.
- `specs/security.md` §3.1 (role model, "admin is never a tenant-ownership bypass").
- `specs/database.md` §3.1 (`users.status`), §3.2 (`refresh_tokens`), §3.14 (`audit_logs`).
- `specs/ui-ux.md` §15 (Admin) — layout, components, and interaction spec for the frontend half.
- `specs/testing.md` §3.5 (cross-tenant/authorization).

## Requirements
- `FR-ADMIN-001` (P1) — admin user directory; account/operational metadata only, never document/chat/extraction content.
- `FR-ADMIN-002` (P1) — system health: queue depth, processing failure rate, AI request volume (24h rolling).
- `FR-ADMIN-003` (P1) — suspend/unsuspend, immediately revoking all sessions, never touching the user's own data.
- `NFR-SEC-001` (P0, carried) — every admin route gated by `require_admin`; the one legitimate cross-user query surface in the codebase, explicitly bounded to admin routes only.
- `NFR-PRIV-004` — no admin route ever returns document/chat/extraction content.

## Dependencies
- R1 (`require_admin`, `RefreshTokenRepository.revoke_all_for_user`) — both built in R1 with no consumer until this task, reused directly, unmodified.
- R3/R5/R6/R7 (the four RQ queues) — `queue_depth` sums all of them.

## A genuine compatibility fix to R1 shared infrastructure — confirmed with the user before implementing, not silently done

**`FR-ADMIN-003`'s "immediately revoking all sessions" clause cannot be satisfied by revoking refresh tokens alone.** Access tokens are short-lived (~15 min) but stateless JWTs — `get_current_user` (`core/dependencies.py`) only verified the JWT signature, never queried `users.status`. Revoking refresh tokens blocks *re-authentication*, but a suspended user's already-issued access token would keep working for up to 15 more minutes, silently under-implementing the requirement's own explicit wording (`remediation-plan.md` §13 flags this exact trap by name: "easy to under-implement as 'block future logins only'").

This is a change to R1's most shared dependency — every authenticated route in the app now does one extra `users` lookup per request. Given the magnitude, **this was surfaced to the user as an explicit architectural decision before implementing**, not assumed: the user chose to add the DB status check (over the alternative of accepting refresh-token-only revocation as a documented limitation).

**What changed:** `get_current_user` now looks up the caller's `User` row and raises `AccountSuspendedError` (403, existing error class, already used at login/refresh — this extends the identical check to every request) if `status == "suspended"`, or `UnauthorizedError` (401) if the row no longer exists. `auth_service.py` already had this exact check at login and refresh; this closes the one gap where it was missing.

**Two pre-existing tests broke as a direct, necessary consequence** (fixed, not worked around):
- `tests/test_require_admin.py` — its probe app minted JWTs for synthetic `uuid4()` ids with no backing `users` row. Fixed by giving the probe app a real DB-backed session (mirroring `conftest.py`'s own `client` fixture) and real `User` rows.
- `tests/test_validation_errors.py::test_users_me_patch_empty_display_name_returns_envelope` — used a bare `uuid4()` as the authenticated caller, unrelated to what the test actually verifies (the 422 envelope shape). Fixed by creating a real user via `make_user(db_session)`.

Both fixes are scoped exactly to what the `get_current_user` change requires — no other R1–R9 behavior was touched.

## Files Affected
**Backend — shared infrastructure (the compatibility fix above):**
- `backend/app/core/dependencies.py` — modified — `get_current_user` gains a DB dependency and a live `users.status` check.
- `backend/app/errors.py` — modified — added `NotSuspendedError` (409, `not_suspended`).
- `backend/app/repositories/user_repository.py` — modified — added `UserRepository.list_paginated` (the one deliberate cross-user query, `FR-ADMIN-001`).
- `backend/tests/test_require_admin.py`, `backend/tests/test_validation_errors.py` — modified — compatibility fixes described above.

**Backend — R10 itself:**
- `backend/app/repositories/admin_repository.py` — **new** — `AdminRepository`: `processing_failure_rate_24h`, `ai_requests_24h`, `ai_error_rate_24h`. Deliberately not added to `DocumentRepository`/`AiRequestRepository` (both are contractually always `user_id`-scoped) and deliberately not a `TenantScopedRepository` — a dedicated, distinctly-named home for the one legitimate system-wide aggregate.
- `backend/app/schemas/admin.py` — **new**.
- `backend/app/services/admin_service.py` — **new** — composes `UserRepository`, `RefreshTokenRepository`, `AuditLogRepository`, `AdminRepository`; queue depth summed from `core/queue.py`'s four existing queue getters.
- `backend/app/api/v1/routers/admin.py` — **new** — every route declares `require_admin`; mutating routes also declare `verify_csrf`.
- `backend/app/main.py` — modified — mounts the new router.
- Tests — new: `test_admin_repository.py` (9 tests), `test_admin_api.py` (16 tests).

**Frontend (this task's explicit scope decision — see below):**
- `frontend/lib/api/admin.ts` — **new**.
- `frontend/hooks/use-admin.ts` — **new**.
- `frontend/components/domain/admin/suspend-dialog.tsx`, `admin-user-table.tsx` — **new**.
- `frontend/app/(admin)/admin/users/users-view.tsx`, `frontend/app/(admin)/admin/system/system-view.tsx` — **new**.
- `frontend/app/(admin)/admin/users/page.tsx`, `frontend/app/(admin)/admin/system/page.tsx` — modified — wired to the new views (were `PhasePlaceholder`).

## Implementation Notes

### Frontend scope — an explicit decision, not silent expansion
Every prior R-task this session was backend-only. R10 is structurally different: `remediation-plan.md` §13 itself scopes frontend work into R10 (`frontend/lib/api/admin.ts` didn't exist; the `(admin)/admin/*` pages had zero API calls). This was surfaced to the user as an explicit choice before any code was written — the user chose full scope per the remediation plan over a backend-only pass.

### `AdminRepository` — deliberately outside the tenant-scoping contract
`skills/database.md` §10's checklist ("every method takes `user_id` as its first parameter") is the load-bearing invariant for `DocumentRepository`/`AiRequestRepository`. Rather than add an unscoped exception method to either (which would make that checklist unreliable-by-inspection for everything else in those classes), the three system-wide aggregates live in a new, distinctly-named `AdminRepository` whose entire purpose is documented as the one legitimate cross-tenant query surface, reached only through `require_admin`.

### Email search on the admin user directory — a documented spec-consistency gap, resolved the same way `DocumentsView` already resolves it
`ui-ux.md` §15 says "search/filter user directory by email/status," but `api.md` §12 defines no server-side email query param (`limit`/`offset`/`status`/`plan` only) — treated as a `ui-ux.md`/`api.md` inconsistency, not license to invent a new backend contract. Resolved identically to how `DocumentsView` already handles its own filename search (verified by reading `documents-view.tsx` directly): the email search box filters the currently-loaded page client-side; `status`/`plan` (the real, spec-backed params) narrow the actual server-side query. Not a new pattern — the existing one, reused.

### `processing_failure_rate_24h` does not exclude soft-deleted documents
A document's processing outcome is an operational fact about the pipeline, independent of whether the user later deleted it — deliberate, not an oversight.

### No migration
`users.status`, `refresh_tokens`, and `audit_logs` all already existed with everything this task needed (`database.md` §3.1/§3.2/§3.14) — confirmed by inspection before writing any repository code, not assumed.

## Tests
- **`test_admin_repository.py`** (new, 9 tests) — `UserRepository.list_paginated` returns across the whole base and filters by status/plan; `AdminRepository`'s three aggregates compute correctly, respect the 24h window, and return `0.0`/`0` with no data.
- **`test_admin_api.py`** (new, 16 tests) — non-admin gets `403` on every admin route (dedicated loop over all four); unauthenticated gets `401` not `403`; admin succeeds on every route; exact response shapes for both `GET` routes; `NFR-PRIV-004`'s "never document content" assertion (a document's filename/storage key never appear in the user-directory response); status filter; suspend's exact shape + DB state + refresh-token revocation + audit log row + `404` for an unknown id; **the FR-ADMIN-003 cross-role test**: a target's own already-issued session is rejected on its very next request after being suspended, not merely at next login; unsuspend's exact shape + restored access + audit log row + `404`/`409 not_suspended`.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.14:
- `FR-ADMIN-001`: Given an admin session, when viewing the admin user list, then no document content, chat content, or extracted field values are visible — only account/operational metadata. — Verified by `test_list_users_never_returns_document_content`.
- `FR-ADMIN-002`: An admin can see aggregate processing queue depth, failure rates, and AI request volume. — Verified by `test_system_health_returns_the_exact_documented_shape` and the live smoke test.
- `FR-ADMIN-003`: An admin can suspend an account, immediately revoking all sessions and blocking login, without deleting data. — Verified by `test_suspend_user_immediately_invalidates_the_targets_current_session` (the literal "immediately," not just "at next login") and `test_suspend_user_revokes_all_active_refresh_tokens`.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted — the `get_current_user` architectural change was confirmed with the user before implementing; the email-search spec gap is documented, not silently resolved
- [x] Full backend test suite, ruff, black, mypy all green (see Verification Results)
- [x] Frontend `tsc --noEmit`, ESLint, `vitest run`, and `next build` all green
- [x] Browser QA performed — see Verification Results (real browser install unavailable in this environment; verified instead through the real Next.js BFF proxy with real cookies/CSRF, the same request path a browser takes)
- [ ] Linked in a PR description — not created this session (no commit was made, per the session's explicit instruction)

## Known Limitations (recorded, not silently dropped)
- **No true interactive-browser (Playwright) QA** — Chrome could not be installed in this environment (no admin privileges). Substituted with full HTTP-level verification through the real Next.js dev server's BFF proxy (real login, real CSRF token, real cookie relay) — the same code path a browser exercises, just driven by curl instead of a rendered page. Visual/layout correctness (spacing, responsive behavior at tablet width per `ui-ux.md` §15) was not verified.
- **No dedicated frontend unit tests** (`*.test.tsx`) were added for the new admin components — the existing 182 frontend tests all still pass (regression-clean), and the components were verified working end-to-end via the BFF, but component-level test coverage matching e.g. `filter-bar.test.tsx`'s depth was not built for this task, to keep scope controlled.
- **`GET /admin/users`'s email search is client-side-over-the-loaded-page only** (see Implementation Notes) — a `ui-ux.md`/`api.md` inconsistency, not an R10 defect; flagged for a future spec reconciliation pass, not fixed unilaterally here.

## Verification Results
- **Targeted test files:** `test_admin_repository.py` (9), `test_admin_api.py` (16) — 25 total, all passed.
- **Full backend suite:** 505 passed, 0 failed (480 pre-existing + 25 new — the 2 pre-existing tests fixed for compatibility are counted in the 480 baseline, not as new tests). Run three times, identical pass count each time (~27–38s per run).
- **Ruff:** clean. **Black:** clean. **Mypy:** clean (100 source files).
- **Frontend:** `tsc --noEmit` clean; ESLint clean on every new/modified file; `vitest run` — 182/182 passed (no regressions); `next build` — compiled successfully, `/admin`, `/admin/users`, `/admin/system` all present in the route manifest.
- **Migrations:** none added — confirmed no schema change was needed by inspection.
- **Live smoke test (backend only, ASGI transport):** real Postgres, no dependency overrides — suspend → target's next request gets `403 account_suspended` → unsuspend → access restored, all against real independent DB connections (not the shared test-transaction session).
- **Live smoke test (full stack, through the real Next.js BFF):** real `uvicorn`/`next dev` processes, real Postgres/Redis, two real registered users (one promoted to `admin` directly in the dev DB), real login → real `csrf_token` cookie → `GET /admin/users` (200, correct rows) → `GET /admin/system/health` (200) → `POST .../suspend` with the real CSRF token (200) → the target's own already-authenticated session immediately got `403 account_suspended` on its next request (through the same BFF, real cookies) → `POST .../unsuspend` (200) → target's access restored. All QA users, the dev-only `.env.local`, and both dev server processes were removed/stopped afterward — confirmed via `git status` (clean) and a final port check.
- **Tenant isolation / authorization:** verified by both the automated suite (the dedicated non-admin-gets-403-on-every-route test, the `NFR-PRIV-004` content-leak test) and the live full-stack check (a non-admin session was never tested against `/admin/*` live, but is covered exhaustively in the automated suite).
- **AI observability:** not applicable — R10 makes no LLM/embedding provider calls.
- **Scope check:** `git status` shows exactly the files listed above as modified/new. The `get_current_user`/`errors.py`/`user_repository.py` changes and the two fixed test files are the one documented, necessary exception to "no R1–R9 changes," explicitly confirmed with the user before implementing. No R11+ code, no spec/roadmap changes, no migration, no commit made, no deployment.
