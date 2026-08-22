# Doxly — Implementation Roadmap

> Dependency-aware, phased implementation plan. Each phase lists objectives, dependencies on prior phases, the requirement IDs it fulfills (from `requirements.md`), the specs it draws on, expected outputs, the tests that must pass, and a Definition of Done. This is the bridge between "what Doxly must be" (`specs/`) and "what to implement next" (`tasks/`) — individual implementation tasks are created per-phase using the template in `tasks/README.md`, not enumerated here.

## How to read this roadmap

- Phases are sequential by default (each depends on the prior phase's Definition of Done being met), but note explicit **Dependencies** — some phases only depend on specific earlier phases, not literally every phase before them, and may be reordered or parallelized by team capacity once foundational phases are done.
- "Requirements fulfilled" cites P0 requirements primarily; P1/P2 requirements for the same feature area are folded in where natural but may trail into a later hardening pass — call this out per phase where relevant.
- Post-MVP items (team/org support, OCR, billing, public API keys) are listed at the end, deliberately excluded from the 19 phases, consistent with `decisions.md`'s Open Questions.

---

## Phase 1 — Foundation

- **Objectives:** Repository scaffolding for both services; local dev environment reproducible via Docker Compose; base CI pipeline (lint + build, no feature tests yet since there's no feature code).
- **Dependencies:** None (first phase).
- **Requirements fulfilled:** None directly (infrastructure only) — enables all subsequent phases.
- **Specs used:** `architecture.md`, `devops.md`, `decisions.md` (ADR-001, 002, 003, 006).
- **Tasks:** Initialize Next.js app (TypeScript, TailwindCSS, shadcn/ui installed), initialize FastAPI app (layered folder structure per `skills/backend.md`), Docker Compose with Postgres+pgvector and Redis, base GitHub Actions workflow (lint/build only).
- **Expected outputs:** Both apps boot locally via `docker-compose up`; empty health-check endpoint on FastAPI; empty landing page shell on Next.js.
- **Tests:** CI lint/build passes; a smoke test hitting the health-check endpoint.
- **Definition of Done:** A new contributor can clone the repo, run one documented command, and have both services running locally against a local Postgres+Redis.

## Phase 2 — Authentication

- **Objectives:** Full auth system: registration, login, OAuth, session refresh, logout, password reset, session management.
- **Dependencies:** Phase 1.
- **Requirements fulfilled:** FR-AUTH-001 through FR-AUTH-008.
- **Specs used:** `requirements.md` §1.1, `decisions.md` ADR-010 (+ OQ-01), `security.md` §1, `database.md` §3.1–3.2, `api.md` `/auth` domain, `ui-ux.md` Login/Register pages.
- **Tasks:** `users`/`refresh_tokens` tables + migration, password hashing, JWT issuance, Google OAuth integration, email verification flow, password reset flow, session list/revoke, Next.js login/register pages + route-handler proxies.
- **Expected outputs:** A user can register, verify email, log in (password or Google), stay logged in across a session refresh, log out, and reset a forgotten password.
- **Tests:** Auth unit/API test suite (`testing.md` §Backend/Authentication tests), including rate-limit/backoff behavior (NFR-SEC-002) and generic-error-message behavior (NFR-SEC-006).
- **Definition of Done:** All FR-AUTH-* P0 acceptance criteria pass; no auth endpoint leaks account existence or internals.

## Phase 3 — Database

- **Objectives:** Full schema migration for all remaining tables (beyond users/refresh_tokens): documents, document_chunks, tags, document_tags, conversations, conversation_documents, messages, citations, extractions, comparisons, document_summaries, ai_requests, audit_logs.
- **Dependencies:** Phase 1 (Phase 2's users table must exist first).
- **Requirements fulfilled:** None directly — enables Phases 4–14.
- **Specs used:** `database.md` (full), `skills/database.md`.
- **Tasks:** Alembic migrations for every table in `database.md` §3, pgvector extension + HNSW index setup, repository-layer base classes enforcing the `user_id`-first-argument convention (`skills/database.md` "New Table Checklist").
- **Expected outputs:** Complete schema present in every environment; repository layer scaffolded (empty CRUD methods) for each entity.
- **Tests:** Migration up/down tests; constraint tests (FK cascade, CHECK constraints, UNIQUE constraints) per `testing.md` §Database tests.
- **Definition of Done:** Schema matches `database.md` exactly; `alembic upgrade head` / `downgrade base` both succeed cleanly on a fresh DB.

## Phase 4 — Document Management

- **Objectives:** Upload (presigned), list, view metadata, rename, delete, tag documents — without processing yet (documents can sit in `queued` with no pipeline running).
- **Dependencies:** Phases 2, 3.
- **Requirements fulfilled:** FR-DOC-001 through FR-DOC-008 (upload confirms creation only in this phase; processing itself is Phase 5).
- **Specs used:** `requirements.md` §1.3, `decisions.md` ADR-009 (+ OQ-04, OQ-06, OQ-07), `security.md` §3, `api.md` `/documents` domain, `ui-ux.md` Documents/Upload pages.
- **Tasks:** Object storage integration (Vercel Blob default) + presigned URL generation, `documents`/`tags`/`document_tags` repository + service layer, storage quota enforcement against `users.storage_used_bytes`, Documents list/Upload/rename/delete UI.
- **Expected outputs:** A user can upload a file end-to-end (it lands in storage and a `documents` row exists as `queued`), see it in their list, tag/rename/delete it.
- **Tests:** Upload flow API tests, quota-exceeded rejection test, cross-tenant isolation tests for documents (`testing.md`'s critical authorization category), MIME/size validation tests (NFR-SEC-003/004).
- **Definition of Done:** All FR-DOC-* P0 criteria pass except those requiring a processed (`ready`) document, which depend on Phase 5.

## Phase 5 — Document Processing

- **Objectives:** The full extraction pipeline: text extraction, per-type parsing, status transitions, failure handling.
- **Dependencies:** Phases 3, 4, and the worker infrastructure from Phase 1 (Redis/RQ wiring).
- **Requirements fulfilled:** FR-PROC-001, FR-PROC-002 (chunking mechanics land fully in Phase 6, but structural handoff metadata starts here), FR-PROC-004, FR-PROC-005.
- **Specs used:** `document-processing.md` (full), `decisions.md` ADR-008 (+ ADR-014), `architecture.md` §4.
- **Tasks:** `DocumentParser` interface + PDF/DOCX/TXT/CSV implementations, RQ worker wired to consume the processing queue, status-transition logic (`queued→extracting`), failure handling with sanitized error messages, reprocessing endpoint.
- **Expected outputs:** An uploaded document has its text extracted and `documents.extracted_text_available=true`; corrupt/unsupported files fail cleanly with a user-facing reason.
- **Tests:** Per-file-type extraction tests (golden sample files for each MIME type), corrupt-file/failure-path tests, retry/backoff test (NFR-AVAIL-002).
- **Definition of Done:** FR-PROC-001/004/005 P0 criteria pass for all four supported file types.

## Phase 6 — Embeddings & Vector Search

- **Objectives:** Chunking, embedding generation, pgvector storage, and raw similarity search (no LLM answer generation yet).
- **Dependencies:** Phase 5.
- **Requirements fulfilled:** FR-PROC-002 (chunking, completed), FR-PROC-003, the retrieval-mechanics half of FR-RAG-001.
- **Specs used:** `rag.md` §1–6, `database.md` §4, `decisions.md` ADR-012 (+ OQ-03), `performance.md` (embedding batching, vector search budget).
- **Tasks:** Chunking implementation (recursive/semantic-aware per `rag.md`), `EmbeddingProvider` implementation (OpenAI default), batch embedding job, `document_chunks` population with tenant-filtered HNSW-indexed vectors, a raw (non-LLM) similarity-search repository method.
- **Expected outputs:** A `ready` document has chunk rows with populated embeddings; a direct vector query for a known question returns relevant chunks scoped to the correct user.
- **Tests:** Chunk boundary tests, embedding dimension/model consistency tests, tenant-scoped retrieval tests (a query never returns another user's chunks even when more "similar"), `NFR-PERF-005` benchmark at representative scale.
- **Definition of Done:** `documents.status` reaches `ready` end-to-end from upload; retrieval mechanics are correct and isolated per user.

## Phase 7 — RAG

- **Objectives:** Full retrieval pipeline wiring: query processing, filtering, context assembly, citation data model — the complete non-generative half of RAG, ready to be called by a graph.
- **Dependencies:** Phase 6.
- **Requirements fulfilled:** FR-RAG-001 (complete), FR-RAG-003.
- **Specs used:** `rag.md` §6–11.
- **Tasks:** Query-processing layer (embed the query, apply document/date/tag filters), context assembly logic (dedup, rank, trim to budget), relevance-threshold rejection path, `citations` table population logic.
- **Expected outputs:** Given a query and scope, the system returns an assembled, budgeted context set with citation metadata — independent of any specific LLM workflow consuming it yet.
- **Tests:** `testing.md` §RAG tests, §Retrieval tests, threshold/"no relevant match" path test (FR-RAG-003).
- **Definition of Done:** Retrieval pipeline is a stable, independently testable module ready for LangGraph integration.

## Phase 8 — LangGraph

- **Objectives:** Implement the LangGraph state machine scaffolding and all four graphs' nodes/edges (wired to mocked or real LLM calls as appropriate per environment).
- **Dependencies:** Phase 7 (Document Q&A and Extraction graphs depend on retrieval), Phase 5 (Comparison graph depends on extraction/parsing reuse).
- **Requirements fulfilled:** Enables FR-AI-*, FR-SUM-*, FR-EXT-*, FR-COMP-* (graphs built here; product-facing endpoints wired in Phases 9–12).
- **Specs used:** `langgraph.md` (full), `ai.md` (provider abstraction, prompt architecture).
- **Tasks:** `LLMProvider` implementation (Anthropic default), typed state definitions per graph, all nodes (Classifier, Retriever, Context Analyzer, Answer Generator, Citation Validator, Content Analyzer, Summary Generator, Quality Checker, Document Classifier, Schema Generator, Extraction Agent, Validation, Semantic Alignment, Difference Detection, Change Classification), checkpointing configuration, retry/error edges.
- **Expected outputs:** All four graphs are independently invokable and unit-testable with mocked LLM calls; each reaches a terminal state on every tested input including simulated failures.
- **Tests:** `testing.md` §LangGraph tests (per-node, per-graph, no-hang guarantee), `NFR-MAINT-002`.
- **Definition of Done:** Every graph node is unit-tested in isolation; graphs are ready to be invoked from API endpoints.

## Phase 9 — AI Chat

- **Objectives:** Wire the Document Q&A graph to the `/chat` API domain with SSE streaming, conversation persistence.
- **Dependencies:** Phase 8.
- **Requirements fulfilled:** FR-AI-001 through FR-AI-006.
- **Specs used:** `api.md` `/chat` domain, `architecture.md` §5, `ui-ux.md` AI Chat page.
- **Tasks:** `/chat` endpoints, SSE streaming response handling in FastAPI, conversation/message/citation persistence, AI Chat frontend (streaming UI, citation rendering, scope selector).
- **Expected outputs:** A user can chat with a document and get a grounded, cited, streamed answer; asking something the document doesn't cover yields an explicit "can't answer from this document" response.
- **Tests:** `testing.md` §Citation tests, §Hallucination tests, E2E chat golden path.
- **Definition of Done:** FR-AI-* P0 criteria pass; citation and "I don't know" behavior verified against the golden test set.

## Phase 10 — Summarization

- **Objectives:** Wire the Summarization graph to a `document_summaries`-backed feature.
- **Dependencies:** Phase 8.
- **Requirements fulfilled:** FR-SUM-001, FR-SUM-002.
- **Specs used:** `langgraph.md` §Summarization graph, `database.md` §6 (Open Item: `document_summaries` table — finalize its migration here if not already added in Phase 3).
- **Tasks:** Summarization endpoint (background-worker job per `architecture.md`), summary persistence, retrieval of past summaries, Document Viewer / Documents UI summary entry point.
- **Expected outputs:** A user requests a summary at a chosen detail level and receives a persisted, quality-checked result.
- **Tests:** Summarization quality-checker loop test (bounded retries), API tests.
- **Definition of Done:** FR-SUM-001/002 P0/P1 criteria pass.

## Phase 11 — Extraction

- **Objectives:** Wire the Extraction graph to the `/extractions` API domain with preset templates.
- **Dependencies:** Phase 8.
- **Requirements fulfilled:** FR-EXT-001 through FR-EXT-004.
- **Specs used:** `langgraph.md` §Extraction graph, `api.md` `/extractions` domain, `ui-ux.md` Extractions page.
- **Tasks:** Schema/template definitions (invoice, contract, resume, research paper presets per FR-EXT-002), extraction endpoint, structured-output validation, field-edit endpoint (FR-EXT-004), Extractions UI (schema picker + results table).
- **Expected outputs:** A user runs extraction against a document and gets a validated structured result with per-field citation/confidence, with missing fields explicitly null+reasoned rather than fabricated.
- **Tests:** `testing.md` §Extraction tests, schema-validation-rejection tests.
- **Definition of Done:** FR-EXT-001/003 P0 criteria pass; at least the four named preset templates work end-to-end.

## Phase 12 — Comparison

- **Objectives:** Wire the Comparison graph to the `/comparisons` API domain.
- **Dependencies:** Phase 8 (and reuses Phase 5's extraction/parsing).
- **Requirements fulfilled:** FR-COMP-001 through FR-COMP-003.
- **Specs used:** `langgraph.md` §Comparison graph, `api.md` `/comparisons` domain, `ui-ux.md` Comparison page.
- **Tasks:** Comparison endpoint (background-worker job), semantic alignment + change classification implementation, graceful-degradation path for structurally dissimilar documents, Comparison UI (report view with change-type badges).
- **Expected outputs:** A user compares two documents and gets a structured, classified diff report; comparing structurally incompatible documents yields a clear message instead of a nonsensical diff.
- **Tests:** `testing.md` comparison-specific API/E2E tests.
- **Definition of Done:** FR-COMP-001/002 P0 criteria pass.

## Phase 13 — Global Search

- **Objectives:** Hybrid (keyword + vector) search across a user's full corpus.
- **Dependencies:** Phase 7.
- **Requirements fulfilled:** FR-SEARCH-001 through FR-SEARCH-003.
- **Specs used:** `rag.md` §Hybrid Search, `api.md` `/search` domain, `ui-ux.md` Global Search page.
- **Tasks:** `tsvector` generated column + GIN index on chunk content/document names, reciprocal-rank-fusion combining logic, `/search` endpoint with filters, Search UI.
- **Expected outputs:** A user searches across all documents and gets ranked, highlighted, filterable results.
- **Tests:** Search relevance sanity tests, tenant-isolation test, filter-combination tests.
- **Definition of Done:** FR-SEARCH-001 P0 criteria pass.

## Phase 14 — Analytics

- **Objectives:** Personal usage dashboard.
- **Dependencies:** Phases 4–13 (aggregates data produced by all prior feature phases).
- **Requirements fulfilled:** FR-ANALYTICS-001 (FR-ANALYTICS-002 is P2, optional in this phase).
- **Specs used:** `api.md` `/analytics` domain, `ui-ux.md` Analytics page, `database.md` §6 (aggregation at query time, no dedicated analytics table for MVP).
- **Tasks:** Aggregate query endpoints (documents-over-time, storage, AI request volume from `ai_requests`), Analytics UI.
- **Expected outputs:** A user sees an accurate, reasonably fresh usage dashboard.
- **Tests:** Aggregate-query correctness tests.
- **Definition of Done:** FR-ANALYTICS-001 P1 criteria pass.

## Phase 15 — Security Hardening

- **Objectives:** A dedicated pass applying the full `security.md` checklist across everything built in Phases 2–14, closing gaps found under focused review rather than assuming each phase's inline security work was exhaustive.
- **Dependencies:** Phases 2–14.
- **Requirements fulfilled:** Full sweep of NFR-SEC-001 through 011.
- **Specs used:** `security.md` (full), `privacy.md` (full).
- **Tasks:** Security headers audit, CSRF verification, rate-limit tuning against real usage patterns, prompt-injection red-team pass against the golden adversarial-document set, admin-content-exposure audit (FR-ADMIN-001), account/document deletion purge-job verification against the 30-day retention policy.
- **Expected outputs:** A documented pass/fail against every NFR-SEC-* and NFR-PRIV-* item.
- **Tests:** `testing.md` §Security testing (full run), §Prompt injection tests (full run).
- **Definition of Done:** No open P0 security finding; all NFR-SEC-*/NFR-PRIV-* P0 items verified, not just implemented.

## Phase 16 — Testing

- **Objectives:** Close coverage gaps: bring E2E suite and AI golden-eval set to full coverage of the traceability table in `testing.md`, not just per-phase spot coverage.
- **Dependencies:** Phases 2–15.
- **Requirements fulfilled:** Verification layer for all P0/P1 requirements (no new product requirements introduced).
- **Specs used:** `testing.md` (full).
- **Tasks:** Fill any traceability-table gaps identified by review, expand the golden document/query/extraction set to better represent real student/developer/researcher/freelancer document types, wire the nightly AI-eval workflow.
- **Expected outputs:** Every P0 requirement has at least one passing automated test; nightly AI-eval baseline established for future regression detection.
- **Tests:** N/A (this phase's output IS the test suite).
- **Definition of Done:** `testing.md`'s traceability table shows no P0 gaps.

## Phase 17 — Docker

- **Objectives:** Production-grade Docker images (hardened, minimal, non-root) for backend/worker/frontend, finalized Compose setup for dev parity.
- **Dependencies:** Phase 1 (revisits/hardens what was scaffolded there), effectively runs once all services' final dependencies are known (after Phase 15).
- **Requirements fulfilled:** None directly — operational readiness.
- **Specs used:** `devops.md` §Docker architecture, `skills/devops.md`.
- **Tasks:** Multi-stage Dockerfile hardening, image size/vulnerability scan, Compose healthchecks finalized.
- **Expected outputs:** Production-ready images build reproducibly in CI.
- **Tests:** Image build verification in CI, container vulnerability scan passes.
- **Definition of Done:** Images pass the CI build/scan gate defined in `devops.md`.

## Phase 18 — CI/CD

- **Objectives:** Full CI/CD pipeline: all test tiers wired with correct cadence (per-PR vs nightly), CD to Vercel (frontend) and the container platform (backend/worker) on merge to `main`.
- **Dependencies:** Phases 16, 17.
- **Requirements fulfilled:** None directly — operational readiness.
- **Specs used:** `devops.md` (full), `deployment.md` (full).
- **Tasks:** GitHub Actions workflows for lint/test/build/migration-check (per-PR) and E2E/AI-eval (nightly), Vercel Git integration, container-platform deploy workflow, migration-then-deploy ordering.
- **Expected outputs:** Merging to `main` reliably ships both services with migrations applied first.
- **Tests:** A staged rollout to a preview/staging environment validates the pipeline itself before first production use.
- **Definition of Done:** A merge to `main` results in a correctly deployed, migrated, working staging/production environment without manual steps.

## Phase 19 — Production Deployment

- **Objectives:** First real production launch.
- **Dependencies:** Phase 18.
- **Requirements fulfilled:** All P0 requirements, in production.
- **Specs used:** `deployment.md` (full), `observability.md` (full), `performance.md` (full).
- **Tasks:** Production environment provisioning (managed Postgres w/ pgvector, Redis, container platform, Vercel production project), DNS/HTTPS, production secrets configured, monitoring/alerting live (per `observability.md`), a basic load-test validating the concurrent-user assumption in `performance.md`.
- **Expected outputs:** Doxly is live and usable end to end in production.
- **Tests:** Production smoke test covering the full golden path (register → upload → chat → extract → compare → search).
- **Definition of Done:** All P0 requirements verified against the live production environment; monitoring confirms no active P0 alert conditions.

---

## Post-MVP (explicitly out of the 19 phases)

| Item | Why deferred | Reference |
|---|---|---|
| Team/organization/workspace sharing | MVP targets individual users; adding shared tenancy now would complicate the isolation model before it's proven | `decisions.md` ADR-013, OQ-11 |
| OCR for scanned/image documents | Different infra/cost profile; would slow the core loop | `decisions.md` OQ-05 |
| Billing/subscription enforcement (Stripe) | Product-loop validation comes before monetization plumbing | `decisions.md` OQ-09 |
| Public API keys (`FR-SETTINGS-002`) | No external API consumers at launch | `requirements.md` FR-SETTINGS-002 |
| Self-service trash/restore (vs. support-assisted recovery within the retention window) | Nice-to-have UX on top of the retention policy already in place | `privacy.md` |
| Reranking in RAG | Quality enhancement, not required to meet MVP retrieval quality bar | `rag.md` §Reranking |
| Human-in-the-loop LangGraph pauses (e.g., low-confidence extraction confirmation) | Adds UX/state complexity beyond MVP scope | `langgraph.md` §Human-in-the-loop |

## Requirement → Phase Cross-Reference (P0 only)

| Requirement ID | Phase |
|---|---|
| FR-AUTH-001..008 | 2 |
| FR-USER-001..003 | 2, 4 (usage display depends on Phase 4/14 data) |
| FR-DOC-001..008 | 4, 5 |
| FR-PROC-001..005 | 5, 6 |
| FR-RAG-001..003 | 6, 7 |
| FR-AI-001..006 | 8, 9 |
| FR-SUM-001..002 | 8, 10 |
| FR-EXT-001..004 | 8, 11 |
| FR-COMP-001..003 | 8, 12 |
| FR-SEARCH-001..003 | 13 |
| FR-ANALYTICS-001 | 14 |
| FR-ADMIN-001..003 | Interleaved with 2/4 (admin views existing data) — hardened in 15 |
| NFR-SEC-*, NFR-PRIV-* | Inline per phase, swept in 15 |
| NFR-PERF-* | Inline per phase, validated in 19 |
