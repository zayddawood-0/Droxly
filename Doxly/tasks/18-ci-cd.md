# Task 18: CI/CD Pipeline

## Task ID
P18-001

## Feature
DevOps — Full CI/CD Pipeline (per-PR gate + nightly slow tier + deploy-on-main)

## Objective
Deliver `roadmap.md` Phase 18 in full: a GitHub Actions pipeline that lints, type-checks, tests, and builds every PR and every push to `main` (blocking merge on failure per `devops.md` §5), a nightly workflow for the slower E2E/AI-regression tiers, and a deploy-on-main flow that applies database migrations before deploying the backend/worker image, ordered per `roadmap.md`'s explicit "migration-then-deploy ordering" requirement. Frontend deploy is Vercel's own GitHub integration (not a workflow step); backend/worker deploy is a GitHub Actions job that pushes to GHCR and, once a platform secret exists, deploys to the container platform.

## Specification References
- `roadmap.md` Phase 18 — "Full CI/CD pipeline: all test tiers wired with correct cadence (per-PR vs nightly), CD to Vercel (frontend) and the container platform (backend/worker) on merge to `main`" — the objective this task implements in full.
- `devops.md` §5–§6, §6.1 (new), §1.2 (new) — CI pipeline stages, CD flow, and the backend/worker image hardening this phase's CD step depends on; all updated in this task to describe what was actually built (see Implementation Notes for what changed vs. what was already accurate).
- `decisions.md` ADR-019 (new) — the registry (GHCR) and workflow-shape decisions this task required and that weren't previously made.
- `decisions.md` OQ-13 (new) — the one thing this task could not resolve (which container platform actually hosts backend/worker) because it requires human dashboard/billing access.
- `testing.md` §3 ("Current interim state"), §7 (CI integration contract), §4.5–§4.7 (golden-set tiers) — the testing-side contract this pipeline has to satisfy, including its already-documented statement that no real backend router exists yet for most domains.
- `deployment.md` §1–§2, §9 — production topology this CD flow targets (Vercel for frontend, container platform for backend/worker).
- `architecture.md` §2.3 — the shared FastAPI/worker image this task's Dockerfile builds.

## Requirements
None directly (`roadmap.md` Phase 18: "Requirements fulfilled: None directly — operational readiness"), matching Phase 17's same framing.

## Dependencies
- Phase 16 (Testing) — the test suite this pipeline runs.
- Phase 17 (Docker) — the frontend image this pipeline builds; **this task also had to build the backend/worker image Phase 17 didn't**, since Phase 18's "build & push image" CD step has nothing to build/push without it (see Implementation Notes — identified as a genuine, minimal prerequisite, not a scope expansion).

## Files Affected
- `backend/Dockerfile` — new — multi-stage, non-root backend/worker image (the Phase 17 prerequisite gap).
- `backend/.dockerignore` — new — keeps the build context minimal (`.venv/`, `tests/`, caches excluded).
- `backend/pyproject.toml` — modified — added `mypy` to `dev` extras + a `[tool.mypy]` config block (devops.md §5 specified a backend type-check stage since Phase 1; it was never wired to a dependency or a job until this task).
- `backend/app/repositories/base.py` — modified — a `_TenantScopedModel` Protocol replaces the plain `Base` bound on `TenantScopedRepository`'s generic, resolving 5 real `mypy` errors (`Base` doesn't declare `id`/`user_id`, but every tenant-scoped subclass's `model` does) surfaced by wiring the new mypy CI stage. No behavior change — purely a typing fix.
- `backend/app/ai/llm.py` — modified — `cast(T, next_response)` in `FakeLLMProvider.generate_structured`, resolving 1 real mypy error (a test double returning a general `BaseModel` where the generic `T` was expected). No behavior change.
- `backend/app/ai/graphs/summarization.py` — modified — `_quality_router` now explicitly routes a `None` `quality_check_result` to `"fail"` before accessing `.passed`, resolving 1 real mypy `union-attr` error. This is a genuine (if unreachable in the graph's current wiring) null-safety fix, not a suppression.
- `.github/workflows/ci.yml` — new — the per-PR/push-to-main pipeline (lint → type-check → test+migration-check → build → deploy-on-main).
- `.github/workflows/nightly.yml` — new — scheduled E2E + AI-regression tiers.
- `specs/devops.md` — modified — §1.2 (backend image hardening), §5/§6 rewritten to describe the actual implemented pipeline (including a spec correction: "ESLint + Prettier" → "ESLint" — Prettier was never actually part of this project), new §6.1 (nightly workflow).
- `specs/decisions.md` — modified — new `ADR-019` (GHCR + workflow-shape decision) and `OQ-13` (container platform destination, left open).

## Implementation Notes

### The Phase 17 gap this task had to close (minimum-necessary prerequisite, not scope creep)
Verified before writing any workflow file: `roadmap.md` Phase 17's own objective line names "backend/worker/frontend" images, but `tasks/17-docker.md` is explicitly titled "(Frontend)" and only ever touched `frontend/Dockerfile`. No `backend/Dockerfile` existed. Phase 18's roadmap task line ("GitHub Actions workflows for ... build ... and container-platform deploy workflow") cannot be implemented without something to build — a backend image is a hard prerequisite, not an optional nice-to-have, for the "Build" and "deploy-backend" stages `devops.md` §5's own mermaid diagram already specifies. Per this session's instructions ("implement only the minimum prerequisite necessary if it is genuinely required for Phase 18"), `backend/Dockerfile` was built to the same hardening bar as the frontend image (§1.2), verified by actually building and running it (not just reading it): `docker build` succeeds, the container runs non-root, `/health` returns `200`, `docker inspect .State.Health` reaches `healthy`, and `docker scout cves` went from 2 CRITICAL/2 HIGH (both traced to the base image's unused `perl-base`, verified via `apt-cache rdepends`) to 0 CRITICAL/0 HIGH after purging it (full detail in `devops.md` §1.2).

### A larger, pre-existing gap found during verification — explicitly NOT fixed here
Verifying Phases 2–14 before starting (per this session's instructions) surfaced that `backend/app/main.py` contains only the Phase 1 `/health` endpoint — **no `APIRouter` exists anywhere in `backend/app/`, and `main.py` has zero `include_router` calls.** Every auth, document, chat, extraction, comparison, search, and analytics endpoint `api.md` specifies is unimplemented at the HTTP layer, even though the underlying service/repository/LangGraph-graph logic for most of them is real and tested. This is **not a Phase 18 regression** — it's a pre-existing gap spanning Phases 2, 4, and 9–14, and `testing.md` §3's "Current interim state" paragraph already documents it explicitly ("no real backend router exists yet for most domains ... every request the frontend makes genuinely fails at the BFF proxy ... This is a documented, temporary substitution"). Similarly, no RQ worker consumer module exists (`roadmap.md` Phase 5/8 scope) despite `pyproject.toml` never having gained an `rq` dependency.

Fixing either gap would mean re-implementing the HTTP layer for roughly eight roadmap phases' worth of features — wildly outside "CI/CD pipeline" scope, and exactly the kind of silent scope expansion this session's instructions explicitly prohibit ("do not silently expand scope"). This task instead **designed the pipeline to be correct against what actually exists today**: the backend test suite (which exercises services/repositories/graphs directly, not via HTTP, so it's unaffected by the missing routers), the frontend E2E suite (which `testing.md` §3 already documents as testing the connectivity-error path against the real, router-less backend), and Docker builds that don't depend on any endpoint being wired. `devops.md` §1.2 and §6.1 both document this gap at the point where it affects the pipeline's design (the backend Dockerfile's `CMD`, and the nightly E2E job's "current interim scope" note) so a future contributor sees it in context, not just in this task file. **This is flagged as the single largest follow-up item for whichever phase/task takes ownership of it** — recommended to be addressed before Phase 19 (Production Deployment), since a production launch with no working API beyond `/health` would not meet Phase 19's "Doxly is live and usable end to end in production" Definition of Done.

### CI pipeline design (`.github/workflows/ci.yml`)
Implements `devops.md` §5's mermaid diagram exactly: `lint` → `typecheck` → `test` (which also runs the migration-check, since `alembic upgrade head` against a fresh ephemeral Postgres already proves migrations apply cleanly before `pytest` runs against that schema) → `build` → `deploy` (gated `if: github.ref == 'refs/heads/main' && github.event_name == 'push'`). Frontend and backend run as parallel job-internal steps within each stage rather than fully separate job graphs, keeping the four-stage shape readable in the Actions UI while still failing fast (a `lint` failure in either language skips every later stage). Backend test/migration steps use GitHub Actions `services:` (`pgvector/pgvector:pg16`, `redis:7-alpine`) — the same images `docker-compose.yml` uses — rather than invoking Compose itself, which is the standard, lower-overhead GitHub Actions pattern for ephemeral service dependencies (`devops.md` §5 stage 3's own language: "matching the local Compose stack," not "via the local Compose stack").

No `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` secret is required for the `test` job — `core/config.py`'s `llm_provider`/`embedding_provider` default to `"fake"`, and that's what every currently-existing test (including the LangGraph node tests) is written against.

### Deploy job specifics
- **Migration-then-deploy ordering** (`roadmap.md` Phase 18's explicit requirement): the `deploy` job's first step is `alembic upgrade head` against a `secrets.DATABASE_URL`, before any image build/push step runs. If that secret isn't set (true for this repository today — no production database is provisioned), the step is skipped with an explicit log line rather than failing the job, so the pipeline stays green and honest about what it did and didn't do.
- **GHCR push**: uses `secrets.GITHUB_TOKEN` (always available, `packages: write` permission declared on the job) — no additional secret provisioning needed to reach a working image push, per `decisions.md` ADR-019's reasoning.
- **Platform deploy step**: conditional on `secrets.FLY_API_TOKEN` (or equivalent) being present; currently always no-ops with a log message, since `decisions.md` OQ-13 (which platform) is unresolved and no such secret exists in this repository. Not a placeholder left broken — the step is written correctly and will function the moment the secret is added, requiring no further code change.
- **Frontend deploy**: intentionally not a workflow step at all. Vercel's GitHub App integration (a one-time manual dashboard connection, root directory → `frontend/`) handles it independently per `devops.md` §6. The `deploy` job logs this explicitly so the workflow's Actions-UI output doesn't read as "frontend deploy silently skipped."

### Nightly workflow (`.github/workflows/nightly.yml`)
Cron (`0 3 * * *`) + `workflow_dispatch`. `e2e` job runs the existing `frontend/e2e/*.spec.ts` suite unchanged (already CI-aware via `process.env.CI` in `playwright.config.ts`) — full detail on why this suite tests connectivity-error paths rather than a true golden path is in `devops.md` §6.1 and `testing.md` §3, not repeated here. `ai-eval` job re-runs the four `test_graph_*.py` LangGraph node test files as the current stand-in for the golden-set regression tier `testing.md` §4.7 describes; the curated hallucination/injection fixture sets (`testing.md` §4.5/§4.6) don't exist as files yet — building them is flagged as a follow-up, not fabricated as already done.

### What was verified by actually running things, not just reading config
- `backend/Dockerfile`: built, run against the real `doxly-postgres-1` container over the Compose network, `/health` returned `200`, `docker inspect .State.Health` reached `healthy`, `whoami` inside the container confirmed `appuser` (non-root), `docker scout cves` re-run after the `perl-base` fix confirmed 0 CRITICAL/0 HIGH.
- `mypy`/`ruff`/`black` all run clean against `backend/app/` after the three typing fixes.
- Full backend suite: `alembic upgrade head` against a real ephemeral Postgres, then `pytest` — **87/87 passed**.
- Full frontend suite: `tsc --noEmit` clean, `eslint .` clean, `vitest run` — **182/182 passed** (50 files).
- These regression numbers match the counts already recorded in `tasks/17-docker.md`'s own verification (Vitest 182/182, backend pytest 87/87), confirming this task introduced no regression in Phases 1–17's application code.

## Tests
No new test *files* — this task's deliverable is the pipeline itself (matching Phase 16's own "this phase's output IS the test suite" framing, applied here to "this phase's output IS the CI/CD configuration"). Verification was performed by running every command the workflow files invoke, directly, against real infrastructure (see "What was verified" above) rather than trusting the YAML would work once pushed. GitHub Actions' own execution against a real PR/push to `main` is the final verification step, outside what this local session can perform (no push access exercised without the user's explicit request).

## Acceptance Criteria
(Adapted from `roadmap.md` Phase 18's Definition of Done: "A merge to `main` results in a correctly deployed, migrated, working staging/production environment without manual steps" — the "without manual steps" clause is scoped here to *the pipeline's own steps*; the two genuinely external manual actions — Vercel's one-time dashboard connection, and provisioning `FLY_API_TOKEN`/`DATABASE_URL` secrets — are outside what any workflow file can perform and are documented as such, not silently assumed done.)
- `.github/workflows/ci.yml` runs lint, type-check, test (with a migration-check), and build on every PR and every push to `main`, blocking merge on any failure.
- The `deploy` job runs only on `main`, only after the preceding four stages pass, and applies migrations before any image deploy step.
- `.github/workflows/nightly.yml` runs the E2E and AI-regression tiers on a schedule, not on every PR.
- The backend/worker image builds, runs non-root, and passes its healthcheck.
- No regression in Phases 1–17's application code or tests.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] `.github/workflows/ci.yml` and `.github/workflows/nightly.yml` created, matching `devops.md` §5/§6/§6.1's (updated) design
- [x] `backend/Dockerfile` built and verified by actually running the built image (build, run, healthcheck, non-root check, `curl`/`/health`, vulnerability scan) — the same verification bar `tasks/17-docker.md` set for the frontend image
- [x] No requirement silently changed or reinterpreted — the missing-routers/missing-worker gap found during verification was documented (`devops.md` §1.2, §6.1; this file's Implementation Notes) rather than either silently worked around or silently expanded into a routers-implementation task
- [x] `specs/devops.md` and `specs/decisions.md` updated — §1.2, §5, §6, §6.1 (devops.md); `ADR-019`, `OQ-13` (decisions.md); the pre-existing "ESLint + Prettier" spec/implementation mismatch was also corrected while touching §5, per SDD rule 3
- [x] Full regression check performed across Phases 1–17 — backend pytest 87/87, `mypy`/`ruff`/`black` clean, frontend `tsc --noEmit`/`eslint`/`vitest` clean (182/182), matching `tasks/17-docker.md`'s own recorded counts
- [x] Security review performed — the backend image's `docker scout cves` scan is part of this task's own deliverable (§1.2), went from 2 CRITICAL/2 HIGH to 0/0; CI/CD secrets handling reviewed against `devops.md` §7 (no secret baked into an image, GHCR push uses the ambient `GITHUB_TOKEN`, production secrets gated with graceful skips rather than hardcoded)
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

## Known Limitations / Follow-Up (not fixed this task, correctly scoped to later phases)
- **No API routers exist for most domains** (auth, documents, chat, extractions, comparisons, search, analytics) — a pre-existing gap from Phases 2/4/9–14, already documented in `testing.md` §3 before this task started. This is the single largest blocker to Phase 19 (Production Deployment)'s Definition of Done ("Doxly is live and usable end to end") and should be resourced before that phase begins, not discovered there.
- **No RQ worker consumer entrypoint exists** (`roadmap.md` Phase 5/8 scope) — `backend/Dockerfile`'s image can only actually run the API process today; the worker half of `architecture.md` §2.3's "same image, different entrypoint" design has nothing to invoke yet.
- **Container platform not chosen or provisioned** (`decisions.md` OQ-13) — the `deploy` job's platform-deploy step is written and ready but will no-op until a human provisions Fly.io/Railway/etc. and adds the corresponding secret.
- **`testing.md` §4.5/§4.6's curated golden-set fixture files don't exist yet** — the nightly `ai-eval` job currently re-runs the mocked-LLM graph node tests as a stand-in; building the actual curated adversarial/should-decline question sets is separate content work, not workflow wiring.
