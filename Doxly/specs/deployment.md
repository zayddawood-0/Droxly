# Doxly — Deployment Architecture

> Defines how Doxly is deployed to production. Complements `decisions.md` (ADR-007: the Vercel/container split; ADR-009: presigned uploads) and `architecture.md` (service topology, environments table). `devops.md` owns local dev tooling and the CI build/test pipeline; this file owns **production topology and runtime configuration** — cross-referenced, not duplicated.

## 1. Topology recap

Per ADR-007: **Next.js frontend → Vercel. FastAPI backend + background worker → long-running containers on a container platform** (default recommendation: Fly.io or Railway for early stage; AWS ECS/Fargate as the scale-up path). This is not a stylistic choice — it is required by the execution-time and process-durability constraints of Vercel serverless functions, detailed in §12 below.

```mermaid
graph TB
    subgraph Vercel["Vercel (Production)"]
        NextFrontend[Next.js Frontend<br/>SSR + Route Handlers - BFF<br/>CDN + automatic HTTPS]
    end

    subgraph Platform["Container Platform — Fly.io / Railway (MVP) → AWS ECS/Fargate (scale-up)"]
        API1[FastAPI Replica 1..N<br/>long-lived ASGI process]
        LB{{Load Balancer /<br/>Platform Ingress}}
        Worker1[Worker Replica 1..N<br/>RQ consumer, long-lived process]
        LB --> API1
    end

    subgraph Data["Managed Data Layer"]
        PG[(Managed PostgreSQL<br/>+ pgvector extension)]
        Redis[(Managed Redis<br/>queue + rate limit)]
        Blob[(Vercel Blob<br/>S3-compatible interface)]
    end

    subgraph External["External Providers"]
        LLM[Anthropic Claude<br/>LLM provider]
        Embed[OpenAI<br/>embedding provider]
        OAuth[Google OAuth]
        Mail[Transactional Email]
    end

    Browser((Browser)) -->|HTTPS| NextFrontend
    Browser -.->|Direct presigned upload/download| Blob
    NextFrontend -->|REST, cookie relay| LB
    API1 --> PG
    API1 --> Redis
    Worker1 --> Redis
    Worker1 --> PG
    Worker1 --> Blob
    Worker1 --> LLM
    Worker1 --> Embed
    API1 --> LLM
    API1 --> OAuth
    API1 --> Mail
```

**Reading this diagram:** Vercel hosts exactly one thing — the Next.js frontend. Everything that holds a database connection, consumes a queue, or calls an AI provider for more than a token-stream lives on the container platform or as managed infrastructure outside Vercel entirely. This mirrors `architecture.md` §1's request-flow diagram, redrawn here for *where things run* rather than *how a request flows*.

## 2. Next.js deployment (Vercel)

- **Deploy trigger:** push to `main` → production deploy; every open PR → an isolated preview deploy (per `architecture.md`'s Environments table), both via Vercel's native Git integration — no custom deploy scripting needed for the frontend.
- **Static assets & CDN:** built assets (JS bundles, images, fonts) are served from Vercel's Edge Network automatically; no separate CDN configuration required.
- **Environment variables:** configured per-scope in the Vercel dashboard (Production / Preview / Development), never committed to the repo. Two classes:
  - `NEXT_PUBLIC_*` prefixed — bundled into client-side JavaScript, visible to anyone. Only non-secret values belong here (e.g., `NEXT_PUBLIC_API_BASE_URL` for the FastAPI origin used by client-side fetches, if any occur outside route handlers).
  - Unprefixed — server-only, available in Route Handlers and Server Components, never sent to the browser. Anything remotely sensitive (backend service tokens, internal URLs) must be unprefixed.
  - **Rule:** a secret must never be assigned to a `NEXT_PUBLIC_*` variable. This is a code-review gate, not just a convention.
- **Execution limits:** Vercel serverless (and Edge) functions have hard execution-time ceilings (commonly in the 10–60 second range depending on plan/runtime) and no durable background-process model — a function either returns within its window or is killed. This is why Next.js Route Handlers exist purely as a thin BFF: forward the request to FastAPI, relay the response/cookies, nothing else. No document parsing, no LLM chains, no polling loops live inside a Vercel function.

## 3. FastAPI backend deployment (container platform)

- **Build:** a container image is built in CI (see `devops.md`) and pushed to a registry; the platform deploys the image, not source code directly.
- **Scaling:** minimum 2 replicas in production for availability (`NFR-SCALE-001`), fronted by the platform's load balancer.
- **Health checks:** a lightweight `/health` endpoint (DB connectivity + basic liveness, no auth required, no sensitive data returned) is polled by the platform's orchestrator to route traffic only to ready replicas and restart unhealthy ones.
- **Graceful shutdown:** on deploy/restart, a replica stops accepting new connections but finishes in-flight requests (bounded grace period) before terminating, so a rolling deploy never drops an active chat stream mid-response.

## 4. Background worker deployment

- **Separate deployable** from the API, with its own replica count (`NFR-SCALE-002`) — request volume and processing volume do not correlate, so coupling their scaling would be wasteful in one direction and starved in the other.
- **Scaling heuristic:** for MVP, worker replica count is set manually based on observed queue depth/backlog; a documented future enhancement is autoscaling workers when the Redis queue depth (per ADR-008) exceeds a threshold for a sustained period.
- **Why it isn't on Vercel:** a worker process is designed to run for as long as a job takes — a 50-page PDF pipeline or a multi-node LangGraph extraction run can take well beyond any serverless execution ceiling. Running it as a long-lived container process (not a request/response cycle) is the entire point of ADR-008/ADR-007; it has no timeout ceiling imposed by the platform, only the application-level job timeout defined in `ai.md`/`langgraph.md`.

## 5. Environment variables in production

The full variable inventory is §5.1 below; `devops.md` covers how these are supplied in CI and local `.env` files. In production specifically:
- All backend/worker secrets are injected by the container platform's secret store, never baked into the image.
- Distinct values per environment (dev/preview/prod) — a leaked preview key must not grant access to production data or a shared production LLM budget.
- The Next.js side only ever needs the public API base URL and any `NEXT_PUBLIC_*` display-only flags — it holds no provider or database credentials at all, by design (it never talks to them directly, per `architecture.md` §1).

### 5.1 Environment variable inventory

Names and purpose only — no real values are recorded in any spec file. Actual values live in Vercel's env store (frontend) and the container platform's secret store (backend/worker), per-environment (`devops.md` covers how these are set in CI).

| Variable | Where it lives | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Frontend / Vercel | Reserved, currently unused (R12 correction: `app/api/v1/[...path]/route.ts` proxies every request, including the chat SSE stream, same-origin — the browser never calls the FastAPI origin directly, matching §1's topology diagram) |
| `NEXT_PUBLIC_*` (display-only flags) | Frontend / Vercel | Any other non-secret, browser-visible config (e.g., feature flags safe to expose) |
| `INTERNAL_API_URL` | Frontend / Vercel (server-only, unprefixed) | Origin the Next.js Route Handler (BFF) calls server-side; may differ from the public URL |
| `DATABASE_URL` | Backend + Worker | Managed PostgreSQL connection string (SSL required, §6) |
| `REDIS_URL` | Backend + Worker | Managed Redis connection (job queue + rate-limit store, ADR-008) |
| `JWT_SIGNING_KEY` | Backend | Secret used to sign/verify access + refresh JWTs (ADR-010) |
| `ANTHROPIC_API_KEY` | Backend + Worker | LLM provider credential (ADR-011) |
| `OPENAI_API_KEY` | Backend + Worker | Embedding provider credential (ADR-012) |
| `STORAGE_PROVIDER` | Backend + Worker | Which `StorageProvider` implementation to load (`blob`, `s3`, `r2`, …) |
| `STORAGE_ACCESS_TOKEN` / `STORAGE_ACCESS_KEY_ID` + `STORAGE_SECRET_ACCESS_KEY` | Backend + Worker | Credentials for the configured storage provider (shape depends on provider) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Backend | Google OAuth2 app credentials (ADR-010, OQ-01) |
| `CORS_ALLOWED_ORIGINS` | Backend | Comma-separated list of origins permitted to call the API (§11) |
| `EMAIL_PROVIDER_API_KEY` | Backend | Transactional email provider credential (verification, password reset) |
| `LOG_LEVEL` | Backend + Worker | Per-environment log verbosity (§9) |

## 6. PostgreSQL connection

- **Managed Postgres with pgvector enabled.** This is a hosting requirement to verify explicitly when selecting a provider — not every managed Postgres offering ships the `pgvector` extension enabled by default. Candidate providers (Neon, Supabase, Railway Postgres, or AWS RDS for PostgreSQL with the extension explicitly enabled) each support `pgvector`, but availability, version, and index type support (HNSW requires a sufficiently recent `pgvector` version — `database.md` §4) must be confirmed for the specific provider and plan tier chosen before committing. This is flagged as an infra choice to confirm at implementation time, not silently assumed, consistent with `decisions.md`'s open-question pattern.
- **Connection pooling:** both the API (≥2 replicas, many short-lived request-scoped connections) and the worker (N replicas, fewer but longer-lived job connections) hold DB connections concurrently. For MVP replica counts this is unlikely to exhaust Postgres's default connection limit, but PgBouncer (or the managed provider's built-in pooler, e.g., Neon's or Supabase's pooled connection string) is the documented scaling step once replica count grows — flagged as a scaling concern, not an MVP blocker.
- **SSL required** for all production database connections; no unencrypted connections accepted.

## 7. File storage in production

- Vercel Blob is the default production object store (`decisions.md` OQ-04), configured with production-scoped credentials.
- **Presigned URL generation happens in FastAPI**, not Next.js — FastAPI is the sole authorization authority (ADR-010) and is what decides whether a given user may create a new upload slot (quota check, plan check). The Next.js route handler that the browser calls is a pass-through proxy to that FastAPI endpoint.
- **The actual file bytes never transit Vercel or FastAPI**: the browser uploads directly to Blob storage using the presigned URL (see `architecture.md`'s Document Processing Flow sequence diagram), which is what keeps large uploads compatible with Vercel's body-size limits (§12) and off the FastAPI request path entirely.
- **Provider is a config change, not a code change:** because storage is accessed exclusively behind the `StorageProvider` interface (`decisions.md` ADR-009), moving from Vercel Blob to S3 or Cloudflare R2 later (e.g., for cheaper egress at scale, OQ-04) means implementing/enabling a new `StorageProvider` and flipping the `STORAGE_PROVIDER` environment variable — no changes to the document-processing pipeline, API routes, or business logic that call the interface.

## 8. AI provider configuration

- LLM and embedding provider API keys are backend/worker secrets exclusively — the frontend never holds or calls these directly, eliminating any path for a provider key to leak into a client bundle (`NFR-SEC-008`, `requirements.md`).
- **Per-environment keys:** where the provider supports scoped/separate API keys (both Anthropic and OpenAI do), production, preview, and local dev each use distinct keys. This isolates cost/quota accounting per environment and, more importantly, means a bug in a preview deployment (e.g., an infinite LangGraph retry loop) cannot burn production spend or trip a production rate/quota alert.
- **Recommended safety net beyond app-level limits:** configure a monthly spend cap / budget alert at the provider account level (Anthropic/OpenAI account settings) in addition to the application's own rate limiting (`decisions.md` OQ-08). App-level limits protect against a single account's runaway usage; the provider-level cap protects against a systemic bug or attack pattern the app-level limiter didn't anticipate.

## 9. Build configuration

- **Next.js:** standard Vercel-managed Next.js build output (SSR + Route Handlers) — no static export mode, since the app relies on server-rendered/dynamic routes and API proxying.
- **FastAPI:** the production container runs multiple ASGI worker processes behind the platform's ingress (the standard Uvicorn-workers-behind-a-process-manager pattern, or an equivalent multi-worker ASGI runner) — the exact process count is a per-environment tuning parameter, not a fixed spec value.
- **Configuration source:** all environment-specific values come from injected environment variables; no environment-specific config files are committed to the repository.

## 10. Production configuration — what differs by environment

Beyond the environment-variable *values* already covered in §5, the following behavioral settings are intentionally different per environment (local / preview / production, per `architecture.md` §7), not just different secrets:

| Setting | Local | Preview | Production |
|---|---|---|---|
| Log verbosity (`LOG_LEVEL`) | `debug` | `info` (or `debug` for active investigation) | `info`/`warning` — verbose enough for `observability.md` needs, not so verbose it's costly/noisy at volume |
| Rate limiting (`decisions.md` OQ-08) | Relaxed/disabled for fast local iteration | Same policy as production (catches limiter bugs before release) | Full policy enforced |
| AI model tier | Cheapest available model regardless of quality, to keep iteration cheap | Cheaper/faster model tier by default (e.g., Haiku-class over Sonnet-class) to bound preview AI spend, unless a PR specifically needs production-quality output to review | Production-configured model tier per `ai.md`'s model-selection table (ADR-011/012, OQ-02/03) |
| CORS allowed origins | `localhost` dev ports | Preview deployment's Vercel-generated domain pattern | Locked to the exact production frontend domain(s) only — no wildcards (§11) |
| AI provider API keys | Local/dev key (own quota) | Preview key (own quota, §8) | Production key (own quota, §8) |

**Why this matters:** without an explicit per-environment model-tier and rate-limit policy, it is easy to accidentally run preview traffic against production-cost models and production-strictness limits (wasteful) or, worse, run production against preview-relaxed limits (a security/cost gap). This table exists so that distinction is a deliberate configuration choice, not an accident of whatever the last environment variable set happened to be.

## 11. Production hardening

- **CORS:** FastAPI's CORS policy allows only the known production Vercel domain(s) (and preview-deployment domains via a pattern match scoped to the project, if preview environments call a shared staging API) — never a wildcard origin in production.
- **HTTPS-only** end to end: Vercel terminates TLS for the frontend by default; the container platform's ingress must terminate TLS (or sit behind one that does) for the backend, with HTTP-to-HTTPS redirect enforced.
- **Security headers:** the specific header list (CSP, HSTS, X-Content-Type-Options, frame-ancestors) is owned by `security.md` (`NFR-SEC-011`) — applied at the FastAPI response layer and/or Vercel edge config; not redefined here.

## 12. Vercel limitations — why the split exists (explicit, central statement)

This section exists because the initialization brief explicitly warns against assuming long-running processing can execute synchronously in a serverless request. The concrete limitations that drove ADR-007:

1. **Execution time limits.** Vercel serverless/Edge functions terminate after a fixed window; document parsing, embedding generation, and multi-node LangGraph runs routinely exceed it for non-trivial documents.
2. **No durable background-worker primitive.** Vercel has no first-class mechanism for a process that outlives a single invocation and consumes a queue — which is exactly the execution model document processing and background AI workflows need.
3. **Request body size limits.** Proxying file uploads through a Vercel function is impractical past a small size ceiling — solved entirely by the direct-to-storage presigned upload pattern (§7), which means no uploaded file ever needs to fit inside a Vercel function's request body in the first place.
4. **Cold starts on what should be a persistent, DB-connected process.** A serverless invocation model adds cold-start latency to anything it hosts; that's a bearable inconvenience for a thin proxy, but the FastAPI/worker layer specifically wants a long-lived, warm process that holds a pooled DB connection (§6) and, for the worker, a standing Redis queue subscription — a model fundamentally at odds with per-invocation serverless execution, independent of the raw latency number.

**Resulting design rule:** *Vercel hosts presentation and quick proxying only. Anything that can take more than a few seconds, must survive longer than one HTTP request/response cycle, or wants a persistent connection to Postgres/Redis, runs in the container platform via the Redis job queue.* This is why "the app is deployed on Vercel" is only ever true of the frontend — a reader should not infer from that statement that the API, worker, database, or AI processing run there too.

## 13. Long-running AI processing & background processing — how the queue satisfies the constraint

Restating the mechanism from `decisions.md` ADR-008 and the sequence diagrams in `architecture.md` §4–5, specifically through the lens of the Vercel constraint above: any operation that cannot complete within a single fast HTTP round trip (document processing, summarization, extraction, comparison) is enqueued to Redis by a quick FastAPI call and executed by the container-hosted worker, which has no timeout ceiling beyond the application-level job timeout defined in `ai.md`/`langgraph.md`. The one exception is the Document Q&A chat workflow, which streams token-by-token inline from the FastAPI container (also not Vercel) over SSE — still outside Vercel's execution model, just synchronous rather than queued, because it needs to stream to the client rather than run fully in the background.

**Client-side UX implication (`FR-DOC-008`):** since the client cannot simply hold open one long-lived HTTP call to Vercel for a background job, the UI polls a status endpoint (or subscribes via SSE served from the FastAPI container) to reflect pipeline stage transitions (`queued → extracting → chunking → embedding → ready`) as they happen, rather than blocking on a single request until processing finishes.

## 14. Production Launch Runbook

Added by `tasks/remediation-plan.md` R12 (Production Deployment Readiness) — the "Production Launch Runbook" §15 named as a still-to-build deliverable. Written against what R1–R12 actually built and verified; it does not invent a container-platform choice `decisions.md` OQ-13 leaves open, and does not claim a step is done that this repository has not actually performed.

### 14.1 Prerequisites (must be true before starting)

- [ ] A container platform is chosen and its config committed (`decisions.md` OQ-13 resolved — e.g. `fly.toml` or a Railway service definition). **Not yet done** as of R12 — this blocks every step below that says "deploy the backend/worker image."
- [ ] Managed Postgres provisioned with the `pgvector` extension enabled and confirmed (§6), reachable only over SSL.
- [ ] Managed Redis provisioned (§5.1).
- [ ] Every secret in §5.1's inventory has a real production value in the platform's secret store — `backend/.env.example` documents the full variable list; none of its values are usable as-is in production (`JWT_SIGNING_KEY`'s local default is explicitly insecure — see `app/core/config.py`).
- [ ] `CORS_ALLOWED_ORIGINS` set to the exact production frontend origin(s) — never a wildcard (§11).
- [ ] `STORAGE_PROVIDER` set to a real implementation. **As of R12, `local` is the only `StorageProvider` implementation that exists** (`decisions.md` OQ-04 is still open) — `app/core/storage.py`'s `get_storage_provider()` raises `RuntimeError` for any other value rather than silently falling back, so this is a hard deploy blocker, not a soft warning, until a real cloud provider is implemented.
- [ ] DNS/TLS configured for the backend's public origin (container platform ingress) and the frontend's Vercel domain.

### 14.2 Deploy sequence

1. **CI builds and pushes images.** `.github/workflows/ci.yml`'s existing lint → typecheck → test → build pipeline produces the backend/worker image (shared, `backend/Dockerfile`) and pushes it to GHCR; the `deploy` job is currently gated on `FLY_API_TOKEN`/`DATABASE_URL` secrets being present and no-ops cleanly without them (confirmed by reading the workflow directly).
2. **Backend replicas start.** The platform runs the pushed image with its default `CMD` — `alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` is the local/Compose equivalent (`docker-compose.yml`; the Dockerfile's own default `CMD` binds the same way but without the migration step — see §15.8); the production platform's own start command should apply migrations once (not once per replica racing each other — a documented platform-specific concern, e.g. a Fly.io release command or a dedicated one-off migration step) before traffic-serving replicas start. **Never run `alembic upgrade head` concurrently from N racing replicas.**
3. **Worker replicas start**, same image, command overridden to `rq worker document_processing extraction comparison summary --url $REDIS_URL` (exactly `docker-compose.yml`'s `worker` service, with GHCR's image instead of a local build).
4. **Health check gates traffic.** The platform's orchestrator polls `GET /health` (§3) before routing live traffic to a new replica and before considering a deploy successful — confirm the platform's health-check path/interval is actually configured to point at `/health`, since a missing/misconfigured check silently defeats the zero-downtime-deploy guarantee this section otherwise describes.
5. **Frontend deploys via Vercel's Git integration** (§2) — independent of the backend/worker deploy above; there is no ordering dependency for a routine deploy (the frontend calls whatever backend version is currently live), but a **breaking API contract change** must ship the backend first and the frontend second, same as any client/server versioned API.

### 14.3 Post-deploy verification

1. `curl https://<backend-origin>/health` returns `{"status": "ok"}`.
2. Run `backend/scripts/smoke_test.py` (R12's scripted smoke-test deliverable) against the deployed origin — **as written, it targets a locally-spawned `uvicorn`/`rq worker` pair for a live-local run; pointing it at a real deployed environment requires supplying that origin instead of spawning local subprocesses**, a follow-up adaptation explicitly not made in this revision (see the R12 readiness report's own distinction between "live local" and "actual production" verification levels — this script has only been run in the former mode).
3. Confirm the P0 golden path manually or via the adapted smoke test: register → login → upload → processing reaches `ready` → chat produces a cited answer → summarization/extraction/comparison each reach `completed` → search returns tenant-scoped results.
4. Check the platform's log stream for `request.completed`/`job.completed`/`job.failed` structured log lines (`app/core/logging.py`, `app/workers/_observability.py`) — confirms structured JSON logging is actually active in the deployed environment, not just locally.

### 14.4 Rollback

- **Frontend:** Vercel's own instant-rollback-to-previous-deployment feature (dashboard or CLI) — no application-specific steps needed.
- **Backend/worker:** redeploy the previous known-good image tag from GHCR. A rollback that also needs to reverse a database migration is a separate, higher-risk operation — `devops.md`'s migration-authoring guidance (write reversible migrations where practical) is what makes this possible at all; a rollback plan that assumes forward-only migrations were the only kind ever written is not safe to rely on without checking the specific migration involved.
- **Never** roll back the backend image without checking whether the currently-applied migration is still compatible with the older code — a rollback that reintroduces code expecting a pre-migration schema against an already-migrated database is a self-inflicted outage.

### 14.5 What this runbook does not yet cover

Documented explicitly rather than silently omitted, per this task's own instruction not to overclaim completeness:
- The actual Railway project/service provisioning and first real deploy (`OQ-13` is resolved to Railway — see §15 — but no account has been provisioned and no deploy has occurred).
- A load test against a production-scale seeded dataset (`backend/scripts/load_test.py` exists and has been run against a live-local instance only — see the R12 readiness report).
- An automated, CI-triggered smoke test against a real staging/production environment (today it is a manually-invoked script).

## 15. Railway Deployment Configuration

Added by the release-closure pass that resolved `decisions.md` OQ-13. This section is the Railway-specific instantiation of §1's topology and §14's runbook — it does not repeat what's identical to any container platform (health checks, graceful shutdown, the runbook's deploy sequence shape); it covers what's specific to Railway or was discovered while checking Railway-specific compatibility.

### 15.1 Service topology on Railway

One Railway **project** containing four services:

| Service | Image/source | Start command | Public networking |
|---|---|---|---|
| `backend` | `backend/Dockerfile`, unmodified | Railway's Start Command override (see §15.8) — `sh -c "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`; binds to Railway's injected `$PORT`, falling back to 8000 only if unset | Public domain (Railway-generated `*.up.railway.app` or a custom domain) — this is what Vercel's `INTERNAL_API_URL` points at |
| `worker` | Same `backend/Dockerfile`, same build context | Overridden: `rq worker document_processing extraction comparison summary --url $REDIS_URL` | None — never reachable from outside the project, exactly like `docker-compose.yml`'s `worker` service |
| `postgres` | Railway's managed PostgreSQL **or** a custom Docker image deploy of `pgvector/pgvector:pg16` — see §15.4 for why this choice isn't yet finalized | N/A (managed) | Private networking only (`*.railway.internal`) |
| `redis` | Railway's managed Redis | N/A (managed) | Private networking only |

The **Next.js frontend is not a Railway service** — per `ADR-007` (unchanged), it continues to deploy to Vercel. "Railway architecture" for the frontend is: nothing runs there. `frontend/Dockerfile` remains what `ADR-006` always scoped it for — local `docker-compose` dev-parity only, not a production deploy target.

### 15.2 Can the existing Dockerfiles deploy directly?

**Backend/worker: yes, unmodified.** Railway's "Deploy from Dockerfile" mode builds `backend/Dockerfile` as-is; the `worker` service is the same image with only its Start Command overridden in Railway's dashboard/config, mirroring `docker-compose.yml`'s own `backend`/`worker` split exactly (`ADR-007`'s "same codebase, same dependency layer, differing only in the container's entrypoint command"). No Railway-specific Dockerfile fork is needed or was created.

**Frontend: not applicable** — it deploys to Vercel, not Railway (§15.1).

### 15.3 Required environment variables per service

Names and purpose only, per `deployment.md` §5's existing convention — no real values recorded here.

**`backend` and `worker` (identical set — both need every variable either might read):**

| Variable | Value on Railway | Secret? |
|---|---|---|
| `DATABASE_URL` | **Do not bind directly to Railway's auto-generated Postgres `DATABASE_URL` reference** — see §15.4. Must be set explicitly with the `postgresql+asyncpg://` scheme. | Secret (contains the DB password) |
| `REDIS_URL` | Bind directly to Railway's Redis service reference (`${{Redis.REDIS_URL}}`) — format is already compatible, no scheme issue (§15.5). | Secret |
| `JWT_SIGNING_KEY` | A real, random secret — **the local-dev default in `config.py` is explicitly insecure and must never be used in production.** | **Secret** |
| `ENVIRONMENT` | `production` — this is what flips `secure=True` on session/CSRF cookies (`_cookies_secure()`/`request_context_middleware`'s HSTS-enabling check) and disables the local-dev-only local-storage router (`app/main.py`'s `if settings.storage_provider == "local"` mount). | Non-secret config |
| `CORS_ALLOWED_ORIGINS` | The real Vercel production frontend domain(s) — never a wildcard. See §15.6 for why this matters less than it would in a non-BFF architecture, but still must be set correctly as defense-in-depth per `security.md`. | Non-secret config |
| `FRONTEND_BASE_URL` | The real Vercel production frontend origin — used to construct the Google OAuth `redirect_uri` (§15.9) and any email links. | Non-secret config |
| `BACKEND_PUBLIC_BASE_URL` | The Railway backend service's own public domain — used only for `LocalFilesystemStorageProvider`'s presigned URLs, which are **not** the production storage path (§15.4's sibling concern — see `STORAGE_PROVIDER` below). | Non-secret config |
| `STORAGE_PROVIDER` | **A separate, still-open blocker, independent of OQ-13/Railway.** `local` is the only implemented `StorageProvider` (`app/core/storage.py`'s `get_storage_provider()` raises `RuntimeError` for any other value, R12) — `decisions.md` OQ-04 (cloud storage provider choice) is still open. `local` writes to the container's own filesystem, which does not persist across a Railway redeploy/restart and is not the durable, shared storage a real production deployment needs. **Do not launch to real users with `STORAGE_PROVIDER=local`** — this must be resolved (OQ-04 decided, a real provider implemented) before production launch, regardless of the Railway decision. | N/A until OQ-04 resolves and a real provider is implemented |
| `LOG_LEVEL` | `info` or `warning` | Non-secret config |
| `LLM_PROVIDER` / `ANTHROPIC_API_KEY` | `anthropic` / a real API key, once ready to use real LLM calls (defaults to `fake` otherwise, which is safe but non-functional for real users) | Secret (API key) |
| `EMBEDDING_PROVIDER` / `OPENAI_API_KEY` | `openai` / a real API key, same caveat as above | Secret (API key) |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Real Google Cloud OAuth client credentials, once Google OAuth is wanted in production (defaults to `oauth_not_configured` responses otherwise, which is safe) | Secret |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | Real SMTP relay credentials, once email verification/reset should actually deliver mail (defaults to `FakeEmailProvider`, safe but non-functional for real users) | Secret (username/password) |
| `EMAIL_FROM_ADDRESS` | The real sending address | Non-secret config |
| `EMAIL_PROVIDER` | `smtp` once the above is configured | Non-secret config |
| `STORAGE_ACCESS_TOKEN` / `STORAGE_ACCESS_KEY_ID` / `STORAGE_SECRET_ACCESS_KEY` | Credentials for whichever real `StorageProvider` OQ-04 eventually resolves to | Secret |
| `DOCUMENT_PROCESSING_STALE_THRESHOLD_SECONDS` | `900` (the tested default) unless deliberately tuned | Non-secret config |
| `STORAGE_PRESIGNED_URL_EXPIRES_IN_SECONDS` | `900` (the tested default) unless deliberately tuned | Non-secret config |

**Vercel (frontend) — unchanged by this decision, restated for completeness:**

| Variable | Value | Secret? |
|---|---|---|
| `INTERNAL_API_URL` | The Railway `backend` service's public domain | Non-secret (server-only, but not a credential) |
| `NEXT_PUBLIC_API_BASE_URL` | Reserved, unused — see `frontend/.env.example`'s own comment (R12) | N/A |

### 15.4 Database: two things that must be verified before the first migration runs, not assumed

1. **Connection string scheme.** Railway's managed Postgres add-on exposes `DATABASE_URL` in the bare `postgresql://user:pass@host:port/db` form. This codebase's `app/core/database.py` uses SQLAlchemy's **async** engine, which requires the `postgresql+asyncpg://` scheme — a bare `postgresql://` URL will fail to connect (the sync `psycopg2` dialect would accept it, but nothing in this codebase uses that dialect). **Do not bind the backend/worker services' `DATABASE_URL` directly to Railway's auto-generated Postgres reference.** Instead, set it explicitly using Railway's variable-reference syntax against the Postgres service's individual connection-component variables, e.g. `postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}` (exact variable names to confirm against the actual provisioned Postgres service's "Variables" tab — Railway's naming has been consistent but should be checked against the live instance, not assumed from documentation alone).
2. **`pgvector` extension availability.** Every migration that touches `document_chunks.embedding` runs `CREATE EXTENSION IF NOT EXISTS vector` (`alembic/versions/20260821_phase3_remaining_schema.py`) — this **activates** the extension per-database but requires the extension's compiled files to already exist on the Postgres server. `docker-compose.yml`'s local Postgres uses the `pgvector/pgvector:pg16` image specifically because standard Postgres images don't ship it. **Whether Railway's managed PostgreSQL template includes `pgvector` could not be verified without a live Railway account in this pass** — `deployment.md` §6 already flagged this exact class of risk generically ("not every managed Postgres offering ships the `pgvector` extension enabled by default"), and this is that risk made concrete for the chosen platform. **Recommended safe path if the managed template doesn't include it:** deploy Postgres on Railway as a custom Docker image service using `pgvector/pgvector:pg16` (Railway supports deploying any Docker image as a service, not only its own managed database templates) — this exactly matches the already-tested local/CI image, eliminating the question entirely rather than hoping the managed template happens to include it.

Neither of these was silently resolved — both require a decision/verification step against the real, provisioned Railway Postgres instance before `alembic upgrade head` is run there for the first time.

### 15.5 Redis

Railway's managed Redis add-on exposes `REDIS_URL` as `redis://default:password@host:port` — this is directly compatible with `redis.asyncio.from_url()` (used by `app/core/rate_limit.py`, `app/core/chat_stream_control.py`, `app/core/queue.py`) with no scheme translation needed, unlike Postgres. Bind the backend/worker services' `REDIS_URL` directly to Railway's Redis reference variable.

### 15.6 CORS, cookies, and why the BFF pattern changes what actually matters here

`app/main.py`'s `CORSMiddleware` and `security.md`'s cookie requirements (httpOnly, `secure` when not `environment=local`, `SameSite=Lax`) are unchanged by this decision and must still be configured correctly (`CORS_ALLOWED_ORIGINS` set to the real Vercel domain, `ENVIRONMENT=production` on Railway). **But the actual risk this protects against is smaller than a naive cross-origin-deployment reading would suggest**, confirmed by R12's own BFF-proxy finding: `frontend/app/api/v1/[...path]/route.ts` proxies every request — including the chat SSE stream — same-origin from the browser's perspective. The browser only ever talks to Vercel; it never calls the Railway backend origin directly for anything except a presigned storage upload (`deployment.md` §7, once a real `StorageProvider` exists). This means the `Set-Cookie` header the browser actually receives is scoped to the **Vercel** domain, not Railway's — there is no cross-origin cookie problem to solve between Vercel and Railway specifically. `CORS_ALLOWED_ORIGINS`/cookie `secure`/`SameSite` settings remain required (defense-in-depth, and Next.js's own server-side `fetch` to Railway is still a real cross-service call `security.md` cares about), but getting them "wrong" in a Vercel+Railway split does not create the classic browser-side cross-origin auth-cookie failure mode a reader might expect.

### 15.7 HTTPS

Railway terminates TLS for its public service domains by default (and for any attached custom domain, via automatic certificate provisioning) — matching `deployment.md` §11's "the container platform's ingress must terminate TLS" requirement with no additional configuration needed on the application side beyond `ENVIRONMENT=production` enabling `secure` cookies and HSTS (`app/main.py`'s `request_context_middleware`).

### 15.8 Migrations on Railway

Per §14.2's existing "never run `alembic upgrade head` concurrently from N racing replicas" guidance (unchanged by this decision): Railway does not have a first-class "release phase" step distinct from the running service the way some platforms do, so the safest pattern — matching `docker-compose.yml`'s own `backend` service exactly — is the `backend` service's start command running migrations before starting `uvicorn`: `sh -c "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`. This is **not** the Dockerfile's own baked-in default `CMD` — that CMD binds uvicorn to `${PORT:-8000}` but runs no migration step (`sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`), the same way `docker-compose.yml`'s own `backend` service overrides it with the migrate-then-serve variant rather than relying on the image default. Railway needs this same migrate-then-serve `sh -c` wrapper configured explicitly as the `backend` service's Start Command — using the image's bare default CMD on Railway would start serving traffic against a not-yet-migrated schema. With Railway's default of one instance for the `backend` service at MVP scale, the "N racing replicas" concern is theoretical until `NFR-SCALE-001`'s 2-replica minimum is actually configured — worth setting the replica count to 1 until the migration-race question is revisited, or moving to a dedicated Railway "pre-deploy command" (a feature Railway has offered in various forms) if scaling to 2+ backend replicas before this is addressed further.

### 15.9 OAuth production configuration — a non-obvious pitfall specific to the BFF split

`backend/app/api/v1/routers/auth.py`'s `oauth_google_start`/`oauth_google_callback` both construct `redirect_uri = f"{settings.frontend_base_url}{OAUTH_CALLBACK_PATH}"` — **the redirect URI Google is told to use is the frontend's (Vercel) domain, not the backend's (Railway) domain**, even though FastAPI is what ultimately handles the callback (the request lands on Vercel, then the BFF proxy forwards `/api/v1/*` to Railway, same as every other request). **The Google Cloud Console OAuth client's "Authorized redirect URI" must therefore be set to `https://<production-frontend-domain>/api/v1/auth/oauth/google/callback` — registering the Railway domain instead will break OAuth entirely.** This behavior predates this ADR and is not changed by the Railway decision; it's flagged here because it's the single easiest mistake to make when a reader's mental model assumes "the backend's own domain" for an OAuth callback.

### 15.10 What remains before an actual Railway deploy can happen

Per this pass's explicit instruction not to deploy: none of the following was done, only documented as the next concrete steps —
1. Create the Railway project and its four services (§15.1).
2. Resolve §15.4's two Postgres verification points against the real provisioned instance.
3. Set every variable in §15.3, with real secret values from a password manager/secrets vault — never typed into chat or committed to any file.
4. Register the correct Google OAuth redirect URI (§15.9), if Google OAuth is wanted at launch.
5. Point Vercel's `INTERNAL_API_URL` at the real Railway backend domain once it exists.
6. Run the Production Launch Runbook's existing §14.2 deploy sequence and §14.3 post-deploy verification.
