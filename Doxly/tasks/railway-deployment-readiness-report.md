# Railway Deployment Readiness Report

**Date:** 2026-08-29 · **Scope:** closing `decisions.md` OQ-13 and preparing Doxly for Railway deployment. **No deployment performed. No commit made.**

---

## A. OQ-13 Resolution

`specs/decisions.md`'s OQ-13 entry is updated from **Open** to **Decided: Railway**. Full ADR-style write-up (context, alternatives, reasoning, consequences) is in the file itself; summary: Railway hosts the backend and worker as two services built from the same image (mirroring `docker-compose.yml`'s existing split); PostgreSQL and Redis are Railway managed add-ons (with one caveat on Postgres — see F/G); the Next.js frontend is **unaffected** — it continues to deploy to Vercel per `ADR-007`, which was not reopened.

## B. Railway Service Architecture

```
Railway project
├── backend    — backend/Dockerfile, unmodified, public domain
├── worker     — same image, Start Command overridden to
│                `rq worker document_processing extraction comparison summary --url $REDIS_URL`,
│                no public networking
├── postgres   — Railway managed Postgres, OR a custom Docker image
│                deploy of pgvector/pgvector:pg16 (see F) — private networking only
└── redis      — Railway managed Redis — private networking only

Vercel (unchanged)
└── frontend   — Next.js, deploys to Vercel per ADR-007, not Railway
```

Full detail: `specs/deployment.md` §15.1.

## C. Required Services

| Service | Platform | New or existing config |
|---|---|---|
| Next.js frontend | Vercel | Existing, unchanged |
| FastAPI backend | Railway | New Railway service, existing Dockerfile |
| RQ worker | Railway | New Railway service, existing Dockerfile + Start Command override |
| PostgreSQL (+ pgvector) | Railway | New — managed add-on **or** custom image (F) |
| Redis | Railway | New — managed add-on |

## D. Required Environment Variables

Full table with exact names and purpose: `specs/deployment.md` §15.3. Summary by category:

- **Backend + worker (identical set):** `DATABASE_URL`, `REDIS_URL`, `JWT_SIGNING_KEY`, `ENVIRONMENT`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_BASE_URL`, `BACKEND_PUBLIC_BASE_URL`, `STORAGE_PROVIDER` (+ its credentials), `LOG_LEVEL`, `LLM_PROVIDER`/`ANTHROPIC_API_KEY`, `EMBEDDING_PROVIDER`/`OPENAI_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`, `SMTP_*`, `EMAIL_FROM_ADDRESS`/`EMAIL_PROVIDER`, `DOCUMENT_PROCESSING_STALE_THRESHOLD_SECONDS`, `STORAGE_PRESIGNED_URL_EXPIRES_IN_SECONDS`.
- **Vercel (unchanged):** `INTERNAL_API_URL` (now points at the Railway backend's public domain), `NEXT_PUBLIC_API_BASE_URL` (still unused, per R12).

## E. Secrets Checklist

**Must be supplied as Railway/Vercel secret environment variables, never committed:**
- `DATABASE_URL` (contains the Postgres password)
- `REDIS_URL` (contains the Redis password)
- `JWT_SIGNING_KEY` — **the local-dev default in `config.py` is explicitly insecure; a real deploy must never use it**
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
- `SMTP_USERNAME`, `SMTP_PASSWORD`
- `STORAGE_ACCESS_TOKEN` / `STORAGE_ACCESS_KEY_ID` / `STORAGE_SECRET_ACCESS_KEY` (once OQ-04 resolves)
- `RAILWAY_TOKEN` (as a **GitHub Actions** repository secret, for CI's deploy-gate step — not an application runtime variable)

**Non-secret configuration** (real values, but not credentials): `ENVIRONMENT`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_BASE_URL`, `BACKEND_PUBLIC_BASE_URL`, `LOG_LEVEL`, `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `EMAIL_PROVIDER`, `EMAIL_FROM_ADDRESS`, `DOCUMENT_PROCESSING_STALE_THRESHOLD_SECONDS`, `STORAGE_PRESIGNED_URL_EXPIRES_IN_SECONDS`.

**Must never be committed anywhere in the repository** (verified — none are): any of the secret values above, in any form, in any file including `.env.example` (which correctly contains only placeholders, re-verified this pass by reading both `.env.example` files in full — no change was needed).

## F. Docker/Deployment Configuration Status

- **Backend/worker Dockerfile: deployable to Railway unmodified.** No Railway-specific fork was created or is needed — Railway's "Deploy from Dockerfile" mode plus a per-service Start Command override is sufficient, exactly mirroring `docker-compose.yml`'s existing `backend`/`worker` split.
- **Frontend Dockerfile: not applicable to Railway** — it remains local-dev-parity-only (`ADR-006`); production frontend hosting is Vercel, unchanged.
- **`.github/workflows/ci.yml` updated**: the previously Fly.io-shaped conditional deploy-gate step (`FLY_API_TOKEN`) now checks for `RAILWAY_TOKEN`, preserving the exact same "builds and pushes to GHCR unconditionally, deploys only if the secret exists" safety behavior `ADR-019` established — no functional deploy occurs from this change; the step remains a documented placeholder until the secret is actually provisioned.
- **Two genuine compatibility points found, not silently resolved** (both documented in `deployment.md` §15.4, both must be verified/decided before the first migration runs against the real Railway Postgres):
  1. Railway's auto-generated Postgres `DATABASE_URL` uses `postgresql://`; this codebase's async SQLAlchemy engine needs `postgresql+asyncpg://`. **Resolution is a Railway variable-configuration step, not a code change** — set the backend/worker services' `DATABASE_URL` explicitly using Railway's variable-reference syntax against the Postgres service's individual connection components, with the correct scheme prepended.
  2. Whether Railway's managed Postgres template ships the `pgvector` extension **could not be verified without a live Railway account**. Recommended safe path: deploy Postgres as a custom Docker image service using `pgvector/pgvector:pg16` — the exact image already used and tested in `docker-compose.yml` — rather than assuming the managed template includes it.
- **A third, separate blocker, independent of OQ-13:** `STORAGE_PROVIDER` has only one real implementation (`local`, R12's own hardening), and `local` writes to the container's own filesystem — not durable, not shared, unsuitable for real production use regardless of which platform hosts the container. `decisions.md` OQ-04 (cloud storage provider) remains open and is **not resolved by this pass** — flagged clearly as a pre-launch requirement, not silently worked around.

## G. Database Migration Procedure

Unchanged mechanism from the existing Production Launch Runbook (`deployment.md` §14.2), Railway-specific instantiation in §15.8:

1. Provision the Railway Postgres service (managed or custom image — see F).
2. **Before running any migration**, verify `pgvector` is available (`CREATE EXTENSION vector;` succeeds) and set `DATABASE_URL` with the correct `postgresql+asyncpg://` scheme (F, items 1–2).
3. The `backend` service's Start Command must be `sh -c "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"` (matching `docker-compose.yml`'s override — the bare Dockerfile CMD has no migration step by design, since that's a Compose/platform-level override, not baked into the image).
4. Keep the `backend` service at a single instance until the "N racing replicas running migrations concurrently" question is revisited, or move migration to a dedicated Railway pre-deploy step if scaling to 2+ instances before then.

**Can migrations safely run against Railway Postgres?** Yes, once items F.1 and F.2 are verified/configured — the migration chain itself (`alembic upgrade head`) is platform-agnostic and already verified clean (`alembic heads == current == 0004_search_tsvector`, re-confirmed this pass) against the local dev Postgres. Nothing about the migrations themselves is Railway-specific; only the connection string and extension availability need confirming against the real instance.

## H. RQ Worker Configuration

**Verified safe, unmodified.** The `worker` Railway service uses the identical `backend/Dockerfile` image with its Start Command overridden to `rq worker document_processing extraction comparison summary --url $REDIS_URL` — exactly `docker-compose.yml`'s existing, already-validated pattern (RQ's own default forking `Worker` class, correct for Railway's Linux containers, unlike the Windows-only workarounds this session's local smoke-testing needed). No code change was made or is needed. Note: a real, separately-running `rq worker` process consuming a live queue has still never been empirically verified anywhere in this project's history (`final-release-audit.md`'s finding, `release-closure-plan.md` item #5) — this remains true after this pass; Railway deployment is expected to be the first real-world verification of it, not a substitute for verifying it pre-launch if that's preferred (see Remaining Blockers).

## I. Frontend/Backend Connectivity Configuration

- `INTERNAL_API_URL` (Vercel, server-only) → the Railway backend service's public domain.
- `CORS_ALLOWED_ORIGINS` (Railway backend/worker) → the real Vercel production domain(s), never a wildcard.
- **Cookies/CORS risk is smaller than a naive cross-platform reading suggests**, confirmed by R12's own finding: the BFF proxy (`frontend/app/api/v1/[...path]/route.ts`) relays every request — including the chat SSE stream — same-origin from the browser's perspective. The browser never calls the Railway origin directly for anything except a presigned storage upload (once OQ-04 resolves). `Set-Cookie` headers the browser actually receives are scoped to the Vercel domain, not Railway's, so there is no classic cross-origin auth-cookie failure mode between Vercel and Railway specifically — `CORS_ALLOWED_ORIGINS`/cookie `secure`/`SameSite` settings are still required (defense-in-depth, and Next.js's own server-side call to Railway is a real cross-service call), but getting them wrong doesn't break the primary user-facing auth flow the way it would in a direct-browser-to-backend architecture.
- HTTPS: Railway terminates TLS automatically for its service domains and custom domains — no additional app-side configuration beyond `ENVIRONMENT=production` (enables `secure` cookies and HSTS in `request_context_middleware`).

## J. OAuth Production Configuration

**Non-obvious pitfall, documented clearly to prevent a real mistake:** `backend/app/api/v1/routers/auth.py` constructs the Google OAuth `redirect_uri` from `settings.frontend_base_url`, not the backend's own domain — because the callback request is expected to land on the frontend's BFF proxy first, then be forwarded to FastAPI, exactly like every other request. **The Google Cloud Console "Authorized redirect URI" must be set to `https://<production-frontend-domain>/api/v1/auth/oauth/google/callback` — the Vercel domain, not the Railway domain.** Registering the Railway domain will break OAuth entirely. This behavior predates the Railway decision and is unchanged by it; flagged here because it's the single easiest mistake a reader would otherwise make.

## K. Remaining Blockers

1. **The actual Railway project/services/secrets have not been provisioned** — this pass is documentation and configuration-readiness only, per your explicit instruction not to deploy.
2. **`pgvector` availability on Railway's managed Postgres is unverified** — must be checked against the real instance, or sidestepped entirely by deploying Postgres as a custom `pgvector/pgvector:pg16` image (recommended).
3. **`DATABASE_URL` scheme must be set explicitly** — do not bind directly to Railway's auto-generated Postgres reference.
4. **OQ-04 (storage provider) remains open and is a real launch blocker independent of OQ-13** — `STORAGE_PROVIDER=local` is not viable for real production use. This was not resolved by this pass (out of scope — you asked to close OQ-13, not OQ-04) but is flagged prominently because it will block real users regardless of how well the Railway setup itself goes.
5. **Standalone `rq worker` verification remains unverified anywhere** — Railway deployment will be the first real-world test of it; consider treating the first deploy's worker service as the verification event itself, or verify it earlier via Docker/CI if you'd rather de-risk before the first real deploy (unchanged from `release-closure-plan.md`'s prior assessment).
6. **Google OAuth / SMTP / real LLM+embedding provider credentials** are all still unset (all default to safe-but-non-functional fake/unconfigured providers) — fine for an initial deploy that doesn't yet need real AI calls, real email, or real Google sign-in, but each is a real prerequisite for that specific feature to work for real users.

## L. Exact Deployment Steps To Execute Next

**Not executed this pass — listed for your approval before I (or you) proceed:**

1. Create the Railway project; add the `postgres` service (decide: managed add-on vs. `pgvector/pgvector:pg16` custom image — recommend the latter for certainty) and the `redis` service.
2. Verify `pgvector` is available on the provisioned Postgres instance (`CREATE EXTENSION vector;`).
3. Create the `backend` Railway service: connect this repository, set Root Directory to `backend/`, confirm it builds from `backend/Dockerfile`, set Start Command to `sh -c "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"`.
4. Create the `worker` Railway service: same repository/Dockerfile, Start Command `rq worker document_processing extraction comparison summary --url $REDIS_URL`.
5. Set every variable from §D/E on both `backend` and `worker` — `DATABASE_URL` composed explicitly with the `postgresql+asyncpg://` scheme (not bound directly to Railway's own reference), `REDIS_URL` bound directly to the Redis service reference.
6. Update Vercel's `INTERNAL_API_URL` to the Railway backend's public domain.
7. If launching with real Google OAuth: register the redirect URI in Google Cloud Console as the **Vercel** domain + `/api/v1/auth/oauth/google/callback` (§J), then set `GOOGLE_OAUTH_CLIENT_ID`/`SECRET`.
8. Add `RAILWAY_TOKEN` as a GitHub Actions repository secret once you want CI's deploy-gate step to actually mean something (still just a documented placeholder today).
9. First deploy → run `deployment.md` §14.3's post-deploy verification (health check, adapted smoke test, structured-log confirmation).
10. Resolve OQ-04 (storage provider) before onboarding real users, independent of the above.

---

## Local Validation Results (this pass)

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
| `.github/workflows/ci.yml` YAML syntax | Valid (re-checked after edits) |

No live Docker build/run was possible (daemon unresponsive, unchanged environment constraint, unrelated to Railway). No Railway-specific validation was possible without a live account, per this pass's explicit no-deploy instruction.

## Git Status — Every Modified File

```
 M .github/workflows/ci.yml       (Fly.io → Railway deploy-gate rename, no functional deploy change)
 M specs/decisions.md             (OQ-13 resolved to Railway, changelog entry)
 M specs/deployment.md            (new §15 Railway Deployment Configuration; §14.5 updated)
?? tasks/release-closure-plan.md  (from the PRIOR turn — still uncommitted, untouched this pass)
?? tasks/railway-deployment-readiness-report.md   (this report)
```

**No commit was made.** No push occurred. No deployment was performed or attempted — Docker daemon was not invoked for any build/run, no Railway API/CLI call was made. No R13 or new product-development task was created. No application behavior was modified — every change is either a specification/documentation update (`decisions.md`, `deployment.md`) or a CI configuration rename that preserves its existing inert-until-secret-provisioned safety property (`ci.yml`). The two genuine compatibility risks found (Postgres URL scheme, `pgvector` availability) were surfaced and documented, not silently patched into application code, per your explicit instruction.

Awaiting your review and explicit approval before any commit, Railway provisioning, or deployment step.
