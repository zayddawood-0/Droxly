# Task R12: Production Deployment Readiness

## Task ID
R12-001

## Feature
Production deployment readiness verification and closure of the gaps `tasks/remediation-plan.md` §15 explicitly named as "still to plan/build once R1–R11 land": CORS middleware, security headers, structured JSON logging + request-ID correlation, a Production Launch Runbook, a scripted smoke test, and a basic load test — plus a full checklist audit (security, config, database, workers, storage, observability, health, error handling, deployment config, frontend, testing, smoke test) against `specs/deployment.md`, `specs/security.md`, `specs/observability.md`, and the §15.1 P0 gate.

## Objective
This is the final production-readiness phase, not new feature work. Verify — with evidence, not assumption — whether R1–R11's implementation is actually deployable, closing only the specific gaps the remediation plan named for R12 and any genuine defect discovered along the way that blocks production. Do not start R13, do not implement P1/P2 features, do not weaken any requirement to make a check pass.

## Specification References
- `tasks/remediation-plan.md` §15/§15.1 — R12 scope and the explicit P0 gate checklist.
- `specs/deployment.md` — production topology, environment variables, hardening requirements (CORS, HTTPS, security headers), the new §14 Production Launch Runbook this task adds.
- `specs/security.md`, `specs/observability.md`, `specs/api.md` §0.5/§0.7, `specs/performance.md` §3 (`NFR-PERF-002`), `specs/testing.md`.

## Requirements
Verifies/closes `NFR-SEC-011` (security headers), `NFR-SEC-010`/CORS, `NFR-OBS-*` (structured logging, request correlation), `NFR-PERF-002` (load test), and the full §15.1 P0 gate list. No new `FR-*` requirement is introduced.

## Dependencies
R1 through R11, all committed and independently verified.

## Files Affected
- `backend/app/core/logging.py` — **new** — structured JSON log formatter + `configure_logging()`.
- `backend/app/main.py` — CORS middleware, security-response-headers, request-ID correlation middleware, completes the previously-deferred unhandled-exception structured log call.
- `backend/app/core/config.py` — `cors_allowed_origins` / `log_level` settings.
- `backend/app/core/storage.py` — fixed a pre-existing silent-fallback bug: `get_storage_provider()` ignored `STORAGE_PROVIDER` entirely and always returned the local filesystem implementation; now raises loudly for any unimplemented provider value.
- `backend/app/workers/_observability.py` — **new** — shared job-lifecycle structured logging (`job.started`/`job.completed`/`job.failed`) for all four RQ entrypoints.
- `backend/app/workers/__init__.py`, `backend/app/workers/{document_processing,extraction,comparison,summary}_worker.py` — wired to the above.
- `backend/.env.example`, `frontend/.env.example` — corrected to match what the code actually reads (added missing R1–R3 settings; removed the stale, unused `NEXT_PUBLIC_API_BASE_URL` claim).
- `backend/Dockerfile` — corrected a stale "worker entrypoint doesn't exist yet" comment (it has, since R3/R5/R6/R7).
- `docker-compose.yml` — added the previously-missing `backend` service; fixed `worker`'s command (was only consuming 1 of 4 real queues); added a shared local-storage volume between `backend`/`worker`; fixed a graceful-shutdown defect (`sh -c "... && uvicorn ..."` without `exec`, so a forwarded `SIGTERM` never reached uvicorn).
- `frontend/app/api/v1/[...path]/route.ts` — corrected a stale "not reachable yet" docstring from Phase 1 scaffolding.
- `specs/deployment.md` — added §14 Production Launch Runbook; corrected the `NEXT_PUBLIC_API_BASE_URL` inventory row to match the actual (fully BFF-proxied, including SSE) implementation.
- `backend/tests/test_production_hardening.py` — **new** — 10 tests: security headers, HSTS environment-conditional behavior, request-ID propagation/matching, CORS allow/deny, storage-provider guard.
- `backend/scripts/smoke_test.py` — **new** — live, separately-running-`uvicorn`-process P0 golden path smoke test.
- `backend/scripts/load_test.py` — **new** — basic concurrent-load check against `NFR-PERF-002`'s budget.

## Implementation Notes

### The storage-provider fallback bug (found by inspection, not by a failing test)
`get_storage_provider()` built a `LocalFilesystemStorageProvider` unconditionally, regardless of `settings.storage_provider`'s actual value. In a multi-replica production deployment with `STORAGE_PROVIDER` set to anything other than `local` (which, per `decisions.md` OQ-04, is the *only* implementation that exists), this would silently write every uploaded document to one replica's local disk — invisible to every other replica, and gone on redeploy. Fixed to raise `RuntimeError` for any unimplemented provider value rather than silently substituting a wrong one.

### `docker-compose.yml`'s graceful-shutdown defect
`command: sh -c "alembic upgrade head && uvicorn ..."` runs uvicorn as a *child* of `sh`. `sh` does not relay a forwarded `SIGTERM` to a child it is merely waiting on — `docker compose stop`/a rolling deploy would get no graceful drain at all, falling straight through to `SIGKILL` after the stop grace period and dropping any in-flight request (including a streaming chat response), directly contradicting `deployment.md` §3's explicit graceful-shutdown requirement. Fixed with `exec` before `uvicorn` so it replaces the shell process and receives the signal directly.

### The `rq worker` / Windows gap (see `backend/scripts/smoke_test.py`'s own docstring for the full account)
A real, separately-running `rq worker` process consuming the queue has never been exercised anywhere in this project — not by any pytest file (all four `test_*_worker.py` files and `test_r11_golden_path.py` invoke job functions directly), not by CI (no workflow step runs `rq worker`), and an attempt to add it to this task's own live smoke test hit two independent POSIX-only crashes running natively on this session's Windows host (`os.fork()`, `signal.SIGALRM`) — an upstream RQ constraint, not a Doxly defect, and not something the real deployment hits (`backend/Dockerfile` is a Linux container). The smoke test instead verifies the enqueue side for real (RQ `queue.count` assertions) and executes jobs directly in-process, the same established pattern every worker test already uses. This is a genuine, named verification gap, not silently glossed over — see the R12 readiness report.

### Rate-limit burst check false negative, and what it revealed
The smoke test's first version hammered 75 requests under `user_a`'s identity *after* that identity had already made ~20 real general-tier requests earlier in the same run, made the exact remaining-token count hard to reason about, and produced a misleading "no 429 seen" result. An isolated, minimal repro (a single fresh user, 70 rapid requests, inspecting the actual Redis token-bucket key afterward) proved the real mechanism is correct: exactly 60 succeed, then every subsequent request 429s, matching `api.md` §0.7's documented capacity exactly. The smoke test was fixed to burst-test a fresh, isolated identity instead of reusing a warmed-up one.

## Testing Summary
- Backend: `pytest` — 517 passed, run twice (no nondeterminism observed).
- Frontend: `vitest` — 182 passed (50 files); `tsc --noEmit` clean; `eslint` clean; `next build` succeeds.
- New: `test_production_hardening.py` — 10/10 passed.
- Live-local smoke test (`backend/scripts/smoke_test.py`, real separate `uvicorn` process, real Postgres, real Redis) — 26/26 steps passed on the final run.
- Live-local load test (`backend/scripts/load_test.py`, 10 concurrent × 20 requests against `GET /documents`) — p95 190.3ms against `NFR-PERF-002`'s 300ms budget: **PASS**.

Full verdict, evidence, and the complete P0 gate matrix: see the R12 Production Deployment Readiness Report delivered alongside this task file.
