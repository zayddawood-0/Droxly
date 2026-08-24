# Doxly

**AI-powered document intelligence.**
*Your docs, but smarter.*

> **Status: Phases 1–18 of 19 implemented.** This repository is built via Specification-Driven Development — `specs/` remains the source of truth, and `frontend/`/`backend/` are real, running applications built against it, with CI/CD wired per `specs/devops.md`. See [§ Current State](#current-state) for what's implemented and the one significant known gap.

## What is Doxly

Doxly is a modern, AI-first document intelligence platform. It's built for university students, developers, researchers, freelancers, young professionals, startup founders, content creators, and knowledge workers who deal with documents constantly and want something faster and smarter than a folder full of PDFs.

The core experience is one loop:

```
Upload → Understand → Ask → Extract → Compare → Search → Act
```

Upload a document, get a grounded AI chat interface to ask it questions (with citations, never guesses), pull structured data out of it, compare it against another version, search across your whole document library, and export what you find.

## Planned Features

- **Document upload & management** — PDF, DOCX, TXT, CSV, with tagging, status tracking, and a real processing pipeline (not a black box).
- **AI chat over your documents** — grounded, cited, streaming answers; explicit "I don't know" when a document doesn't cover something, never a fabricated answer.
- **Summarization** — brief, detailed, or bullet-point summaries, quality-checked before they're shown to you.
- **Structured extraction** — pull fields out of invoices, contracts, resumes, research papers (presets or custom schemas), with per-field confidence and source citations.
- **Document comparison** — semantic diff between two documents, classified by change type, not a naive line diff.
- **Global search** — hybrid keyword + semantic search across your entire document library.
- **Usage analytics** — a personal dashboard of what you've processed and asked.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, TailwindCSS, shadcn/ui, Lucide Icons |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy (async), Alembic |
| Database | PostgreSQL + pgvector |
| AI | LangGraph (stateful workflows), LangChain, RAG, provider-abstracted LLM (default: Anthropic Claude) and embeddings (default: OpenAI) |
| Infrastructure | Docker, Docker Compose, GitHub Actions, Vercel (frontend) + a container platform (backend/worker) |

Every choice above is documented with its full rationale and alternatives considered in [`specs/decisions.md`](specs/decisions.md).

## Architecture Overview

Doxly is two deployable services, not one monolith:

- **Next.js frontend** (Vercel) — renders the UI, proxies authenticated requests to the backend. Never talks to the database, queue, or LLM providers directly.
- **FastAPI backend + background worker** (containerized, not Vercel serverless) — owns authentication, authorization, all business logic, and long-running work (document processing, multi-step AI workflows) via a Redis-backed job queue.

This split exists specifically because document processing and multi-node AI workflows can take longer than a serverless function is built to run — see [`specs/deployment.md`](specs/deployment.md) for the full reasoning, and [`specs/architecture.md`](specs/architecture.md) for the request/data flow diagrams.

## Specification-Driven Development (SDD)

This project is built spec-first. The specification is the source of truth; code implements it, tests verify it. The hierarchy:

```
CLAUDE.md   → how Claude Code (and contributors) must work
skills/     → how to engineer each discipline well
specs/      → what Doxly must be and how it must behave
tasks/      → what to implement next (created per active roadmap phase)
source code → the implementation
tests       → verification against the specs
```

Every requirement in [`specs/requirements.md`](specs/requirements.md) has a stable ID (`FR-AUTH-001`, `NFR-SEC-001`, etc.) that's referenced — not restated — throughout the rest of the documentation, so a change to a requirement has one place to happen and many places that stay consistent with it.

## Documentation Structure

```
/
├── CLAUDE.md                    Root operating rules for Claude Code
├── README.md                    This file
│
├── specs/                       What Doxly must be
│   ├── requirements.md          Every FR-*/NFR-* requirement, with acceptance criteria
│   ├── design.md                Brand identity & UX philosophy
│   ├── architecture.md          System topology & data flows
│   ├── database.md              Full PostgreSQL + pgvector schema
│   ├── api.md                   Full REST API contract
│   ├── ui-ux.md                 Page-by-page UI specification
│   ├── ai.md                    AI capabilities & provider abstraction
│   ├── langgraph.md             The four stateful AI workflows
│   ├── rag.md                   Retrieval architecture
│   ├── document-processing.md   Per-file-type parsing pipeline
│   ├── security.md              Threats, controls, verification
│   ├── privacy.md               Data ownership, retention, deletion
│   ├── testing.md               Full test strategy & traceability
│   ├── devops.md                Docker, Git workflow, CI pipeline
│   ├── deployment.md            Production deployment architecture
│   ├── performance.md           Performance budgets
│   ├── observability.md         Logging, metrics, error tracking
│   ├── roadmap.md               19-phase implementation plan
│   └── decisions.md             ADRs + explicitly flagged open questions
│
├── skills/                      How to engineer each discipline
│   ├── skills.md                Overview & index
│   ├── frontend.md              Next.js/React/TypeScript standards
│   ├── backend.md                FastAPI/Python standards
│   ├── database.md              PostgreSQL/SQLAlchemy/Alembic standards
│   ├── ai-engineering.md        LangGraph/RAG engineering practice
│   ├── testing.md               Testing craft
│   └── devops.md                Docker/CI/CD/Vercel practice
│
└── tasks/
    ├── README.md                Task template
    └── 01-...18-*.md            Per-phase task files (Phases 1-18)
```

## Development Workflow

1. Pick up the next phase from [`specs/roadmap.md`](specs/roadmap.md) (phases are dependency-ordered, starting with Phase 1 — Foundation).
2. Create task file(s) for that phase's objectives using the template in [`tasks/README.md`](tasks/README.md), sized to one reviewable PR each.
3. Implement against the current state of `specs/` and the relevant `skills/*.md` guidance. If a spec is unclear or wrong once you're implementing against it, fix the spec first, in the same PR, not after.
4. Write the tests `specs/testing.md` maps to the requirement(s) the task fulfills.
5. Verify against the acceptance criteria in `specs/requirements.md` — not just "it runs."

## Current State

Phases 1–18 of `specs/roadmap.md` have been implemented (see `tasks/` for the per-phase task files and their Definition of Done). `frontend/` (Next.js) and `backend/` (FastAPI) are real, dependency-installed applications with their own `package.json`/`pyproject.toml`, Dockerfiles, and test suites; `.github/workflows/ci.yml`/`nightly.yml` run lint/type-check/test/build on every PR and a slower E2E/AI-regression tier nightly (`specs/devops.md` §5–§6.1).

**The one significant gap a new contributor should know about immediately:** `backend/app/main.py` currently exposes only a `/health` endpoint — no `APIRouter` for auth, documents, chat, extraction, comparison, search, or analytics has been wired in yet, even though the underlying service/repository/LangGraph logic for most of those domains is implemented and tested. This is a pre-existing gap from Phases 2/4/9–14, documented in `specs/testing.md` §3 and `tasks/18-ci-cd.md`, not something recent work introduced — but it means the frontend's BFF proxy (`frontend/app/api/v1/[...path]/route.ts`) currently has almost nothing real to call. Resourcing this is flagged as the top priority before Phase 19 (Production Deployment).

## Open Questions

A number of product/infrastructure decisions were given a recommended default rather than left unresolved, since SDD requires *some* answer to build against — every one of them is explicitly flagged, with its reasoning, in [`specs/decisions.md`](specs/decisions.md) under "Open Questions." Notable ones: authentication/social-login provider, LLM and embedding provider choice, file storage provider, OCR scope, file size/storage quota limits, rate limits, subscription/monetization model, and background job infrastructure. None of these are silently baked in — read that section before assuming any of them are final.
