# Doxly

**AI-powered document intelligence.**
*Your docs, but smarter.*

> **Status: specification foundation.** This repository currently contains the complete Specification-Driven Development (SDD) documentation for Doxly — no application source code has been written yet. Everything below describes what Doxly will be and how it will be built, not a running application. See [§ Current State](#current-state) before looking for setup instructions.

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
    └── README.md                Task template — no tasks created yet
```

## Development Workflow

1. Pick up the next phase from [`specs/roadmap.md`](specs/roadmap.md) (phases are dependency-ordered, starting with Phase 1 — Foundation).
2. Create task file(s) for that phase's objectives using the template in [`tasks/README.md`](tasks/README.md), sized to one reviewable PR each.
3. Implement against the current state of `specs/` and the relevant `skills/*.md` guidance. If a spec is unclear or wrong once you're implementing against it, fix the spec first, in the same PR, not after.
4. Write the tests `specs/testing.md` maps to the requirement(s) the task fulfills.
5. Verify against the acceptance criteria in `specs/requirements.md` — not just "it runs."

## Current State

**Nothing has been implemented yet.** There is no `package.json`, no `pyproject.toml`, no Dockerfile, no application code, and no dependencies installed — only this specification set. Setup/run instructions will be added once Phase 1 (Foundation) of `specs/roadmap.md` produces an actual scaffolded application; documenting install/run commands for code that doesn't exist yet would be misleading, so none are included here.

## Open Questions

A number of product/infrastructure decisions were given a recommended default rather than left unresolved, since SDD requires *some* answer to build against — every one of them is explicitly flagged, with its reasoning, in [`specs/decisions.md`](specs/decisions.md) under "Open Questions." Notable ones: authentication/social-login provider, LLM and embedding provider choice, file storage provider, OCR scope, file size/storage quota limits, rate limits, subscription/monetization model, and background job infrastructure. None of these are silently baked in — read that section before assuming any of them are final.
