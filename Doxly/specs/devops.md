# Doxly — DevOps Specification

> Defines HOW the team builds, tests, and ships Doxly: local development via Docker Compose, Git branching/PR workflow, the CI pipeline, and the database migration workflow. This file owns process and local-environment mechanics. `deployment.md` owns WHERE things run in production (Vercel specifics, container platform choice, per-environment variable inventory, Vercel limitations) — refer there for production topology. `security.md` owns the deeper secrets-management requirements (NFR-SEC-008); this file covers the DevOps mechanics of how secrets are injected per environment. `database.md` §5 owns Alembic migration authoring conventions; this file covers the review/deploy workflow around them.

## 1. Docker Architecture

Per ADR-006 (`decisions.md`), every service runs in Docker, both locally and (for backend/worker) in production. Per `architecture.md` §2.3, FastAPI and the background worker share the same application image — same codebase, same dependency layer — differing only in the container's entrypoint command (HTTP server vs. queue consumer), so dependencies are built once, not duplicated across two images.

| Service | Base image family | Purpose | Key env vars | depends_on |
|---|---|---|---|---|
| `next-app` | Node LTS | Next.js frontend (dev only — production is Vercel, not this container; see `deployment.md`) | `NEXT_PUBLIC_API_URL`, `NEXTAUTH_*`/session-cookie config | `fastapi-app` |
| `fastapi-app` | Python (slim) | REST API, auth, synchronous CRUD, inline streaming AI calls | `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `LLM_PROVIDER_API_KEY`, `EMBEDDING_PROVIDER_API_KEY`, `STORAGE_*` | `postgres`, `redis` |
| `worker` | Python (slim) — same image as `fastapi-app`, different entrypoint | Consumes the RQ queue: document processing, embedding generation, non-streaming LangGraph workflows | same env vars as `fastapi-app` (shared config surface) | `postgres`, `redis` |
| `postgres` | Official `pgvector/pgvector` image (Postgres 14+ with the extension preinstalled) | System of record: relational data + embeddings (ADR-003) | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | — |
| `redis` | Official Redis image | RQ job queue, rate-limit token buckets (ADR-008) | — (no auth needed for local dev; production config in `deployment.md`) | — |

Using the `pgvector/pgvector` base image (rather than plain `postgres` + a manual extension install step) keeps the pgvector version pinned and identical across every developer's machine and CI, avoiding the classic "works on my machine" drift for a native-code extension.

### 1.1 Frontend image hardening (`roadmap.md` Phase 17)

`frontend/Dockerfile`'s runtime (`runner`) stage applies two hardening steps beyond the baseline non-root multi-stage build, both verified by actually running the built image, not inferred from reading the Dockerfile:

- **`apk upgrade --no-cache`** patches the base `node:22-alpine` image's own system packages (e.g. libssl/libcrypto) to whatever CVE fixes exist upstream as of build time, rather than freezing at whatever the base image tag was published with.
- **The base image's bundled global `npm`/`npx` are removed** (`rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx`). The container starts via `node server.js` directly — npm is never invoked at runtime — but `node:22-alpine` ships a full npm install (and npm's own transitive dependencies) regardless. A `docker scout cves` scan of the unpatched image found 16 vulnerabilities (1 critical, 8 high) across 6 packages, every one traced to `/usr/local/lib/node_modules/npm/...`; removing it brought the scan to zero findings across the image's remaining 98 packages. This is the standard fix for this class of finding on Node base images, not a Doxly-specific workaround — re-verify with `docker scout cves` after any base-image bump, since a future Node release could change what's bundled.

The image's `HEALTHCHECK` (`wget --spider` against the app's own root path) targets `127.0.0.1:3000` explicitly, never `localhost:3000` — Alpine's resolver returns the IPv6 loopback (`::1`) for `localhost` first, but `HOSTNAME=0.0.0.0` only binds the IPv4 wildcard, so a `localhost`-based healthcheck connection-refuses even though the server is genuinely up and serving traffic on the mapped port. This was caught by actually running the built image and inspecting `docker inspect`'s health-check log, not by reading the Dockerfile — the same class of bug a real container run catches that static review doesn't.

### 1.2 Backend/worker image hardening (`roadmap.md` Phase 18, closing a Phase 17 gap)

`roadmap.md` Phase 17's own objective named "Production-grade Docker images ... for backend/worker/frontend," but the task actually executed for Phase 17 (`tasks/17-docker.md`) scoped itself to the frontend image only — no `backend/Dockerfile` existed until Phase 18, which needed one as a genuine prerequisite for its own "build & push image" CD step and therefore built it here rather than leaving CI/CD un-implementable. `backend/Dockerfile` is a multi-stage, non-root build (`python:3.12-slim`, a `builder` stage that creates a venv and `pip install`s the package, a `runner` stage that copies only the venv + `app/`/`alembic/`) — the same non-root/hardening posture as `frontend/Dockerfile`, applied to the Debian-slim base instead of Alpine:

- **`apt-get upgrade`** patches the base image's own system packages, same rationale as §1.1's `apk upgrade`.
- **`perl-base` is purged** after `addgroup`/`adduser` run (both are themselves Perl scripts on Debian, so removal has to happen after user/group creation, not before) — a real `docker scout cves` finding: `python:3.12-slim` ships it as a Debian "Essential" package, nothing this container runs invokes it, and no other installed package depends on it (verified: `apt-cache rdepends --installed perl-base` returns nothing). It carried 2 CRITICAL + 1 HIGH CVE with no upstream fix at build time; purging it brought the scan to 0 CRITICAL/0 HIGH. Same class of "bundled-but-unused base-image weight" finding as §1.1's npm removal, different package.
- **Healthcheck** uses `python -c "...urllib.request..."` against `/health` rather than `curl`/`wget` — neither ships in `python:3.12-slim` by default, and the interpreter that's already in the image is enough to probe one endpoint without adding a package solely for that purpose.

**One image, two roles, one role not yet runnable:** per `architecture.md` §2.3, this single image is meant to serve both the FastAPI HTTP server and the background worker, differing only in the container's entrypoint command. The image's `CMD` runs the API (`uvicorn app.main:app`); **no worker entrypoint module exists in this codebase yet** (`roadmap.md` Phase 5/8 scope — an RQ queue consumer — was never implemented; confirmed by inspecting `backend/app/` before writing this Dockerfile: no `worker.py`, no queue/job module, and no `rq`/`redis` dependency in `pyproject.toml`). This is a pre-existing gap from earlier phases, not something Phase 18 introduced or is scoped to fix (see `tasks/18-ci-cd.md`'s Implementation Notes) — the CD workflow's backend deploy step therefore only ever runs the API process; a worker-process deploy step is not wired until that entrypoint exists.

## 2. Docker Compose (Local Development)

A single `docker-compose.yml` at the repo root composes all five services described above. Conceptually, it provides:

- **Hot-reload volumes** for `next-app` and `fastapi-app`: the host source tree is mounted into each container so `next dev` and FastAPI's auto-reloading dev server pick up file changes without an image rebuild. `worker` shares the same mounted source as `fastapi-app` since it's the same image.
- **A local Postgres with pgvector**, migrated automatically on startup (see §3) so a fresh clone reaches a working schema without a manual step, and optionally seeded with representative sample data (documents, a demo user) for UI development.
- **Redis**, unauthenticated locally, giving the worker and API something to enqueue/dequeue against immediately.
- **An `.env.example` pattern**: the repository commits `.env.example` with every variable the compose stack needs, each set to a placeholder or obviously-fake value — never a real secret. Each developer copies it to a gitignored `.env` and fills in their own (or a shared team dev-only) API keys. This mirrors the secrets principle in `security.md` (NFR-SEC-008): nothing that grants access ever lives in source control, even for "just local dev" convenience.
- **Service isolation with a shared network**: containers reach each other by service name (`fastapi-app` calls `postgres:5432`, not `localhost`), matching how the same code addresses managed services in production (`deployment.md`), which is the core value of ADR-006's dev/prod parity goal.

## 3. Development Environment Workflow

A new contributor gets a fully running stack through the following steps:

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in the required values — for local dev, most default to safe placeholders (DB credentials, JWT signing secret can be any local value); LLM and embedding provider API keys must be real (a shared team dev key or the contributor's own) since AI features call out to live providers even in local dev.
3. Bring up the full stack via the Compose entrypoint (a documented `make`/npm script wraps the underlying `docker compose up` invocation so contributors don't need to memorize flags).
4. On first startup, database migrations run automatically against the local Postgres container before the API becomes ready to serve traffic — a new contributor never has to run a manual migration command just to get to a working schema. The same startup step also seeds optional sample data (a demo user, a couple of processed documents) when a `SEED_DB` flag is set, useful for frontend/UI work without needing to upload real files.
5. The contributor confirms the stack is healthy by hitting the frontend and API health-check endpoints, then begins work with hot-reload active on both `next-app` and `fastapi-app`.
6. When the contributor pulls new changes that include an Alembic migration, restarting the stack (or re-running the migration step alone) brings their local schema up to date — migrations are idempotent and additive per `database.md` §5, so this is safe to run repeatedly.

No production credentials, staging database access, or real user data are ever part of this workflow — local dev is fully self-contained against the Dockerized Postgres/Redis instances.

## 4. Git Workflow

**Decision: GitHub Flow** — short-lived feature branches off `main`, opened as a pull request, merged back into `main` once approved and green.

- **Branching:** every change (feature, fix, chore) starts as a branch off `main`, named descriptively (e.g., `feat/document-comparison`, `fix/chunk-index-race`). Branches are expected to live hours-to-days, not weeks — long-lived branches accumulate merge conflicts and drift from the CI pipeline's assumptions.
- **Pull requests required:** direct pushes to `main` are not the normal path. Every change lands via a PR, which is where CI runs (§5) and review happens.
- **Review:** at least one approving review is required before merge. For a small early-stage team this is deliberately lightweight — one reviewer, not a multi-stage approval chain — chosen to keep velocity high while still catching correctness issues, tenant-isolation regressions (`architecture.md` §6), and spec drift before they reach `main`.
- **CI must pass:** the full pipeline (§5) must be green on the PR before merge is allowed.
- **Merge strategy:** squash-merge is preferred. Each feature branch's many small commits (WIP, fixups, review-response commits) collapse into one clean commit on `main`, keeping `main`'s history readable and making `git bisect`/rollback straightforward.

**Why GitHub Flow over trunk-based-with-feature-flags or Git Flow:** the team is small and early-stage, with a single deployable environment sequence per service (dev → preview → production, `architecture.md` §7) rather than multiple parallel release trains. Git Flow's `develop`/release-branch ceremony solves a coordination problem this team doesn't have yet; full trunk-based development with per-commit production deploys and feature flags is a heavier discipline than an early product needs. GitHub Flow's single long-lived branch plus ephemeral feature branches, backed by Vercel's automatic PR preview deployments (`architecture.md` §7, `deployment.md`), gives fast iteration with a real review gate.

## 5. CI Pipeline (GitHub Actions)

CI runs on every pull request (and again on merge to `main`, as the trigger for CD in §6), implemented as `.github/workflows/ci.yml` (`roadmap.md` Phase 18, `decisions.md` ADR-019). The pipeline is staged so that fast, cheap checks fail early before expensive ones run:

```mermaid
flowchart LR
    A[Lint] --> B[Type-check]
    B --> C[Test<br/>unit + integration]
    C --> D[Build]
    D --> E{Deploy gate<br/>on main only}
    E -->|frontend| F[Vercel auto-deploy]
    E -->|backend/worker| G[Build & push image]
```

**Stages:**

1. **Lint:** frontend — ESLint only (`npx eslint .`; no auto-fix in CI, violations fail the build). **Spec correction made in this phase:** this stage previously read "ESLint + Prettier check," but the frontend has never had Prettier installed or configured (verified: no `.prettierrc*`, no `prettier` in `package.json`/`eslint.config.mjs`) — ESLint alone has been this project's actual formatting/lint gate since Phase 1. Corrected here per `CLAUDE.md`'s SDD rule 3 (resolve a spec/implementation mismatch explicitly, not silently) rather than retrofitting Prettier onto the whole codebase as an unplanned Phase 18 side effect. Backend — `ruff check .` + `black --check .`.
2. **Type-check:** frontend — `tsc --noEmit`; backend — `mypy app --ignore-missing-imports` against the FastAPI/SQLAlchemy codebase (`mypy` added as a backend dev dependency in this phase — it was specified here but not yet wired to any dependency or CI job before Phase 18). Enforces the "validate everything at the boundary" and typed-contract principles that `api.md`'s generated OpenAPI schema and `database.md`'s SQLAlchemy models depend on.
3. **Test (unit + integration) + migration check:** `alembic upgrade head` runs first against a fresh ephemeral Postgres (a `pgvector/pgvector:pg16` GitHub Actions service container, matching `docker-compose.yml`'s image) and Redis service container, proving migrations apply cleanly from empty — the "migration-check (per-PR)" task named in `roadmap.md` Phase 18. `pytest` then runs the full backend suite (`backend/tests/`, including `test_migrations.py`'s own upgrade/downgrade round-trip, all LangGraph node tests, and the tenant-isolation tests) against that database, and `vitest run` runs the full frontend suite. Both use the "fake" `LLMProvider`/`EmbeddingProvider` implementations (`core/config.py`'s default) — no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` secret is required for this job. What the suite covers is defined in `testing.md`; this pipeline stage is the trigger point, not the source of truth for coverage.
4. **Build:** frontend — `next build`, confirming the production bundle compiles cleanly; backend — `docker build` for `backend/Dockerfile` (§1.2), confirming the shared `fastapi-app`/`worker` image builds successfully; the frontend image (§1.1) is also built here as a Compose/dev-parity check even though production frontend is Vercel-deployed, not this container. A build failure here blocks merge even if tests passed, catching build-time-only issues (env var access patterns, static generation errors).
5. **Deploy gate (main only):** the preceding four stages must all succeed. This stage does not run on PR branches — it is the hinge between CI and CD, described in §6.

**Explicitly out of scope for CI:** CI never applies migrations to a production or staging database (step 3's migration check runs only against the ephemeral CI database, never a real environment), and never deploys anything itself. It only proves the code is lintable, type-safe, tested, and buildable, then hands off to CD. Migration application to production is an explicit, reviewed deploy step (§8, `deployment.md`), not something that happens as a side effect of a green CI run.

**Slower tiers deliberately not in this per-PR workflow:** the Playwright E2E suite and the AI golden-set regression tier (`testing.md` §4.7, §7) run in a separate scheduled workflow — see §6.1.

## 6. Continuous Deployment

CD is triggered automatically by CI success on `main` — never a manual "click to deploy" step, and never triggered from a feature branch. Implemented as the `deploy` job in the same `.github/workflows/ci.yml` (`decisions.md` ADR-019), gated `if: github.ref == 'refs/heads/main' && github.event_name == 'push'` so it only ever runs after the lint/type-check/test/build stages have already passed on that exact commit — never on a PR branch, and never skipping straight to deploy.

- **Frontend:** Vercel's native GitHub integration deploys the `next-app` on every push to `main` that passes CI, using Vercel's own build pipeline (which independently re-runs `next build`). Preview deployments for open PRs are a separate, always-on Vercel behavior independent of this main-branch CD flow. **This is not a GitHub Actions step** — it requires a human with Vercel dashboard access to connect the repository once (Root Directory setting → `frontend/`), a one-time manual action outside what a workflow file can perform; `ci.yml`'s `deploy` job logs this explicitly rather than silently doing nothing.
- **Backend/worker:** on merge to `main`, `ci.yml`'s `deploy` job (1) runs `alembic upgrade head` against the production `DATABASE_URL` secret — **before** the image deploy, per `roadmap.md` Phase 18's explicit "migration-then-deploy ordering" requirement — then (2) builds and pushes the shared application image (§1.2) to GHCR (`decisions.md` ADR-019), tagged with the commit SHA and `latest`, then (3) triggers the container platform's deploy of that image, gated on a platform-specific secret being present (`decisions.md` OQ-13 — the platform itself isn't chosen/provisioned yet, so step 3 currently no-ops with a clear log message rather than failing the pipeline). Both the migration step and the image push are also individually gated on `DATABASE_URL`/registry-push prerequisites being available, so a repository without production secrets configured yet gets a clean, informative skip rather than a red CI run.

### 6.1 Nightly workflow (E2E + AI regression)

Implemented as `.github/workflows/nightly.yml` (`roadmap.md` Phase 18's "E2E/AI-eval (nightly)" task) — scheduled via cron (03:00 UTC daily) plus `workflow_dispatch` for an on-demand manual run, deliberately not on every PR (`testing.md` §7's "the AI golden-set regression suite may run as a separate, slower CI job ... rather than blocking every PR"). Two jobs:

- **`e2e`:** `npx playwright test` against the full `frontend/e2e/*.spec.ts` suite. `playwright.config.ts`'s own `webServer` block builds and starts the Next.js app itself (`npm run build && npm run start` on port 3100) — no separate server-startup step needed in the workflow. **Current interim scope, matching `testing.md`'s own documented state** (§3's "Current interim state" note): no real backend router exists yet for most domains (`devops.md` §1.2 / `tasks/18-ci-cd.md`), so this job runs the E2E suite exactly as it exists today — the connectivity-error-path and route-smoke specs described in `testing.md` §3 — not a fabricated "full golden path against a real backend" that the application can't yet serve. The suite will need no workflow change once real backend routers land; it already runs the full `e2e/` directory.
- **`ai-eval`:** re-runs the backend's LangGraph node test files (`test_graph_document_qa.py`, `test_graph_summarization.py`, `test_graph_extraction.py`, `test_graph_comparison.py`) as the current stand-in for `testing.md` §4.7's golden-set regression tier. **Known gap, not fabricated as complete:** `testing.md` §4.5/§4.6's curated hallucination/prompt-injection golden test sets (fixture files pairing adversarial/should-decline questions with expected behavior) do not exist in this codebase yet — `roadmap.md` Phase 16 ("expand the golden document/query/extraction set ... wire the nightly AI-eval workflow") named building that content as in-scope, but only the workflow-wiring half is done here; the graph node tests these use mocked `FakeLLMProvider` responses, so they verify graph control-flow and schema validation, not actual model-output quality against curated adversarial cases. This job satisfies Phase 18's "wire the nightly AI-eval workflow" deliverable on the current test content; backfilling `testing.md` §4.5/§4.6's actual golden-set fixtures remains open, tracked as a `tasks/18-ci-cd.md` follow-up rather than expanded into this phase.

## 7. Secrets & Environment Variables

**Principle:** secrets are never committed to source control. `.env` files are gitignored everywhere (local dev, CI runners, build agents); `.env.example` documents every required key by name with a placeholder or obviously-fake value only. The deeper secrets-management requirements — rotation, least-privilege scoping, what counts as a secret — are specified in `security.md` (NFR-SEC-008). This section covers only the DevOps mechanics of injection per environment:

| Environment | Where secrets live | How they reach the running process |
|---|---|---|
| Local dev | Developer's own `.env` (gitignored) | Read by Docker Compose and injected as container env vars |
| CI (GitHub Actions) | GitHub Actions encrypted repository/environment secrets | Injected into the workflow run as env vars for the job that needs them (e.g., a dev-tier LLM key for integration tests that exercise the provider abstraction) |
| Frontend production/preview | Vercel project environment variables (scoped per environment: Production/Preview/Development) | Vercel injects them at build and runtime automatically via its GitHub integration |
| Backend/worker production | Container platform's secret store | Injected as environment variables into the running container at deploy time; exact mechanism per platform is detailed in `deployment.md` |

No secret is ever baked into a built image or a committed config file — it is always supplied at runtime by the platform holding it for that environment.

## 8. Database Migrations Workflow

Migration **authoring conventions** (one migration per logical change, never edited after merge, `pgvector` extension + HNSW index created in the initial migration) are defined in `database.md` §5 and are not repeated here. This section defines the workflow around them:

1. **Written alongside the model change:** an Alembic migration is authored and committed in the same PR as the SQLAlchemy model change that requires it — never generated and applied ad hoc against a running database, and never as a separate follow-up PR that could land out of order with the code that depends on the new schema.
2. **Reviewed as part of the PR:** the migration file is part of the normal code review (§4) — reviewers check the migration is additive/backward-compatible where possible, and that any destructive change carries the rollback note required by `database.md` §5.
3. **Tested in CI against a fresh database:** the CI test stage (§5) runs migrations from scratch against the ephemeral CI Postgres before the test suite executes, proving the migration applies cleanly and the resulting schema matches what the tests (and the ORM models) expect. This also catches migrations that only work against a database that already has manually-applied state.
4. **Applied to production as an explicit, reviewed deploy step — not automatically:** unlike the frontend/backend image deploy (§6), migrations are not run as an unattended side effect of every merge to `main`. Applying a migration to the production database is a deliberate, logged action taken as part of the deploy process, giving a human the chance to sequence it correctly relative to the application deploy (e.g., additive-first for zero-downtime changes) and to intervene if it fails partway. The exact production migration execution mechanism (who/what runs `alembic upgrade head`, in which step of the deploy sequence) is specified in `deployment.md`.
5. **Never run directly against production outside this path:** no one applies a migration by hand against the production database outside the logged deploy step, even for "small" schema fixes — a corrective change is itself a new migration, following the same PR → review → CI → deploy path.

## 9. Traceability

| Concern | Spec |
|---|---|
| Docker service split rationale | `decisions.md` ADR-006, ADR-007, ADR-008 |
| Shared FastAPI/worker image | `architecture.md` §2.3 |
| Production deploy topology, Vercel specifics, per-environment variable inventory | `deployment.md` |
| Secrets-management requirements (NFR-SEC-008) | `security.md` |
| Migration authoring conventions, pgvector/HNSW setup | `database.md` §5 |
| Test suite composition and coverage | `testing.md` |
