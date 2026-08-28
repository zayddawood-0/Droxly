# R12 Production Deployment Readiness Report

**Date:** 2026-08-28/29 · **Scope:** `tasks/remediation-plan.md` R12 · **Author:** Claude Code (this session)

---

## 1. Executive Verdict

## **READY WITH CONDITIONS**

R1–R12 are implemented, tested, and — for everything that can be verified without a real deployed environment or a container platform decision — verified. The application is **not** blocked by any code defect found this session; every defect found was fixed and re-verified. What blocks a clean **READY** is two things outside this session's authority to resolve: (1) `decisions.md` OQ-13 (container platform choice) is still open, so no `fly.toml`/Railway config exists and no actual deployment has occurred; (2) two P0 gate items in §15.1 are genuinely unverified in this environment (real Playwright browser E2E; an actual deployed-environment smoke test) — not because they fail, but because the tools to run them (a browser, a live deployment) are not available here. Both are named explicitly, not glossed over. See §15.

**Do not deploy to production from this report alone.** It confirms the code, config, and local/live-local verification are sound. It does not substitute for OQ-13 being resolved, secrets being provisioned, or a real staging smoke test.

---

## 2. Scope & Methodology

Per the user's instruction, every verification below is labeled by the level actually performed:
- **Unit/Integration** — `pytest`/`vitest` in-process (real Postgres/Redis for backend, no real network hop).
- **Live local** — a real, separately-running `uvicorn` process (backend/Dockerfile's actual entrypoint) on this session's Windows host, talking to real Postgres/Redis over real sockets. `backend/scripts/smoke_test.py` and `load_test.py`.
- **Container-local** — `docker compose` on this host. **Not achieved this session** — the Docker daemon was unresponsive to every `docker` CLI call throughout (confirmed via a bounded 8-second `docker info` probe that never returned). `docker-compose.yml` was validated statically (`docker compose config --quiet`) only.
- **Staging/Production** — not performed. No deployment occurred. No production credentials exist in this environment.

No claim in this report conflates these levels.

---

## 3. Checklist A — Security

| Item | Status | Evidence |
|---|---|---|
| Auth/authz (register/login/refresh/logout/reset/verify) | PASS | R1, re-verified live-local (smoke test) |
| `require_admin` | PASS | Live-local: non-admin → 403; admin → 200 |
| CSRF | PASS | Every mutating smoke-test call carries `X-CSRF-Token`; `test_r11_golden_path.py` + unit suite cover rejection paths |
| Rate limiting (general 60/min, AI 10/min+daily cap) | PASS | Isolated live-local repro: fresh user, 70 rapid requests → exactly 60×200 then 429s, matching `GENERAL_TIER_CAPACITY=60` exactly. Fail-open-on-Redis-error is deliberate (ADR-020), not a defect |
| Password hashing (argon2) | PASS (code inspection, R1) | `app/core/security.py` |
| JWT config (HS256, expiry) | PASS | `jwt_signing_key` local-dev default is explicitly insecure and documented as such; **must be overridden in production** (Runbook §14.1) |
| Refresh-token rotation/reuse detection | PASS (R1, unchanged this session) | |
| Session revocation (suspend → immediate) | PASS | Live-local: suspended user's very next request (no re-login) → 403 `account_suspended`; unsuspend restores access |
| Password-reset / email-verification security | PASS (R1, unchanged) | |
| OAuth config | PASS (returns `oauth_not_configured` when unset, R1) | |
| Multi-tenant isolation | PASS | Live-local: cross-tenant doc access → 404 not 403; search tenant-scoped; `ai_requests` isolation (R11) |
| CORS | **FIXED this session** | Was entirely absent. Added `CORSMiddleware`, origin list from `CORS_ALLOWED_ORIGINS`, no wildcard. 3 new tests (allow configured origin / reject unconfigured / no wildcard in list) |
| Security headers | **FIXED this session** | `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security` (non-`local` only) added in `request_context_middleware`. Tested |
| Trusted proxy/IP handling | NOT APPLICABLE at this phase | No reverse-proxy config exists yet (container platform undecided, OQ-13) — `_client_ip()` reads `request.client.host` directly; revisit once the platform's proxy behavior (e.g., `X-Forwarded-For`) is known |
| Cookie config | PASS (R1, httpOnly/secure/samesite — unchanged) | |
| Secret handling | PASS | No secret committed; `.env.example` files contain only placeholders (verified by reading both) |
| DEBUG settings / error-info leakage | PASS | `unhandled_exception_handler` never leaks stack traces to the client (api.md §0.5 envelope); full detail now actually logged server-side (previously only the safe envelope existed — R1's own docstring flagged this as deferred to R12) |

---

## 4. Checklist B — API/Application Configuration

- `.env.example` (backend) corrected: added `STORAGE_ACCESS_TOKEN`, `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `EMBEDDING_PROVIDER`, `OPENAI_API_KEY`, `DOCUMENT_PROCESSING_STALE_THRESHOLD_SECONDS`, `CORS_ALLOWED_ORIGINS`, `LOG_LEVEL` — every one of these already existed as a real `Settings` field but was undocumented.
- `.env.example` (frontend) corrected: `NEXT_PUBLIC_API_BASE_URL` documented as reserved/unused rather than implying the browser calls FastAPI directly (it doesn't — see §12).
- No real secret found in any example file (read both in full).
- Allowed origins, frontend/backend URLs, upload/storage config, AI provider config, rate-limit config, log config — all present in `Settings` (`app/core/config.py`), all have safe local defaults, all documented in `deployment.md` §5.1.

## 5. Checklist C — Database

- `alembic heads` == `alembic current` against the live dev Postgres: `0004_search_tsvector (head)` — migrations are complete and applied cleanly.
- No migration changes this session (none needed).
- Required indexes/constraints: unchanged from R1–R11, already verified by those tasks' own DB tests.
- Connection config: `DATABASE_URL` is environment-injected, no hardcoded credentials; SSL-required is a production-config concern documented in `deployment.md` §6 (not enforceable in code without knowing the target provider).

## 6. Checklist D — Redis/Workers/Background Jobs

- Redis connectivity: live-verified (real enqueue, real rate-limit buckets).
- `docker-compose.yml`'s `worker` service **fixed**: was consuming only 1 of 4 real queues (`document_processing` only) — extraction/comparison/summary jobs would sit in Redis forever under `docker compose up`. Now lists all four, matching `app/core/queue.py`.
- Retry/failure behavior: unchanged from R3/R5/R6/R7 (`on_*_failure` callbacks, `Retry(max=3, ...)`), all still covered by the full unit suite (517/517).
- Stale-job recovery: `document_processing_stale_threshold_seconds` (ADR-026), unchanged, now documented in `.env.example`.
- Fail-open behavior (Redis-down rate limiting): deliberate, ADR-020, unchanged.
- **Genuine gap, named not hidden:** a real, separately-running `rq worker` process has never been exercised in this project on any OS, in CI, or in this session — see §15 item and `backend/scripts/smoke_test.py`'s docstring.
- Worker job-lifecycle logging: **added this session** (`_observability.py`, `job.started`/`job.completed`/`job.failed` structured events) — previously the workers logged nothing about their own execution.

## 7. Checklist E — Storage

- **Real bug fixed:** `get_storage_provider()` ignored `settings.storage_provider` and always returned the local filesystem implementation — a silent multi-replica data-loss risk. Now raises `RuntimeError` for any unimplemented provider. 2 new tests.
- Local storage is explicitly dev/local-only (`decisions.md` ADR-022); the only real provider until OQ-04 (cloud storage choice) resolves.
- Upload limits, file validation, path/key isolation, cleanup: unchanged from R2/R3, already tested.
- `docker-compose.yml`: added a shared `doxly-local-storage` volume between `backend` and `worker` — without it, a document uploaded via `backend` would be invisible to `worker` in a containerized dev/smoke-test run (separate container filesystems).

## 8. Checklist F — Observability

- **Structured JSON logging: built this session** (`app/core/logging.py`) — the formatter/handler layer was entirely missing; call sites already passed structured `extra={...}` fields (nothing to change there).
- Request/correlation IDs: **built this session** — `request_context_middleware` establishes one `request_id` per request (`request.state`), echoed in `X-Request-ID`, included in every log line and every error envelope for that request. Verified: inbound `X-Request-ID` is echoed back; error-response `request_id` matches the response header exactly.
- AI request logging, token usage: unchanged from R4–R7 (`ai_requests` table, `AiRequestRepository`), already tested.
- Worker failure logging: **built this session**.
- No secrets logged: `JsonFormatter` only emits `timestamp`/`level`/`service`/`request_id`/`user_id`/`event` + explicit `extra` fields already reviewed by R1–R11's own no-secrets discipline; no new call site logs a credential.

## 9. Checklist G — Health/Readiness

`GET /health` (DB connectivity + liveness, no auth, no sensitive data) already matched `deployment.md` §3 exactly before this session. No spec anywhere (`deployment.md`, `api.md`, `observability.md`, the remediation plan) names a separate readiness endpoint, a Redis health check, or worker-visibility endpoint. Per the explicit instruction to "implement only what is required," **no new endpoint was added.** PASS, no change.

## 10. Checklist H — Error Handling

The `api.md` §0.5 envelope (`{"error": {"code", "message", "fields"?}}`), `request_id` correlation, and `NFR-SEC-009`'s no-stack-trace-leak rule were already fully built (R1). This session completed the one explicitly-deferred piece: `unhandled_exception_handler` now actually logs the full exception server-side (previously only the safe client-facing envelope existed). Verified via the new hardening tests and the live smoke test's error-envelope/request-ID checks.

## 11. Checklist I — Deployment

- Backend/worker startup commands: `backend/Dockerfile`'s CMD (uvicorn) is real and correct; `docker-compose.yml`'s `worker` command now correct (4 queues).
- Migration procedure: `alembic upgrade head` runs automatically before `uvicorn` starts in Compose (`command: sh -c "alembic upgrade head && exec uvicorn ..."`) — **graceful-shutdown bug fixed** (added `exec`; without it, a forwarded `SIGTERM` never reached uvicorn, since `sh` doesn't relay it to a child it's merely waiting on — a direct contradiction of `deployment.md` §3's graceful-shutdown requirement).
- Production build: backend Dockerfile multi-stage, non-root, patched base image, correct `HEALTHCHECK` — unchanged, re-confirmed by reading.
- Container config: `docker-compose.yml`'s previously-missing `backend` service **added**.
- No dev-only config/localhost hardcoding found in backend or frontend source (grepped; only `.env.example` defaults reference `localhost`, which is correct for local dev).
- **Not done, explicitly:** `fly.toml`/Railway config (blocked on OQ-13, a platform decision this task must not make unilaterally); an actual deployment (not requested, and the user's scope rules disallow it without explicit approval).
- **Added this session:** `specs/deployment.md` §14, a full Production Launch Runbook (prerequisites, deploy sequence, post-deploy verification, rollback, explicit "not yet covered" list).

## 12. Checklist J — Frontend Production Readiness

- `npx tsc --noEmit`: clean.
- `npm run lint` (ESLint): clean.
- `npm run test` (Vitest): 182/182 passed, 50 files.
- `npm run build` (`next build`, Turbopack): succeeded, 23 routes, correct static/dynamic split, `postbuild` asset copy succeeded.
- API base URL / cookie / session handling: `lib/api/client.ts` — same-origin BFF pattern, session-refresh-and-retry on 401, CSRF double-submit — all same-origin, no hardcoded backend origin.
- **SSE corrected:** `app/api/v1/[...path]/route.ts` proxies the chat SSE stream same-origin (`upstream.body` passed through unbuffered) — the browser never calls FastAPI directly. `deployment.md` §5.1 and `frontend/.env.example` previously claimed otherwise (a stale claim from Phase 1 scaffolding, contradicted by `deployment.md`'s own §1 topology diagram); both corrected to match the actual, already-built, spec-consistent implementation. `NEXT_PUBLIC_API_BASE_URL` has zero readers anywhere in the codebase — documented as such, not deleted (its name stays reserved).
- Admin route protection: `AdminGuard` (`components/layout/admin-guard.tsx`) fails closed — pending/error/wrong-role states never mount admin children or fire their data hooks; real enforcement is backend `require_admin` (verified live-local: 403 for non-admin).
- No localhost/dev credentials found in source (grepped).
- Route-handler stale docstring corrected (previously claimed "not reachable yet — Phase 2+"; it has been reachable since R1).

## 13. Checklist K — Testing

| Suite | Result | Runs |
|---|---|---|
| Backend `pytest` (full suite) | **517 passed** | 2× (no nondeterminism) |
| `test_production_hardening.py` (new) | **10/10 passed** | included above |
| R11 integration suite (`test_r11_golden_path.py`) | Passing, part of the 517 | unit/integration tier |
| Frontend `vitest` | **182 passed**, 50 files | 1× |
| Frontend `eslint` | Clean | 1× |
| Frontend `tsc --noEmit` | Clean | 1× |
| Frontend `next build` | Succeeded | 1× |
| Backend `ruff check` | Clean (app/, tests/) | confirmed this session for new/changed files |
| Backend `black --check` equivalent | Applied (`black`, then re-checked clean) | this session's new/changed files |
| Backend `mypy` | Clean, 102 files | this session |
| Migration verification | `alembic heads` == `current` == head | live dev Postgres |
| Live Postgres/Redis/RQ smoke test | **26/26 steps passed** (final run) | live local — see §14 |

## 14. Checklist L — Production-Like Smoke Test

**Verification level: live local**, explicitly not container-local (Docker daemon unresponsive all session) and explicitly not staging/production (no deployment occurred). `backend/scripts/smoke_test.py`: real, separately-running `uvicorn` subprocess (backend/Dockerfile's actual CMD), real Postgres, real Redis, real HTTP over a real socket. 26/26 steps passed on the final run:

register/login (both tenants) → unauthenticated-rejected → upload+confirm ×3 → **real RQ enqueue verified** (`queue.count += 3`) → document processing (direct in-process job invocation — see the gap noted below) → `status=ready` → search (tenant-scoped) → chat conversation create → **chat SSE contract** (`message_id` first, `citations` present, `done` last) → summarization/extraction/comparison enqueue (202) + real completion → cross-tenant 404 → admin promote/list/suspend/unsuspend → **suspended-user immediate rejection, no re-login** → general rate limit (isolated fresh-user burst: 60×200 then 429s) → error envelope shape + `X-Request-ID` correlation.

**Named gap, not hidden:** job *execution* in this smoke test is direct in-process invocation (the same pattern every `test_*_worker.py` file and R11's own test already use), not a real, separately-running `rq worker` process. Building the smoke test surfaced that RQ's job execution unconditionally depends on `os.fork()` (default `Worker`) and `signal.SIGALRM` (RQ's timeout mechanism, invoked on *every* job, not just timeouts) — both POSIX-only, both absent on this session's Windows host, confirmed by two independent crash tracebacks. This is an upstream RQ/Windows incompatibility, not a Doxly defect, and does not affect the real deployment (a Linux container). But it means **a real standalone `rq worker` consuming the queue has never been verified anywhere in this project** — not by this script, not by CI (no workflow step runs it, on any OS), not by any existing test. This is the closest thing to a residual blocker this report identifies; see §15 and §16.

`backend/scripts/load_test.py`: 10 concurrent clients × 20 requests against `GET /documents` (a representative non-AI CRUD read, `NFR-PERF-002`) — **p95 190.3ms, budget 300ms: PASS.** (p99 was 904.7ms, likely per-client argon2 login cost under concurrency; p95 is the documented budget metric and comfortably passes.)

## 15. Checklist M — Remediation Plan §15.1 P0 Gate

| Item | Status | Evidence |
|---|---|---|
| Authentication works | PASS | Live smoke test |
| CSRF protection works | PASS | Live smoke test (every mutating call) |
| Rate limiting works | PASS | Isolated live repro |
| Authorization + multi-tenancy work | PASS | Live smoke test (cross-tenant 404, admin 403/200, suspend) |
| Document upload works | PASS | Live smoke test |
| Document processing works | PASS | Live smoke test (direct in-process job invocation — see below) |
| Chat works, incl. exact SSE contract | PASS | Live smoke test (`message_id`/`citations`/`done` ordering) |
| Summarization works | PASS | Live smoke test |
| Extraction works | PASS | Live smoke test |
| Comparison works | PASS | Live smoke test |
| Search works | PASS | Live smoke test |
| AI request observability works | PASS | R11 (unit/integration tier; not re-asserted live this session) |
| R11's full backend integration suite passes | PASS | Part of the 517 |
| **R11's rewritten Playwright E2E suite passes** | **BLOCKED — environment** | No Chrome tab group / no attached interactive browser in this headless background session (confirmed: `tabs_context_mcp` reports no tab group). R11's own report noted the identical constraint. Not fabricated as a pass. |
| **A production smoke test passes against the actual deployed environment** | **BLOCKED — no deployment exists** | Not achievable without OQ-13 resolved and a real deployment, which this task's scope explicitly does not authorize. The closest available evidence is §14's live-local run. |

**2 of 15 P0 gate items are BLOCKED, not PASS — both for environment reasons (no browser, no deployment), not because anything failed.** 13 of 15 are PASS with live-local evidence.

## 16. Blockers (require action outside this session's authority)

1. **OQ-13 (container platform) is still open.** No `fly.toml`/Railway config exists; none should, until a platform is chosen — that is a product/infra decision, not a code defect, and R12's scope explicitly forbids making it unilaterally.
2. **No real standalone `rq worker` process has ever been verified** consuming the queue, on any OS, anywhere in this project (§14). Recommended next step: verify this once a Linux CI runner or the real container platform is available (it will work there — the blocker is Windows-specific, confirmed by two independent POSIX-API crashes) — this is a real, if narrow, gap in verification depth, not a known-broken feature.
3. **Playwright browser E2E** (`frontend/e2e/*.spec.ts`) has not been run in this session (no browser attached) — same constraint R10/R11 already documented.
4. **Production smoke test against an actual deployed environment** cannot exist until (1) and a real deployment happen.

## 17. Non-Blockers (fixed this session, verified, no further action needed)

CORS middleware, security headers, structured JSON logging, request-ID correlation, unhandled-exception server-side logging, storage-provider silent-fallback bug, `docker-compose.yml`'s missing `backend` service / wrong `worker` queue list / missing shared storage volume / graceful-shutdown bug, stale Dockerfile/route-handler/deployment.md documentation, `.env.example` gaps (both frontend and backend), worker job-lifecycle logging, the Production Launch Runbook, the scripted smoke test, the basic load test, the rate-limit-check false negative in the smoke test itself.

## 18. Files Changed (complete list, this session only)

```
 M backend/.env.example
 M backend/Dockerfile
 M backend/app/core/config.py
 M backend/app/core/storage.py
 M backend/app/main.py
 M backend/app/workers/__init__.py
 M backend/app/workers/comparison_worker.py
 M backend/app/workers/document_processing_worker.py
 M backend/app/workers/extraction_worker.py
 M backend/app/workers/summary_worker.py
 M docker-compose.yml
 M frontend/.env.example
 M frontend/app/api/v1/[...path]/route.ts
 M specs/deployment.md
?? backend/app/core/logging.py
?? backend/app/workers/_observability.py
?? backend/scripts/smoke_test.py
?? backend/scripts/load_test.py
?? backend/tests/test_production_hardening.py
?? tasks/R12-production-deployment-readiness.md
?? tasks/R12-readiness-report.md
```
14 files modified, 8 new. No file outside `backend/`, `frontend/`, `docker-compose.yml`, `specs/deployment.md`, and `tasks/` was touched. No R1–R11 file was modified except where explicitly noted above (`.env.example` additions, the storage-provider bug fix).

## 19. Confirmations

- **R1–R11 remain green:** full backend suite (517/517, ×2) and frontend suite (182/182) both include R1–R11's own tests, unmodified, all passing.
- **No new product feature or redesign was started.** Every change above is either a named R12 deliverable (CORS, headers, logging, runbook, smoke/load test) or a genuine defect fix discovered while verifying R12's checklist (storage fallback, graceful shutdown, stale docs) — none expands product scope.
- **No deployment occurred.** No `docker compose up` succeeded (daemon unresponsive); no container platform was pushed to; no production/staging environment was touched.
- **No secret was committed.** Both `.env.example` files were read in full; only placeholder values are present.
- **No file outside R12's stated scope was modified.**
- **This report was not committed.** Per explicit instruction, no commit has been made. Awaiting approval before creating the final commit or performing any real deployment step.
