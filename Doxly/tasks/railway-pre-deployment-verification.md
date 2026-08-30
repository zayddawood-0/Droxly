# RAILWAY PRE-DEPLOYMENT VERIFICATION REPORT

**Date:** 2026-08-29 · **Scope:** verification only. No deployment performed. No commit made. No application code modified.

---

## A. Overall Status

## **READY WITH CONDITIONS**

Every local check that can run without a live Railway account is green (520/520 backend tests, 182/182 frontend tests, ruff/black/mypy/eslint/tsc all clean, migrations at head, both production builds succeed). Nothing found this pass required an application-code change, so nothing was changed. One **new, genuine deployment blocker** was found and is reported here, not silently fixed, per your explicit instruction: **the backend hardcodes port 8000 rather than reading Railway's injected `$PORT`** (§J.1). Everything else carried forward from the prior Railway readiness report (Postgres URL scheme, `pgvector` availability, OQ-04/storage) remains unresolved in exactly the same way — re-verified, not assumed.

---

## B. Frontend Status

- **Production build:** `npm run build` succeeds — 23 routes, correct static/dynamic split, `postbuild` asset copy succeeds. Re-run this pass, clean.
- **API/BFF configuration:** unchanged from R12's finding — `app/api/v1/[...path]/route.ts` proxies every request (including the SSE chat stream) same-origin; no direct browser-to-backend call exists anywhere in frontend source (re-confirmed by this pass's grep sweep, §J below).
- **Production environment variables:** `INTERNAL_API_URL` (server-only) must point at the Railway backend's public domain once it exists; `NEXT_PUBLIC_API_BASE_URL` remains unused (R12 finding, unchanged).
- **No localhost URLs in production code paths:** confirmed by full-repo grep (§J) — the only frontend-side `localhost` reference in actual source is a code *comment* (`hooks/use-document-upload.ts`, explaining a `crypto.randomUUID()` secure-context caveat, not a URL used anywhere) and `playwright.config.ts`'s own local E2E `baseURL` (test-only, never shipped).
- **HTTPS/cookie assumptions:** correct and, per the BFF pattern, lower-risk than a naive cross-platform read would suggest — the browser only ever talks to Vercel, so the `Set-Cookie` header it actually receives is scoped to the Vercel domain regardless of Railway's own domain (R12/Railway-readiness finding, re-confirmed, unchanged).
- **Frontend deploys to Vercel, not Railway** (`ADR-007`, unchanged) — `frontend/Dockerfile` remains local-dev-parity-only.

**Status: READY** (no frontend-side blocker).

## C. Backend Status

- **Production startup command:** `sh -c "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"` — the `exec` fix from R12 is present and correct (graceful shutdown). **Port is hardcoded — see J.1, a genuine finding.**
- **Docker configuration:** multi-stage, non-root, patched base image, correct `HEALTHCHECK` — unchanged, re-confirmed by reading the file directly this pass.
- **Production environment variables:** full list in N below; unchanged from the prior Railway report.
- **CORS:** `CORSMiddleware` present, no wildcard anywhere in app code (re-confirmed by grep), origin list must be set to the real Vercel domain on Railway.
- **JWT configuration:** HS256, `jwt_signing_key`'s local-dev default is explicitly insecure and must be overridden — unchanged finding, still open (not a defect, a required deploy-time action).
- **OAuth configuration:** `redirect_uri` is built from `settings.frontend_base_url`, not the backend's own origin — the Google Cloud Console redirect URI must be the **Vercel** domain (re-confirmed by re-reading `auth.py` this pass, unchanged from the prior report's §J finding).
- **SMTP/email configuration:** defaults to `FakeEmailProvider` (safe, non-functional for real users) until `EMAIL_PROVIDER=smtp` + real SMTP credentials are set — unchanged.
- **Redis configuration:** see E below.
- **PostgreSQL configuration:** see D below.
- **Trusted proxy/client-IP handling:** `_client_ip()` reads `request.client.host` directly — no `X-Forwarded-For` trust logic exists. **Relevant now that a real platform is chosen**: Railway's own edge network sits in front of every service, meaning the backend process may see Railway's internal proxy as the connecting client rather than the true external IP, depending on how Railway's networking layer presents the connection. This affects only the IP-keyed pre-auth rate-limit tier (`rate_limit_general`'s fallback for unauthenticated requests) — not authorization or tenant isolation. **Flagged as a verify-after-first-deploy item (§K), not fixed** — confirming whether Railway forwards a trustworthy `X-Forwarded-For`/similar header requires observing real traffic against a real deployed instance, which doesn't exist yet.

**Status: READY WITH CONDITIONS** (the port binding in J.1 is the one concrete item; everything else is either already correct or a deploy-time configuration action, not a code defect).

## D. PostgreSQL Status

- **Railway compatibility:** unchanged from the prior report — Railway's managed Postgres plugin's `pgvector` availability remains **unverified without a live account**. Recommendation unchanged: deploy Postgres as a custom `pgvector/pgvector:pg16` image if the managed template doesn't include it, since that image is already the one this project tests against locally and in CI.
- **`DATABASE_URL` handling:** Railway's auto-generated Postgres `DATABASE_URL` uses the bare `postgresql://` scheme; this codebase's async SQLAlchemy engine requires `postgresql+asyncpg://` (confirmed again by reading `app/core/database.py`/`config.py` this pass — no change since the last report). Must be set explicitly via Railway's variable-reference syntax with the correct scheme prepended — a Railway configuration step, not a code change.
- **Migration procedure:** `alembic upgrade head`, run automatically as part of the `backend` service's start command before `uvicorn` starts (unchanged, correct pattern).
- **Migrations at head:** re-verified this pass — `alembic heads == current == 0004_search_tsvector`. No missing migration.
- **No destructive migration required for initial deployment:** confirmed by reading every migration file's `upgrade()` — all are additive (new tables/columns/indexes/extensions) or `CREATE EXTENSION IF NOT EXISTS`; none drop or alter existing data-bearing columns. A fresh Railway Postgres instance running the full chain from empty is exactly the same operation already verified (`alembic downgrade base && alembic upgrade head`, confirmed clean in R3's own verification history and re-confirmed structurally this pass by reading the migration set).

**Status: READY WITH CONDITIONS** (both conditions are Railway-account verification steps, not code defects).

## E. Redis Status

- **Railway compatibility:** Railway's managed Redis add-on exposes `REDIS_URL` as `redis://default:password@host:port` — directly compatible with `redis.asyncio.from_url()`, no scheme translation needed (unchanged finding, re-confirmed by reading every module that constructs a Redis client: `rate_limit.py`, `queue.py`, `chat_stream_control.py` — all use the same `redis_url` setting, none assume a specific host/port beyond what the URL encodes).
- **`REDIS_URL` handling:** bind directly to Railway's Redis reference — no blocker.
- **Rate limiting configuration:** `GENERAL_TIER_CAPACITY=60`/`60s`, `AI_TIER_CAPACITY=10`/`60s` + daily caps — unchanged, platform-agnostic (re-verified live end-to-end in the R12 pass: exactly 60 successes then 429s under a real HTTP burst).
- **Fail-open behavior:** confirmed present in `rate_limit.py`, `queue.py` (`ADR-021`/`ADR-023`) — a Redis outage degrades to "no rate limiting"/"job left queued with a logged warning," never a 5xx storm. Unchanged, correct, platform-agnostic.
- **Production connection configuration:** no TLS-specific Redis configuration exists in the codebase today (`redis://`, not `rediss://`). Railway's Redis add-on's private networking is the expected connection path (service-to-service within the same Railway project, not exposed publicly) — if Railway's Redis only offers a `rediss://` (TLS) connection string for a given plan tier, `redis.asyncio.from_url()` handles that transparently (the scheme itself tells the client library to negotiate TLS); no code change would be needed either way, only using whichever URL Railway actually provides.

**Status: READY** (no blocker; connection scheme is self-describing and handled correctly regardless of which Railway offers).

## F. RQ Worker Status

**Exact entrypoint:** `app/workers/document_processing_worker.py`, `app/workers/extraction_worker.py`, `app/workers/comparison_worker.py`, `app/workers/summary_worker.py` — four job functions, consumed by a single generic `rq worker` process listening on all four queue names (`architecture.md` §2.3: "one generic worker role," not four separate worker services). Exact production command, unchanged from `docker-compose.yml`: `rq worker document_processing extraction comparison summary --url $REDIS_URL`.

- **Can it run as an independent process/container?** Yes, by construction — it's the same Docker image as `backend` with only its Start Command overridden, exactly the pattern already validated locally via `docker-compose.yml`'s `worker` service (though that service itself has never been run in *this specific environment* either, since the Docker daemon here has been unresponsive all session — see below).
- **Same PostgreSQL/Redis configuration as backend?** Yes — confirmed by reading all four worker files directly this pass: each uses `app.core.database.async_session_factory`/`engine` (the same module-level engine `backend` uses) and the same `settings.redis_url`-derived queue connection (`app/core/queue.py`). No separate configuration surface exists for the worker.
- **Required environment variables:** identical set to `backend` (§N) — the worker needs `DATABASE_URL`, `REDIS_URL`, and every AI-provider/storage credential the job functions might invoke (LLM/embedding keys), since job execution calls the same service layer `backend` would for an inline request.
- **No Windows-only assumptions in the production Linux path:** confirmed by grep (`platform_system`/`sys.platform`/`win32` — zero matches anywhere in `app/workers/` or `app/core/queue.py`, re-run this pass, unchanged) and by construction (`backend/Dockerfile`'s base image is `python:3.12-slim`, a real Linux environment where RQ's default forking `Worker` class's dependencies — `os.fork()`, `signal.SIGALRM` — are both standard). The Windows-specific crashes this project's own local smoke-testing hit (`os.fork()`/`SIGALRM` `AttributeError`s) are a documented **host-OS** limitation of this development machine, not the worker code itself.
- **Explicit, honest statement per your instruction:** **a real, standalone `rq worker` process consuming a live queue has still never been executed and verified in this project's history, in this pass or any prior one.** This is not claimed as complete. It is strongly believed correct by code inspection and by the fact that RQ's default Worker class on Linux is an extremely standard, widely-deployed pattern with nothing unusual in how this codebase uses it — but "strongly believed correct by inspection" and "verified by actually running it" are different claims, and only the first is true today.

**Status: READY WITH CONDITIONS** (config/entrypoint verified correct by inspection; actual execution remains unverified — this is the same, unchanged gap from every prior pass, carried forward honestly rather than re-labeled as closed).

## G. Security/Secrets Status

Full repo-wide sweep re-run this pass (§J), not assumed from memory:

| Check | Result |
|---|---|
| `SECRET_KEY`/JWT secrets committed | None found. `jwt_signing_key`'s insecure local-dev default is intentional and documented as unsafe for production. |
| OAuth secrets committed | None found. |
| SMTP credentials committed | None found. |
| Database credentials committed | None found — `alembic.ini`'s `driver://user:pass@localhost/dbname` is Alembic's own generic scaffolding placeholder, confirmed dead (overridden by `env.py` reading `settings.database_url` before any connection). |
| Redis credentials committed | None found. |
| CORS origins | No wildcard anywhere in app code; `CORSMiddleware` correctly configured from `CORS_ALLOWED_ORIGINS`. |
| Secure cookies | `httponly=True`, `secure=(environment != "local")`, `samesite="lax"` — confirmed by reading `auth.py`/`csrf.py` directly this pass. |
| CSRF configuration | Double-submit pattern present on every mutating post-session route; correctly omitted on pre-session routes (no forgeable session exists yet). |
| Secrets committed to git (general sweep) | None — grepped for private-key headers, common cloud API key shapes (`sk-`, `AKIA`, `ghp_`, `xox`), zero matches repo-wide. |
| `.env` files properly ignored | Confirmed via `git ls-files` — no `.env`/`.env.*` file is tracked except both `.env.example` files, which contain placeholders only (re-read in full this pass). |

**Status: READY** (no security/secrets finding this pass; all prior findings remain correctly closed).

## H. Migration Status

- `alembic heads` == `alembic current` == `0004_search_tsvector` — **at head**, re-verified this pass against the local dev Postgres.
- No missing migration — every table/index/extension named in `database.md` exists in the migration chain (cross-checked structurally, not re-derived from scratch, since this was already exhaustively verified in R3's and R8's own task files and is unchanged since).
- No destructive migration required for an initial deployment — confirmed by reading every migration's `upgrade()` function: additive only (`CREATE TABLE`, `CREATE INDEX`, `CREATE EXTENSION IF NOT EXISTS`, `ALTER TABLE ADD COLUMN`). A fresh Railway Postgres running the full chain from empty is not a different code path from what CI and local dev already exercise on every run.

**Status: READY.**

## I. Local Test/Build Results (this pass)

| Check | Result |
|---|---|
| Backend `pytest` (full suite) | 520 passed |
| Backend `ruff check` | Clean |
| Backend `black --check` | Clean, 169 files |
| Backend `mypy app/` | Clean, 102 files |
| Migration verification | `alembic heads == current == 0004_search_tsvector` |
| Frontend `tsc --noEmit` | Clean |
| Frontend `eslint` | Clean |
| Frontend `vitest` | 182 passed, 50 files |
| Frontend production build | Succeeded, 23 routes |
| `docker compose config --quiet` | Valid |
| Backend Docker build (real) | **Not performed** — Docker daemon unresponsive in this session (reconfirmed, fresh 10s probe), same unchanged environment constraint as every prior pass |

## J. Production Configuration Issues

**J.1 — New finding this pass: hardcoded port, not Railway's `$PORT` convention.**
`backend/Dockerfile`'s CMD and `docker-compose.yml`'s `backend` service both hardcode `--port 8000`. Railway (like most PaaS platforms in this category) injects a `PORT` environment variable and expects the application to bind to it — Railway's routing layer directs external traffic to whatever port the app is actually listening on, and the documented, robust pattern is to read `$PORT` rather than assume a fixed value. A hardcoded port is a **real risk**, not a certainty of failure (Railway can sometimes work with a fixed/EXPOSEd port), but it is exactly the kind of thing that silently works in local `docker-compose` (where you control the host-port mapping yourself) and silently fails or behaves unpredictably on a PaaS that manages the port assignment. **Not fixed — reported per your explicit instruction.** The minimal, safe fix (for your approval, not applied): change the backend service's start command to `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`, which falls back to 8000 for local/Compose use (where `$PORT` is unset) and honors Railway's injected value in production. This is a one-line change to `docker-compose.yml`'s command string and/or the Railway service's own Start Command override — it does not require touching `backend/Dockerfile`'s own CMD if Railway's Start Command field is used to override it directly (the same mechanism already used for the worker's queue-consumer command).

**J.2 — Trusted-proxy/IP handling, now concretely relevant.** Carried forward from the prior report as a "becomes relevant once a platform is chosen" item — it's chosen now. `_client_ip()` doesn't inspect any forwarded-for header. Recommend verifying what Railway's edge actually presents to the backend process after the first real deploy, before relying on IP-keyed rate limiting for anything security-critical.

**J.3 — OQ-04 (storage provider) remains open**, unchanged from the prior report — `STORAGE_PROVIDER=local` is not viable for real production use regardless of Railway readiness otherwise.

No other production-configuration issue was found this pass.

## K. Exact Deployment Blockers

1. **J.1 — hardcoded port** (needs your decision: apply the `${PORT:-8000}` fix, or confirm Railway's fixed-port behavior works for your specific service configuration before relying on it).
2. **`pgvector` availability on Railway's managed Postgres — unverified**, resolved either by verifying against the real instance or by using the `pgvector/pgvector:pg16` custom-image path.
3. **`DATABASE_URL` scheme** must be set explicitly (Railway config step, not a code change).
4. **OQ-04 (storage provider)** remains open — blocks real user document storage, independent of Railway.
5. **Standalone `rq worker` execution remains unverified** — not a known defect, but genuinely untested; first real Railway deploy would be the first real-world test of it unless verified earlier via a working Docker daemon or a Linux CI job.

None of these were silently fixed. All five require either your decision, a Railway-account-side verification step, or (for #1 only) your explicit approval to apply the one-line documented fix.

## L. Exact Railway Services to Create

1. `backend` — from `backend/Dockerfile`, public networking, Start Command `sh -c "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"` (pending J.1's resolution — or `--port 8000` unchanged if you decide to rely on Railway's fixed-port handling instead).
2. `worker` — same repo/Dockerfile, no public networking, Start Command `rq worker document_processing extraction comparison summary --url $REDIS_URL`.
3. `postgres` — Railway managed Postgres **or** a custom Docker image deploy of `pgvector/pgvector:pg16` (recommended, per D).
4. `redis` — Railway managed Redis.

Frontend is **not** a Railway service (Vercel, unchanged).

## M. Exact Deployment Order

1. Create `postgres` and `redis` first (backend/worker depend on both existing before they can start meaningfully).
2. Verify `pgvector` is available on the provisioned Postgres (`CREATE EXTENSION vector;`) — resolve via custom image if not.
3. Create `backend`, set every variable in N, confirm the migration-then-serve start command runs cleanly on first deploy (watch the deploy logs for the `alembic upgrade head` step specifically).
4. Create `worker` once `backend` is healthy (mirrors `docker-compose.yml`'s own `depends_on: backend: condition: service_healthy` ordering, which has no direct Railway equivalent — a human should just wait for `backend`'s health check to go green before starting `worker`, or accept a brief early-failure-and-retry window if deploying both simultaneously).
5. Point Vercel's `INTERNAL_API_URL` at the now-live `backend` public domain.
6. If launching with real Google OAuth, register the redirect URI (Vercel domain, not Railway's) before real users attempt sign-in.

## N. Exact Environment Variables Required for Each Service

**`backend` and `worker` (identical set):**
`DATABASE_URL` (secret, explicit `postgresql+asyncpg://` scheme — J/D), `REDIS_URL` (secret, bind directly to Railway's Redis reference), `JWT_SIGNING_KEY` (secret, real random value), `ENVIRONMENT=production` (non-secret), `CORS_ALLOWED_ORIGINS` (non-secret, real Vercel domain), `FRONTEND_BASE_URL` (non-secret, real Vercel domain — also drives the OAuth redirect URI), `BACKEND_PUBLIC_BASE_URL` (non-secret, Railway backend's own domain), `STORAGE_PROVIDER` (blocked on OQ-04) + its credentials (secret, once resolved), `LOG_LEVEL` (non-secret), `LLM_PROVIDER`/`ANTHROPIC_API_KEY` (secret, once real LLM calls are wanted), `EMBEDDING_PROVIDER`/`OPENAI_API_KEY` (secret, same caveat), `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` (secret, once real Google sign-in is wanted), `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD` (secret, once real email delivery is wanted), `EMAIL_FROM_ADDRESS`/`EMAIL_PROVIDER` (non-secret), `DOCUMENT_PROCESSING_STALE_THRESHOLD_SECONDS` (non-secret, `900` default), `STORAGE_PRESIGNED_URL_EXPIRES_IN_SECONDS` (non-secret, `900` default), and (pending J.1) `PORT` — Railway injects this automatically; do not set it manually.

**Vercel (`frontend`, unchanged by this pass):** `INTERNAL_API_URL` (non-secret, server-only — the Railway backend's public domain), `NEXT_PUBLIC_API_BASE_URL` (unused, per R12).

**GitHub Actions (CI, not an application runtime variable):** `RAILWAY_TOKEN` (secret) — only needed once you want CI's deploy-gate step to actually mean something; today it's still an inert placeholder.

## O. Exact Post-Deployment Verification Steps

1. `curl https://<railway-backend-domain>/health` → `{"status": "ok"}`.
2. Check the `backend` service's deploy logs for a clean `alembic upgrade head` run with no errors.
3. Confirm `worker` service logs show `*** Listening on document_processing, extraction, comparison, summary...` (RQ's own startup line) with no crash.
4. Register/log in a real test account through the real Vercel frontend, upload a small document, confirm it reaches `ready`.
5. Check Railway's log stream for `request.completed`/`job.started`/`job.completed` structured JSON lines (confirms R12's structured logging is actually active in the real deployed environment, not just locally).
6. Adapt and run `backend/scripts/smoke_test.py` against the real deployed origin (per `deployment.md` §14.3 — the script currently only spawns local subprocesses; pointing it at a remote origin is a small, not-yet-made adaptation).
7. Specifically verify J.1's port binding actually worked (the health check passing is the practical proof) and J.2's proxy/IP behavior (check what `request.client.host` actually resolves to in a real request's logs).

## P. Should Playwright E2E Run Before or After Deployment?

**Both, for different reasons, and neither blocks the other.**
- The **existing** E2E suite (58/59 passing, connectivity-error-style per `testing.md` §2.4's documented interim state) is environment-independent — it already ran successfully in this session against a local build with no backend at all, and running it again pre- or post-deploy adds no new information about Railway specifically.
- The **real golden-path rewrite** (`release-closure-plan.md` item #4, still not started — out of this pass's scope) would be more valuable run against a **real backend**, which this local environment already provides today (Postgres/Redis/backend all startable locally) — it does not need to wait for an actual Railway deployment to be written and run meaningfully. Recommend: write and run it locally **before** the first real deploy, so a real regression is caught before it reaches Railway, not treated as a reason to delay closing OQ-13-adjacent work.

## Q. Can the Deployed-Environment Smoke Test Be Performed Now?

**No.** No Railway account has been provisioned and no deployment has occurred — this pass was explicitly verification/preparation only, per your instruction not to deploy. `backend/scripts/smoke_test.py` cannot target something that doesn't exist yet. This item stays exactly where the last report left it: mechanically downstream of an actual first deploy (§M), not something this pass could advance further.

---

## Git Status

```
On branch main
Your branch is ahead of 'origin/main' by 2 commits.

nothing to commit, working tree clean
```

## Files Changed During This Pass

**None.** This was a read/run/verify-only pass — every check above was performed by reading existing files and running tests/lint/build/migration commands; nothing was edited.

## Whether Any Commit Was Created

**No.** `git status` is clean because nothing changed, not because anything was committed. The two commits shown as "ahead of origin" (`51b986b`, `29813a6`) are from the two prior passes, already reported at the time they were made — no new commit exists from this verification pass.

---

Stopping here, as instructed. No deployment was performed or attempted. The one concrete decision point requiring your input before proceeding is **J.1 (the port binding fix)** — everything else in §K is either a Railway-account-side verification step or an already-known, unchanged open item.
