# Doxly — DevOps Engineering Skill

> How to work with Doxly's build/ship tooling well. `specs/devops.md` (process, CI pipeline, local dev workflow) and `specs/deployment.md` (production topology, Vercel/container specifics) are authoritative for *what* the pipeline and environments must do — this file is engineering practice around them.

## Purpose

Two deployable services (Vercel frontend, containerized backend/worker), a Dockerized local stack, and a real migration history all have to stay in sync without slowing contributors down. This file exists so that stays true as the team grows.

## Docker

- **Purpose:** dev/prod parity for the Python stack's native dependencies (`pypdf`, `psycopg`, etc.) and a pinned Postgres+pgvector version, per `specs/devops.md` §1.
- **Project-specific usage:** `fastapi-app` and `worker` share one image, differing only in entrypoint command — build it once.
- **Best practices:** keep the image lean (multi-stage build, only runtime deps in the final layer); never bake a secret into an image layer, even a "dev-only" one — secrets are injected at container start via environment variables, not `ARG`/`ENV` baked at build time.
- **Common mistakes:** letting the Dockerfile drift from what CI actually builds (e.g., a locally-patched image that isn't reproducible from the committed Dockerfile); adding a new native dependency without updating the base image's system packages, causing "works on my machine" for one contributor only.
- **Quality expectations:** a fresh `git clone` + documented startup command reaches a fully working local stack with zero manual steps beyond filling in `.env` (`specs/devops.md` §3).

## Docker Compose

- **Purpose:** one-command local environment matching production topology in shape (not scale).
- **Project-specific usage:** the five-service compose stack in `specs/devops.md` §2 — hot-reload volumes, auto-migration on startup, service-name networking that mirrors how production code addresses managed services.
- **Best practices:** service names in compose match the hostnames the application code actually uses (never hardcode `localhost` for an inter-service call, since that breaks the dev/prod parity the whole setup exists for); keep `.env.example` exhaustive and current — every variable the stack reads has an entry, even if the value is an obvious placeholder.
- **Common mistakes:** adding a new required environment variable to application code without adding it to `.env.example`, breaking onboarding for the next contributor silently (the app might even start, then fail confusingly on first use of that variable).
- **Quality expectations:** `.env.example` is reviewed as part of any PR that introduces a new configuration value.

## Git

- **Purpose:** a readable, bisectable `main` history and a review gate that catches tenant-isolation and spec-drift issues before merge.
- **Project-specific usage:** GitHub Flow — short-lived branches, PR required, one approving review, squash-merge (`specs/devops.md` §4).
- **Best practices:** keep branches short-lived (hours-to-days) to avoid conflict/drift; write a PR description that names which `specs/` requirement ID(s) the change addresses, so review can check the implementation against the actual acceptance criteria rather than against the diff alone.
- **Common mistakes:** long-lived feature branches that accumulate unrelated changes, making review and bisection both harder; force-pushing over a branch another contributor has already pulled.
- **Quality expectations:** every merged PR is green on CI and traceable to a requirement or an explicitly-noted non-functional change (refactor, chore).

## GitHub Actions / CI

- **Purpose:** the automated gate that proves a PR is safe to merge.
- **Project-specific usage:** per `specs/devops.md` §5 and `specs/testing.md` §4 — unit, component, API, database, authentication, authorization, and LangGraph-node tests run on every PR; E2E and the full AI golden-set run pre-merge-to-`main` and nightly.
- **Best practices:** keep the per-PR pipeline fast (parallelize independent test jobs, cache dependency installs) so the fast feedback loop stays fast — a CI pipeline contributors start ignoring because it's slow is a CI pipeline that's already failed its purpose; treat a CI secret (provider API key, DB URL) exactly as sensitively as a production secret, since CI runs untrusted-until-reviewed PR code in the case of external contributions.
- **Common mistakes:** letting the per-PR suite grow to include the slow AI golden-set run "just to be safe," eroding the fast/slow split that keeps velocity high; a flaky test that gets re-run until green instead of fixed, which quietly trains the team to distrust CI failures.
- **Quality expectations:** the cross-tenant access suite (`specs/testing.md` §2.5) and any security-relevant test category are release-blocking in CI — never an optional/soft-fail job.

## Environment Variables & Secrets

- **Purpose:** every service gets the configuration and credentials it needs, and nothing sensitive ever reaches source control.
- **Project-specific usage:** distinct secret sets per environment (dev/preview/prod, `specs/deployment.md`); Vercel-side `NEXT_PUBLIC_*` vs. server-only variable discipline (`specs/deployment.md` §2); backend/worker secrets injected via the container platform's environment variable configuration, never committed.
- **Best practices:** rotate a secret immediately if it's ever suspected of leaking (committed by accident, exposed in a log); use the most restrictive scope a platform offers (per-environment, not one shared secret across dev/preview/prod).
- **Common mistakes:** assigning a secret to a `NEXT_PUBLIC_*` variable, which ships it to every browser that loads the page — this is a code-review-blocking mistake, not a style nit; committing a `.env` file (as opposed to `.env.example`) by accident.
- **Quality expectations:** a `git log` of the repository never contains a real secret at any point in its history — if one ever does, it's treated as a rotation-required incident, not just a revert.

## Vercel

- **Purpose:** host the Next.js frontend with zero-config CDN, preview deploys, and automatic HTTPS.
- **Project-specific usage:** Vercel hosts the frontend only, per `decisions.md` ADR-007 and `specs/deployment.md` — nothing that holds a DB connection, consumes a queue, or makes a long AI call runs on Vercel.
- **Best practices:** treat every Next.js Route Handler as a thin BFF proxy — if a handler is doing anything more than forwarding a request/relaying cookies, that's a signal it belongs in FastAPI instead; use Vercel's preview deploys as the default way to review a frontend change visually, not just the code diff.
- **Common mistakes:** reaching for a Vercel serverless function to do "just a quick" document-processing or LLM-chain task because it's convenient — this recreates the exact execution-time-limit problem ADR-007 exists to avoid.
- **Quality expectations:** no Next.js code path ever calls Postgres, Redis, or an LLM/embedding provider directly — verified by code review, not just by the architecture diagram's intent.

## Deployment & Monitoring

- **Purpose:** ship changes to production safely and know quickly when something's wrong.
- **Project-specific usage:** production topology, replica counts, and rollout mechanics live in `specs/deployment.md`; what gets monitored and alerted on lives in `specs/observability.md`.
- **Best practices:** treat a failed health check on a new backend/worker deploy as a hard stop, not a "let's see if it recovers" wait; keep database migrations backward-compatible with the previous code version during a rolling deploy (the old and new backend versions may run simultaneously for a brief window) — a migration that breaks the still-running old version is a deploy-order bug, not just a migration bug.
- **Common mistakes:** deploying a schema migration and the code that depends on it in a way that isn't safe for the brief window both versions coexist during a rolling deploy.
- **Quality expectations:** every production deploy is observable in real time (health, error rate, queue depth) per `specs/observability.md`, so a bad deploy is caught by monitoring within minutes, not by a user report.
