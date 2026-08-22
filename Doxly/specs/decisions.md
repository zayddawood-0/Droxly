# Doxly — Architecture Decision Records (ADR) & Open Questions

> **Status of this document:** Source of truth for all cross-cutting technical decisions. Every other spec file MUST remain consistent with the decisions recorded here. When a decision changes, update it here first, then propagate to affected specs and note the change in the Changelog at the bottom of this file.

## How to read this file

Each ADR has:

- **Decision** — what was decided
- **Context** — why a decision was needed
- **Alternatives considered**
- **Reason** — why this option won
- **Consequences** — trade-offs, follow-on obligations
- **Status** — `Decided` (confident default, safe to implement against) or `Open` (assumption made to unblock spec work; must be revisited with a real product/business decision before or during the relevant implementation phase)

Per Section 37 of the initialization brief, every open question below has an explicit **recommended default** so implementation is never blocked. Nothing is invented silently — each is flagged.

---

## ADR-001: Frontend Framework — Next.js (App Router)

- **Decision:** Next.js (latest stable, App Router) + React + TypeScript.
- **Context:** Need a modern, SEO-capable, fast frontend with first-class Vercel deployment support.
- **Alternatives considered:** Remix, plain Vite + React SPA, SvelteKit.
- **Reason:** Best-in-class Vercel integration, React Server Components reduce client bundle size for a data-heavy dashboard app, huge ecosystem (shadcn/ui), mandated by the initialization brief.
- **Consequences:** Must design around the App Router's server/client component split (see `skills/frontend.md`). Long-running work cannot happen inside Next.js server actions/route handlers — it is proxied to the FastAPI backend.
- **Status:** Decided.

## ADR-002: Backend Framework — FastAPI (Python)

- **Decision:** FastAPI + Pydantic v2 + SQLAlchemy 2.x (async) + Alembic.
- **Context:** Need a Python backend for AI/document-processing workloads (LangGraph, LangChain, document parsing libraries are Python-native).
- **Alternatives considered:** Node/NestJS backend (would fragment the AI stack across languages), Django (heavier, less async-native, less suited to an API-first product).
- **Reason:** FastAPI gives async-native request handling, automatic OpenAPI schema generation (feeds `specs/api.md` directly), Pydantic validation matches our "validate everything at the boundary" principle, and it's the natural home for LangGraph/LangChain.
- **Consequences:** Two deployable services (Next.js + FastAPI) instead of one. Requires a documented API contract and CORS/auth story between them.
- **Status:** Decided.

## ADR-003: Database — PostgreSQL + pgvector

- **Decision:** PostgreSQL (14+) as the single system of record, `pgvector` extension for embeddings, stored in the same database (not a separate vector DB).
- **Context:** Need relational integrity for documents/users/conversations AND vector similarity search for RAG.
- **Alternatives considered:** Dedicated vector DB (Pinecone, Weaviate, Qdrant) alongside Postgres.
- **Reason:** One database means one transaction boundary (a document row and its embedding rows are consistent by construction), simpler multi-tenancy enforcement (row-level filters apply uniformly), lower operational surface for an early-stage product. pgvector's IVFFlat/HNSW indexes are sufficient at expected scale (see `specs/performance.md`).
- **Consequences:** If corpus size or QPS outgrows pgvector, a dedicated vector store becomes a future migration (isolated behind the retrieval abstraction in `specs/rag.md`).
- **Status:** Decided.

## ADR-004: AI Orchestration — LangGraph as the workflow engine

- **Decision:** All multi-step, stateful AI workflows (document Q&A, summarization, extraction, comparison) are modeled as LangGraph graphs. LangChain is used underneath for individual utilities (document loaders, text splitters, prompt templates) where it saves meaningful code, never as the orchestration layer itself.
- **Context:** These workflows have branching, retries, validation loops, and need durable state — a plain prompt-chaining script is insufficient and hard to test.
- **Alternatives considered:** Hand-rolled orchestration (function calling in a loop), CrewAI/AutoGen style multi-agent frameworks.
- **Reason:** LangGraph gives explicit state machines with typed state, conditional routing, retry/error edges, and checkpointing — matching exactly the four documented workflows in `specs/langgraph.md`. It is used because the workflows are genuinely stateful and multi-step, not for marketing value (explicitly required by the brief).
- **Consequences:** Team must understand LangGraph's state/node/edge model (see `skills/ai-engineering.md`). Graphs must be unit-testable independent of the LLM (mockable nodes).
- **Status:** Decided.

## ADR-005: API Style — REST (not GraphQL)

- **Decision:** REST/JSON over HTTPS, versioned under `/api/v1`.
- **Context:** Need a contract between Next.js and FastAPI, and eventually third-party/API consumers.
- **Alternatives considered:** GraphQL, tRPC (rejected because it couples client/server language, and our server is Python while client is TypeScript).
- **Reason:** FastAPI generates OpenAPI/JSON Schema automatically from Pydantic models, which becomes the enforceable contract for `specs/api.md`. REST is simpler to secure, cache, and rate-limit per-endpoint. Streaming (SSE) is needed for AI chat, which is simpler over REST/SSE than GraphQL subscriptions.
- **Consequences:** No single round-trip for deeply nested queries; the frontend composes multiple REST calls or uses purpose-built aggregate endpoints where justified.
- **Status:** Decided.

## ADR-006: Containerization — Docker + Docker Compose for local/dev parity

- **Decision:** Every service (Next.js, FastAPI, worker, Postgres, Redis) runs in Docker locally via `docker-compose.yml`. Images are the deployable unit for backend/worker in production.
- **Reason:** Guarantees dev/prod parity for the Python stack (native deps like `pypdf`, `python-docx`, `psycopg`) and keeps Postgres+pgvector version pinned.
- **Status:** Decided.

## ADR-007: Deployment split — Vercel for frontend only; containers for backend & workers

- **Decision:** Next.js frontend deploys to **Vercel**. FastAPI backend and the background worker deploy as **long-running containers** on a container platform (default recommendation: **Fly.io** or **Railway** for early stage; AWS ECS/Fargate as the scale-up path) — **not** Vercel serverless functions.
- **Context:** The brief explicitly warns: "Do not assume long-running document or AI processing should execute synchronously in a serverless request." Vercel serverless functions have execution time limits and no persistent process/queue consumer model, which is incompatible with document parsing, embedding generation, and multi-node LangGraph runs that can take tens of seconds to minutes.
- **Alternatives considered:** Running everything on Vercel using Edge/Node functions with a queue (Vercel does not offer a durable background worker primitive suitable for this without external infra anyway); AWS Lambda for backend (rejected for local dev-parity and cold-start reasons at this stage).
- **Reason:** Keeps Vercel for what it's best at (static/SSR frontend, global CDN, preview deployments) while giving AI/document workloads a real process that can hold DB connections, run Celery/RQ workers, and stream SSE responses without artificial timeouts.
- **Consequences:** Two deployment pipelines instead of one; CORS and auth cookie domain configuration must be handled across origins (see `specs/deployment.md`).
- **Status:** Decided.

## ADR-008: Background job infrastructure — Redis + task queue (RQ default, Celery-compatible)

- **Decision:** Document processing, embedding generation, and long AI workflows are enqueued to Redis and executed by a separate worker process, not inline in the request/response cycle. Default queue library: **RQ** (Redis Queue) for MVP simplicity; **Celery** documented as the drop-in upgrade path if scheduling/retries/routing needs grow.
- **Context:** FastAPI request handlers must return quickly; processing a 50-page PDF + embeddings + LangGraph classification cannot block an HTTP response.
- **Alternatives considered:** FastAPI `BackgroundTasks` only (rejected — not durable, dies with the process, no retry/visibility), Celery from day one (heavier operational footprint than needed for MVP).
- **Reason:** RQ is simple to run in Docker, has a clear job-status model that maps directly to the `ai_requests`/document `processing_status` fields in `specs/database.md`, and Redis is a small addition to the stack we already benefit from (rate limiting, caching).
- **Consequences:** Requires a Redis instance in every environment. Job status must be polled or pushed to the client (SSE/websocket) for UI progress indicators.
- **Status:** Decided.

## ADR-009: File storage — Object storage via presigned URLs (Vercel Blob default, S3-compatible interface)

- **Decision:** Uploaded files are stored in object storage, never on local disk or in Postgres. Uploads go directly from the browser to storage via a short-lived presigned URL (not proxied through the Next.js/FastAPI request body), to avoid Vercel's serverless request body limits and reduce backend load.
- **Reason:** See Open Question OQ-04 below — default provider is Vercel Blob for MVP given the Vercel frontend, with the storage layer built behind an abstraction (`StorageProvider` interface) so S3/Cloudflare R2/GCS can be substituted without touching business logic.
- **Status:** Decided (mechanism); provider choice is **Open**, see OQ-04.

## ADR-010: Authentication — Backend-issued JWT (access + refresh), httpOnly cookies, OAuth via Authlib

- **Decision:** FastAPI is the authentication authority. It issues short-lived JWT access tokens (~15 min) and longer-lived refresh tokens (~30 days), delivered to the browser as httpOnly, Secure, SameSite=Lax cookies set by Next.js route handlers that proxy the auth calls (BFF pattern). Password auth (bcrypt/argon2 hashing) plus OAuth2 (Google) via Authlib is supported.
- **Alternatives considered:** NextAuth.js/Auth.js as the sole auth system (rejected as primary because the source of truth for identity must live with the backend that also enforces authorization on every API call; using NextAuth would create two identity systems to keep in sync). Session-in-Postgres only (adds a DB round-trip to every request; JWT avoids this while refresh-token rotation bounds the blast radius of a leaked access token).
- **Reason:** Keeps a single source of truth for identity/roles next to the authorization logic that already lives in FastAPI (row-level tenant checks), while still giving the browser secure httpOnly cookies (not localStorage, to reduce XSS token theft risk).
- **Consequences:** Requires refresh-token rotation and revocation list (`specs/security.md`), and CORS credentials configuration across the two origins.
- **Status:** Decided (mechanism). See OQ-01 for the specific provider/social-login default.

## ADR-011: LLM provider abstraction — Anthropic Claude as default primary provider

- **Decision:** All LLM calls go through a `LLMProvider` interface (`specs/ai.md`). Default configured provider: **Anthropic Claude** (Claude Sonnet class model for general chat/RAG answers, a smaller/faster Claude model for cheap classification steps in LangGraph). OpenAI is documented as the supported fallback/alternate provider.
- **Reason:** Best-in-class instruction following and long-context handling for document-grounded Q&A; strong structured-output/tool-calling support needed for the extraction workflow. An abstraction layer means the product is not hard-locked to one vendor.
- **Status:** Decided (abstraction is mandatory); specific model IDs are an **Open** operational detail revisited per `specs/ai.md` model-selection table as new model versions ship.

## ADR-012: Embedding provider abstraction — OpenAI `text-embedding-3-small` as default

- **Decision:** Embeddings go through an `EmbeddingProvider` interface. Default: OpenAI `text-embedding-3-small` (1536 dimensions). Every stored embedding row records the `embedding_model` and `embedding_dim` used, so multiple models can coexist during a migration.
- **Alternatives considered:** Voyage AI embeddings (strong quality, Anthropic-recommended for RAG), open-source local embeddings (BGE/E5, rejected for MVP — adds GPU/infra burden).
- **Reason:** Cheapest well-understood option with broad tooling support and a dimension (1536) that performs well with pgvector's default index types at our expected corpus size. Abstraction allows swapping to Voyage AI later without a schema change (only a re-embedding migration).
- **Status:** Decided (abstraction mandatory); provider choice is **Open**, see OQ-03.

## ADR-013: Multi-tenancy model — per-user isolation, not organizations, for MVP

- **Decision:** Every tenant-scoped row carries `user_id`. All queries are filtered by the authenticated user's ID at the repository layer (never trusted from client input). No shared "organization" or "team" workspace in the MVP schema beyond a nullable forward-compatible hook.
- **Reason:** Matches the stated MVP audience (individuals: students, freelancers, developers). Team/workspace sharing is a real future need (see `specs/roadmap.md` "Post-MVP") but adding it now would force premature multi-tenant-within-multi-tenant design.
- **Consequences:** Table design in `specs/database.md` includes `user_id` as a required column on all tenant data; a future `organization_id` can be added as an additive migration.
- **Status:** Decided.

## ADR-014: Document text extraction libraries

- **Decision:** `pypdf`/`pdfplumber` for PDF, `python-docx` for DOCX, native decode for TXT, Python `csv` module (via pandas for larger files) for CSV — all behind a `DocumentParser` interface keyed by MIME type (`specs/document-processing.md`).
- **Reason:** Mature, pure/near-pure Python libraries that run in the same container as the rest of the backend without external service dependencies for MVP file types.
- **Status:** Decided.

## ADR-015: Repository layout — sibling `frontend/` and `backend/` directories

- **Decision:** The repository is a single monorepo with two sibling top-level application directories: `frontend/` (the Next.js app) and `backend/` (the FastAPI app + worker, sharing one codebase/image per ADR-006). `specs/`, `skills/`, `tasks/`, and root-level `CLAUDE.md`/`README.md` remain at the repository root, outside both.
- **Context:** Next.js's App Router requires an `app/` directory as its routing root; `skills/backend.md`'s recommended FastAPI layout also names its top-level package `app/`. Both services living directly at the repository root would collide on that single `app/` directory the moment either was scaffolded — this had to be resolved before Phase 1's frontend scaffold could be written, not deferred.
- **Alternatives considered:** Two separate repositories (rejected — `specs/roadmap.md` Phase 1 treats both services as one repo's Phase 1 output, and a single PR/CI pipeline spanning both is assumed throughout `devops.md`); renaming FastAPI's package away from `app/` (rejected — fights `skills/backend.md`'s established convention for no real benefit).
- **Reason:** A sibling-directory monorepo is the minimal structural change that avoids the collision, keeps `docker-compose.yml`'s per-service build contexts simple (`context: ./frontend`, `context: ./backend`), and matches `deployment.md`'s independent-deploy-pipelines model (Vercel's root directory setting points at `frontend/`; the container platform's build context points at `backend/`) without requiring either service's internal structure (already specified in `skills/frontend.md` and `skills/backend.md`) to change.
- **Consequences:** Every path reference in `skills/frontend.md`'s folder structure (e.g. `app/`, `components/`, `lib/`) is relative to `frontend/`, not the repository root. `docker-compose.yml` and CI workflow paths must scope build contexts and cache keys per-service accordingly.
- **Status:** Decided.

---

## Open Questions (assumptions made to unblock the spec — flagged for product/business confirmation)

### OQ-01 — Authentication provider & social login
- **Question:** Email/password only, or also social login (Google/GitHub)?
- **Recommended default:** Email/password (argon2 hashing) + Google OAuth2 at launch. GitHub OAuth as a fast-follow (developer audience fit).
- **Why:** Google covers the broad Gen-Z/student/professional audience with minimal friction; GitHub OAuth is cheap to add later given the OAuth abstraction in ADR-010.
- **Status:** **Assumption** — confirm before Phase 2 (Authentication).

### OQ-02 — LLM provider & specific models
- **Question:** Which exact models back chat/summarization/extraction vs. cheap classification nodes?
- **Recommended default:** Primary: latest Claude Sonnet-class model for generation-quality nodes (answer generation, summarization, extraction). Secondary/cheap: latest Claude Haiku-class model for classification/routing nodes in LangGraph (query classifier, document classifier) to control cost/latency.
- **Why:** Matches cost/quality tiering already implied by the LangGraph node design in `specs/langgraph.md` (classifiers don't need the strongest model).
- **Status:** **Assumption** — revisit at Phase 8/9 implementation time as model catalog evolves.

### OQ-03 — Embedding provider & dimensionality
- **Question:** OpenAI vs. Voyage AI vs. open-source embeddings?
- **Recommended default:** OpenAI `text-embedding-3-small`, 1536 dimensions (ADR-012).
- **Why:** Cheapest, most documented, sufficient quality for document RAG at MVP scale; swappable later.
- **Status:** **Assumption** — confirm before Phase 6 (Embeddings & Vector Search).

### OQ-04 — File storage provider
- **Question:** Vercel Blob vs. S3 vs. Cloudflare R2 vs. GCS?
- **Recommended default:** Vercel Blob for MVP (zero-config with the Vercel frontend, presigned uploads supported natively). Interface (`StorageProvider`) allows swapping to Cloudflare R2 (cheaper egress) at scale.
- **Why:** Minimizes infra setup while the frontend is already on Vercel; avoids a third cloud vendor at MVP.
- **Status:** **Assumption** — confirm before Phase 4 (Document Management).

### OQ-05 — OCR for scanned/image-based documents
- **Question:** Should Doxly support OCR for scanned PDFs/images at launch?
- **Recommended default:** **Out of scope for MVP.** Scanned/image-only PDFs are detected (no extractable text layer) and surfaced to the user as "not supported yet" rather than silently failing. OCR (candidate: AWS Textract or `unstructured.io`) is a documented Post-MVP roadmap item.
- **Why:** OCR adds a materially different infra/cost profile (async external API, higher latency, error handling for low-confidence text) that would slow the MVP path from Upload → Ask.
- **Status:** **Assumption** — Post-MVP.

### OQ-06 — Maximum file size and per-request upload limits
- **Question:** What is the hard cap on a single uploaded document?
- **Recommended default:** 25 MB per file for MVP (covers the vast majority of student/professional PDFs and DOCX files), enforced both client-side (pre-upload check) and server-side (presigned URL policy + backend validation on the recorded object size before processing starts).
- **Why:** Large enough for typical academic papers, contracts, and reports; small enough to keep processing latency and embedding cost predictable. Bypasses Vercel body-size limits entirely via direct-to-storage upload (ADR-009).
- **Status:** **Assumption** — confirm against real usage data post-launch; make configurable per plan tier.

### OQ-07 — Storage quota per user/plan
- **Question:** How much storage and how many documents per tier?
- **Recommended default:** Free: 100 MB total / 10 documents. Pro: 5 GB total / unlimited documents.
- **Why:** Gives a meaningful but bounded free tier for evaluation; keeps infra cost predictable pre-monetization.
- **Status:** **Assumption** — depends on OQ-09 (subscription model), which is itself open.

### OQ-08 — Rate limits
- **Question:** What are acceptable request/AI-call rate limits per user?
- **Recommended default:** General API: 60 requests/minute/user. AI-invoking endpoints (chat, extraction, comparison, summarization): 10 requests/minute/user, plus a daily cap (Free: 30 AI requests/day; Pro: 500/day). Enforced via Redis token-bucket middleware.
- **Why:** Protects against runaway cost from a single account (own or compromised) while remaining unnoticeable in normal use.
- **Status:** **Assumption** — confirm against real LLM cost data.

### OQ-09 — Subscription/monetization model
- **Question:** Free/Pro/Team tiers — what exactly is gated, and is billing in scope for MVP?
- **Recommended default:** Billing/payment is **out of scope** for the initial implementation phases (Phases 1–19 in `specs/roadmap.md`). Tier flags (`plan: free | pro`) exist on the `users` table from the start so gating logic (storage quota, rate limits) has somewhere to read from, but Stripe integration is a named Post-MVP roadmap item.
- **Why:** Keeps early phases focused on the core Upload→Ask→Extract→Compare→Search loop; monetization plumbing can be added additively once the product loop is validated.
- **Status:** **Assumption**.

### OQ-10 — Background job infrastructure specifics
- **Question:** RQ vs. Celery vs. a managed queue (SQS)?
- **Recommended default:** RQ + Redis, self-hosted alongside the FastAPI container (ADR-008).
- **Why:** Lowest operational overhead that still gives durable, retryable, observable background jobs.
- **Status:** **Assumption** — revisit if job volume/complexity outgrows RQ's simpler feature set (favor Celery for complex retry/routing needs, or a managed queue if moving to serverless workers).

### OQ-11 — Team/organization support
- **Question:** Should documents be shareable across users (teams) at launch?
- **Recommended default:** No — individual accounts only for MVP (ADR-013). Documented as a Post-MVP roadmap phase.
- **Status:** **Assumption**.

---

## Changelog

- **2026-08-19** — Initial ADR set and open-question defaults established during SDD initialization.
