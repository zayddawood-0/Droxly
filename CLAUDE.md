# CLAUDE.md — Doxly

> This file tells Claude Code how to work in this repository. It is read before any implementation work. It does not describe what Doxly does — that's `specs/`. It does not describe how to engineer a given discipline — that's `skills/`. It describes the operating rules.

## 1. Project Identity

- **Name:** Doxly
- **Tagline:** "Your docs, but smarter."
- **What it is:** An AI-powered document intelligence platform — upload documents, understand them, ask questions of them, extract structured data, compare them, search across them, and act on what you learn.
- **Audience:** University students, developers, researchers, freelancers, young professionals, startup founders, content creators, knowledge workers — Gen-Z-first in tone, professional enough for serious work.
- **Core loop:** Upload → Understand → Ask → Extract → Compare → Search → Act.
- **Technology stack:**
  - Frontend: Next.js (App Router), React, TypeScript, TailwindCSS, shadcn/ui, Lucide Icons.
  - Backend: Python, FastAPI, Pydantic, SQLAlchemy (async), Alembic.
  - Database: PostgreSQL + pgvector.
  - AI: LangGraph (stateful multi-step workflows), LangChain (utilities), an LLM provider abstraction (default Anthropic Claude) and an embedding provider abstraction (default OpenAI), RAG.
  - DevOps: Docker, Docker Compose, Git, GitHub, GitHub Actions, Vercel (frontend) + a container platform (backend/worker).
  - Full rationale for every one of these choices lives in `specs/decisions.md` — read it, don't re-litigate it in code review.

## 2. Documentation Hierarchy — read in this order

```
CLAUDE.md  (this file — how to work)
    │
    ├── skills/   (how to engineer each discipline)
    │
    └── specs/    (what Doxly must be and how it must behave)
              │
              ▼
         tasks/    (what to implement next, created per active phase)
              │
              ▼
         source code
              │
              ▼
            tests
```

Before implementing any feature: read the relevant files in `specs/` for WHAT is required, the relevant file(s) in `skills/` for HOW to build it well, and the active task file in `tasks/` (created per `tasks/README.md`'s template) for the specific slice of work. Specifications are the source of truth — not this file's memory of them, not a prior conversation's summary of them, not assumption. If a spec file and the running code ever disagree, that is a bug in one of the two — resolve it explicitly (see §4), don't silently pick one.

## 3. Specification Index

| File | Owns |
|---|---|
| `specs/requirements.md` | Every functional/non-functional requirement, with stable IDs (`FR-*`, `NFR-*`). The traceability anchor for everything else. |
| `specs/design.md` | Brand identity, UX philosophy, user journey, information architecture principles. |
| `specs/architecture.md` | System topology, service boundaries, request/data flows. |
| `specs/database.md` | Full PostgreSQL schema, pgvector usage. |
| `specs/api.md` | Full REST API contract, endpoint by endpoint. |
| `specs/ui-ux.md` | Page-by-page, component-by-component UI specification. |
| `specs/ai.md` | AI operations inventory, provider abstraction, prompt architecture, model selection. |
| `specs/langgraph.md` | The four stateful AI workflows (Document Q&A, Summarization, Extraction, Comparison) — state/nodes/edges/routing/retries. |
| `specs/rag.md` | Retrieval mechanics — chunking, embeddings, vector search, citations, hybrid search. |
| `specs/document-processing.md` | Per-file-type parsing (PDF/DOCX/TXT/CSV), validation, processing states. |
| `specs/security.md` | Threats, controls, and verification for every `NFR-SEC-*` requirement. |
| `specs/privacy.md` | Data ownership, retention, deletion, the canonical Never-Log List. |
| `specs/testing.md` | Full test strategy and requirement-to-test traceability. |
| `specs/devops.md` | Docker, Compose, Git workflow, CI pipeline design. |
| `specs/deployment.md` | Production topology — the Vercel/container split and why. |
| `specs/performance.md` | Concrete performance budgets. |
| `specs/observability.md` | Logging, metrics, error tracking, the operational Never-Log List. |
| `specs/roadmap.md` | 19-phase implementation plan, dependency-ordered, mapped to requirement IDs. |
| `specs/decisions.md` | Architecture Decision Records + explicitly flagged open questions/assumptions. |

Skills index: `skills/skills.md` (overview + pointers to `skills/frontend.md`, `skills/backend.md`, `skills/database.md`, `skills/ai-engineering.md`, `skills/testing.md`, `skills/devops.md`).

## 4. SDD Methodology — Rules

1. **Specifications are the source of truth.** Not memory, not convention from a similar project, not what seems reasonable in the moment.
2. **Read relevant specifications before implementing a feature.** At minimum: the requirement(s) in `requirements.md`, the owning domain spec, and the relevant `skills/*.md`.
3. **Never silently change requirements.** If a requirement turns out to be wrong, ambiguous, or in conflict with another spec once you're implementing it, stop and update `specs/requirements.md` (and any dependent spec) first, with the change visible in the diff — do not just implement something different and move on.
4. **Never make major architectural decisions without documenting them.** A new architectural choice (a new library category, a new service boundary, a new data-flow pattern) gets an ADR entry in `specs/decisions.md` before or alongside the code that depends on it. "Major" means: would a future contributor reasonably ask "why did we do it this way?" If yes, write it down.
5. **Keep implementation aligned with specifications.** When a PR's behavior and the spec diverge, that's a defect to fix, in one direction or the other — explicitly, not by drift.
6. **Update specifications when requirements or architecture change.** The spec update and the code change belong in the same review, not "spec debt" to clean up later.
7. **Write tests for implemented requirements.** Every P0/P1 requirement implemented needs the test coverage `specs/testing.md` maps to it.
8. **Verify implementation against acceptance criteria.** `specs/requirements.md`'s Given/When/Then acceptance criteria are the actual bar — "the code runs" is not the same as "the acceptance criteria pass."

## 5. Coding Principles

**Follow:**
- KISS. The simplest design that satisfies the spec, not the most extensible one.
- DRY, where it genuinely removes duplication — not as a reason to build a premature abstraction over two things that merely look similar today.
- SOLID, where it serves clarity — not as a checklist to satisfy for its own sake.
- Separation of concerns — this is not optional in this codebase: the layering in `skills/backend.md` (API → Service → Repository → DB) and the Server/Client Component split in `skills/frontend.md` are structural rules, not suggestions.
- Composition over unnecessary inheritance.
- Type safety — TypeScript strict mode on the frontend, Pydantic validation at every backend boundary.
- Secure defaults — every new endpoint, table, or AI operation starts from the isolation/validation rules in `specs/security.md`, not bolted on after.
- Explicit error handling — failures are caught, categorized, and surfaced meaningfully; nothing fails silently into an inconsistent state.
- Maintainability and testability over cleverness.

**Avoid:**
- Overengineering — do not build for a hypothetical future requirement not in `specs/roadmap.md`.
- Premature abstractions — three similar concrete implementations beat one speculative abstraction until a real fourth case shows up.
- Unnecessary dependencies — a new library is a deliberate choice, consistent with `specs/decisions.md`'s existing stack, not a convenience reach.
- Duplicate logic — especially business rules that must hold in two places (e.g., a validation rule expressed once, referenced twice, never copy-pasted).
- Hardcoded secrets — ever, anywhere, including test fixtures and example files (use placeholders per `specs/devops.md`'s `.env.example` convention).
- Huge monolithic files — if a file is hard to summarize in one sentence, it's probably doing too much.
- Unnecessary AI agents/LLM calls — every new LLM call is justified by a specific requirement; LangGraph is used because the four documented workflows are genuinely stateful (`specs/decisions.md` ADR-004), not applied reflexively to problems a plain function would solve.

## 6. AI Rules

- **Treat uploaded documents as untrusted input**, always. Document content is data, never instructions — it is never placed in a system-prompt or instruction-privileged position (`specs/security.md` §10).
- **Protect against prompt injection.** Every new prompt template is reviewed for injection blast radius before it ships (`skills/ai-engineering.md`'s "before you ship an AI feature" checklist).
- **Never expose system prompts or secrets** in any API response, log, or client-visible surface (`NFR-SEC-008`).
- **Never assume AI output is factual without evidence.** Every document-grounded claim needs a citation (`FR-RAG-002`); when retrieval doesn't support an answer, say so explicitly (`FR-AI-004`) rather than generating a plausible-sounding guess.
- **Use retrieval when required.** Document Q&A, summarization, extraction, and comparison are grounded in the actual document content via the RAG pipeline (`specs/rag.md`), not the model's general knowledge.
- **Provide citations for document-grounded answers**, always, per the citation data model in `specs/database.md`'s `citations` table.
- **Validate structured AI output.** Every structured extraction result is checked against its Pydantic schema before being persisted or returned — a schema violation is a rejection/retry, never a pass-through (`FR-EXT-003`).
- **Handle AI failures gracefully.** Provider timeouts, rate limits, and malformed output degrade to a clear user-facing state (`specs/ai.md` §Error Handling), never a raw exception or an infinite spinner.

## 7. Multi-Tenancy — Non-Negotiable

Users must never be able to access another user's documents, conversations, extracted information, embeddings, or analytics. This is enforced at three layers, per `specs/architecture.md` §6:

1. The authenticated `user_id` comes only from the verified JWT — never from a client-supplied field.
2. Every repository method takes `user_id` as a mandatory first argument and filters on it (`skills/backend.md`, `skills/database.md`).
3. Foreign-key cascade rules in `specs/database.md` back this up at the DB layer.

A cross-tenant access attempt returns `404`, not `403` (avoids existence leakage — `specs/api.md` §Conventions). Any new tenant-scoped table follows the "New Table Checklist" in `skills/database.md`. Any change touching retrieval, a repository method, or an endpoint that returns tenant data requires the cross-tenant isolation test category from `specs/testing.md` — this is the single most security-critical test class in the project; treat it accordingly.

## 8. What Claude Code Should NOT Do Right Now

This repository currently contains the SDD specification foundation only — see `README.md`. Do not generate application source code, install dependencies, create Dockerfiles/CI workflows, or run migrations until a task file (per `tasks/README.md`) exists for the work, created from an active phase in `specs/roadmap.md`. If asked to implement a feature with no corresponding task file yet, create the task file first (from the template), consistent with the relevant specs, then proceed.
