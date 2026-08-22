# Doxly — Engineering Skills Index

> This file is the entry point into `skills/`. It names every skill area Doxly's stack touches, states what "good" looks like for that area **on this project specifically**, and points to the dedicated file for depth. Deep practice detail lives in `skills/frontend.md`, `skills/backend.md`, `skills/database.md`, `skills/ai-engineering.md`, `skills/testing.md`, `skills/devops.md` — this file does not duplicate them.

## Full-stack development

**Purpose:** Doxly's frontend, backend, and AI layers hand off to each other in a specific, deliberate way (`specs/architecture.md`) — Next.js is presentation + BFF, FastAPI is the authorization and orchestration boundary, the worker runs long AI/processing jobs. A full-stack change on this project usually touches at least two of these, and getting the handoff right matters more than any single layer's code quality.
**Best practice:** trace a change through the whole request path (UI → Route Handler → FastAPI router → service → repository/AI layer) before writing code, so the layer that should own a piece of logic actually owns it.
**Common mistake:** putting business logic in a Next.js Route Handler because it's the fastest place to make a demo work — it violates the BFF boundary and duplicates logic that belongs in a FastAPI service.

## Next.js / React / TypeScript / TailwindCSS

See `skills/frontend.md` for full depth (App Router conventions, Server/Client Component boundaries, component architecture, forms/validation, state management, accessibility, performance).
**Summary:** Server Components by default, TypeScript strict mode, shadcn/ui as the component base, Tailwind tokens matching `specs/ui-ux.md`'s design system — never a bespoke one-off styling approach per page.

## FastAPI / Python

See `skills/backend.md` for full depth (router/service/repository layering, dependency injection, Pydantic contracts, async discipline).
**Summary:** routers are thin, services own business logic, repositories own queries and always take `user_id` first. `specs/api.md` is the enforced contract — a schema drift from it is a bug.

## PostgreSQL / pgvector / SQLAlchemy / Alembic

See `skills/database.md` for full depth (transactions, indexing, migration discipline, the New Table Checklist).
**Summary:** `specs/database.md` is the schema source of truth; every tenant table has a leading `user_id` index and a repository method that filters on it. HNSW vector search always includes the tenant filter.

## LangGraph / LangChain / RAG

See `skills/ai-engineering.md` for full depth (provider abstraction discipline, prompt versioning, structured outputs, retrieval, evaluation).
**Summary:** all four workflows (`specs/langgraph.md`) are graphs with typed state and mockable, unit-testable nodes. Retrieval always goes through one shared, tenant-filtered function (`specs/rag.md`). LangChain supplies utilities (loaders, splitters); LangGraph is the orchestration layer — never the reverse.

## Document processing

Owned by `specs/document-processing.md` (a product spec, not a general engineering skill — file-type parsing is Doxly-specific, so there's no separate `skills/` file for it). Engineering discipline for extending it (new file types via the `DocumentParser` interface) lives inline in that spec.

## REST APIs

See `skills/backend.md` (contract implementation discipline) and `specs/api.md` (the actual contract). **Summary:** `/api/v1`-versioned, consistent error envelope, every endpoint has an explicit authorization rule — no endpoint is "obviously fine" without stating who can call it.

## Authentication

See `skills/backend.md` (code organization: one auth module, one `get_current_user` dependency) and `specs/security.md` (the policy: JWT design, cookie flags, rate limiting on auth endpoints).

## Security

Security is not a single skill file but a cross-cutting discipline: `specs/security.md` is the policy, and secure-coding practice is folded into `skills/backend.md` (validation, error handling, authorization pattern) and `skills/frontend.md` (XSS avoidance, never trusting client validation alone). Treat any code review that skips the multi-tenancy question ("could User B reach this?") as incomplete.

## Testing

See `skills/testing.md` for full depth (unit/integration/API/component/E2E discipline, AI evaluation, mocking discipline, the Definition-of-Done checklist). **Summary:** `specs/testing.md` defines the strategy and requirement traceability; `skills/testing.md` defines how to write a test that's actually worth having.

## Docker / CI/CD / Vercel

See `skills/devops.md` for full depth (Dockerfile/Compose discipline, Git/PR workflow, CI design, secrets, monitoring habits). **Summary:** `specs/devops.md` and `specs/deployment.md` define the infrastructure; `skills/devops.md` defines the habits that keep it healthy (fast CI, `.env.example` hygiene, no secrets in diffs).

## How these fit together

- `CLAUDE.md` (root) — how Claude Code must behave on this project.
- `skills/` (this directory) — **how** to engineer each part of the stack well.
- `specs/` — **what** Doxly must be and how it must behave; the source of truth for product requirements and system design.
- `tasks/` — **what's next**; discrete implementation units derived from `specs/`.
- Source code and tests are the realization of `specs/`, built using the discipline in `skills/`, tracked as `tasks/`.

A skill file never introduces a product requirement or a schema/contract detail that doesn't already exist in `specs/` — if a skill file and a spec file disagree, the spec file wins, and the skill file should be corrected.
