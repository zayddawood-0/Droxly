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

## ADR-018: Frontend charting library — Recharts (via shadcn's `chart.tsx` primitives)

- **Decision:** `recharts` is the charting library for Analytics' line/bar charts, wrapped through shadcn's standard `ChartContainer`/`ChartTooltip`/`ChartLegend` primitives (`components/ui/chart.tsx`, added via the shadcn CLI — consistent with every other `components/ui/*` primitive in this codebase) rather than a hand-rolled SVG chart or a heavier dashboard-chart package.
- **Context:** Flagged as an open decision in the approved frontend implementation plan ("a minimal charting library for Analytics — 'flat, no 3D/gradient decoration' is specified; the library is not") and left unresolved through Phases 1–13 because no phase needed it until Analytics (Phase 14). `ui-ux.md` §13 requires "minimal chart components (line/bar — flat, no 3D/gradient decoration, consistent with brand restraint)."
- **Alternatives considered:**
  - **visx** (Airbnb) — lower-level primitives, smaller core bundle, but requires assembling axes/tooltips/grids by hand for even a simple line/bar chart; more implementation surface than two small charts justify.
  - **Nivo** — batteries-included and visually rich, but its defaults lean toward gradients/decoration that would need overriding throughout to satisfy the "flat, no 3D/gradient" requirement — fighting the library rather than using it.
  - **uPlot / lightweight-charts** (canvas-based) — excellent performance and the smallest bundle, but canvas rendering means building the accessible text/table fallback `ui-ux.md` §13 requires entirely from scratch, with no DOM nodes for assistive tech to read.
  - **Hand-rolled inline SVG** — zero dependency, but reimplements axis ticks, responsive sizing, and tooltip positioning that a maintained library already solves correctly; not justified by two chart types.
- **Reason:** Recharts is SVG-based (real DOM nodes, easier to pair with an accessible fallback), themes entirely through CSS custom properties that map directly onto this project's existing design tokens (`--color-primary`, `--color-muted-foreground`, etc. — no gradient/3D defaults to strip out), and shadcn ships an official, already-Tailwind-integrated wrapper (`chart.tsx`) with no Radix dependency, so it drops into this Base UI-based project with zero friction alongside every other `components/ui/*` primitive.
- **Consequences:** `recharts` (`^3.8.0`) is a new frontend dependency (`package.json`). `components/domain/analytics/{line-chart,bar-chart}.tsx` wrap `ChartContainer` with Doxly-specific defaults (flat lines/bars, no gradients, tick-density simplification at mobile width) rather than exposing raw Recharts props to page code, keeping the "flat, no 3D/gradient decoration" rule enforced in one place instead of re-applied at every call site.
- **Status:** Decided.

## ADR-019: CI/CD pipeline implementation — GitHub Actions job graph, GHCR as the backend/worker registry

- **Decision:** `devops.md` §5–6's CI/CD design (lint → type-check → test → build → deploy-gate-on-main) is implemented as two GitHub Actions workflows: `.github/workflows/ci.yml` (runs on every PR and on push to `main`; the `deploy` job is gated to `main`-only via `if:`) and `.github/workflows/nightly.yml` (scheduled cron + manual `workflow_dispatch`; runs the slower E2E and AI-regression tiers per `testing.md` §7's "may run as a separate, slower CI job ... rather than blocking every PR"). The backend/worker image is pushed to the **GitHub Container Registry (GHCR)** — `ghcr.io/<owner>/doxly-backend` — authenticated with the workflow's own built-in `GITHUB_TOKEN`, not a third-party registry requiring a separately provisioned credential.
- **Context:** `devops.md` §6 left "the exact registry" as a production-topology decision explicitly deferred to `deployment.md`; `deployment.md` never picked one either. Phase 18 (`roadmap.md`) is the phase whose job is to actually wire the pipeline, so the decision had to be made here rather than deferred again.
- **Alternatives considered:**
  - **Docker Hub** — the default many tutorials use, but requires provisioning and storing a separate `DOCKERHUB_TOKEN` repo secret before any image can be pushed at all, and free-tier pull-rate limits are a real operational risk for a production pull path.
  - **A cloud-specific registry (ECR/GCR/ACR)** — the natural choice once the container platform is AWS ECS/Fargate (`ADR-007`'s scale-up path), but MVP's container platform is still an open choice (Fly.io/Railway, see the new OQ-13 below); picking a cloud registry now would couple the image-storage decision to a platform decision that hasn't been made.
  - **The container platform's own built-in registry** (Fly.io and Railway both offer one) — viable, but ties the image to whichever platform is chosen, which is exactly the coupling this project's `StorageProvider`-style "decide the mechanism, defer the provider" pattern (`ADR-009`) tries to avoid elsewhere.
- **Reason:** GHCR requires zero additional secret provisioning to reach a working push (the workflow's ambient `GITHUB_TOKEN` already has `packages: write` once the workflow permission is granted), keeps the image co-located with the source repo for traceability (a pushed tag maps 1:1 to a commit SHA), and is platform-agnostic — whichever container platform OQ-13 resolves to, it pulls from the same GHCR image rather than needing a registry migration alongside the platform decision.
- **Consequences:** The actual `flyctl deploy`/`railway up` (or equivalent) step that pulls this image onto the chosen container platform is written as a conditional step gated on a platform-specific secret (`FLY_API_TOKEN` or `RAILWAY_TOKEN`) being present in the repository's secrets — until a human with dashboard access provisions that secret and resolves OQ-13, the workflow builds/pushes the image correctly but the final "deploy onto the platform" step no-ops with a clear log message rather than failing the pipeline. Frontend deploy is **not** a GitHub Actions step at all — per `devops.md` §6, Vercel's own GitHub App integration deploys `main` pushes and PR previews independently once a human connects the repository in the Vercel dashboard (a one-time manual setup step outside this repo's scope, same category as GHCR's `packages: write` permission grant).
- **Status:** Decided (registry + workflow shape). Platform destination remains open — see OQ-13.

## ADR-020: Email provider abstraction — Fake default, stdlib SMTP as the real implementation

- **Decision:** A new `EmailProvider` interface (`backend/app/core/email.py`) mirrors the existing `LLMProvider`/`EmbeddingProvider` pattern (`ADR-011`/`ADR-012`): an ABC, a `FakeEmailProvider` (records sent messages in-memory, zero external calls) as the active default until `EMAIL_PROVIDER=smtp` is configured, and one real implementation, `SMTPEmailProvider`, built on Python's stdlib `smtplib`/`email.message` rather than a new dependency.
- **Context:** `tasks/remediation-plan.md` R1 requires email delivery for `FR-AUTH-002` (verification) and `FR-AUTH-007` (password reset), and explicitly scoped "a minimal EmailProvider abstraction mirroring the existing LLMProvider/EmbeddingProvider pattern" as part of R1's implementation — no vendor was named in any prior spec, so the choice had to be made here.
- **Alternatives considered:**
  - **A SaaS provider SDK** (SendGrid, Postmark, Resend, etc.) — better deliverability tooling (bounce handling, templates) at production scale, but a new third-party dependency and a real account/API key to provision before *any* environment (including local dev/CI) could send a real email; `CLAUDE.md` §5's "a new library is a deliberate choice ... not a convenience reach" argues against pulling one in before a production email volume actually demands it.
  - **No real implementation at all (Fake-only)** — rejected because `FR-AUTH-002`/`FR-AUTH-007` are real product requirements (P1/P0 respectively) that need to actually reach a user's inbox in production eventually; leaving no real path would silently defer that indefinitely.
- **Reason:** stdlib SMTP requires zero new dependency and works against any SMTP-speaking provider (a transactional-email vendor's SMTP relay, a self-hosted relay, etc.) via configuration alone (`SMTP_HOST`/`PORT`/`USERNAME`/`PASSWORD`), keeping the vendor choice a deployment-time config decision rather than a code dependency — the same "decide the mechanism, defer the provider" shape as `ADR-009`'s `StorageProvider`.
- **Consequences:** `FakeEmailProvider` is what every test in this codebase runs against (matching `llm_provider`/`embedding_provider`'s own "fake by default" convention in `core/config.py`) — no test in this remediation effort sends a real email. A future phase may still swap in a SaaS SDK-backed `EmailProvider` implementation behind the same interface without touching `auth_service.py`/`user_service.py`, exactly as `ADR-009` allows for storage.
- **Status:** Decided.

## ADR-021: Rate-limiter Redis unavailability — fail open, not closed

- **Decision:** `backend/app/core/rate_limit.py`'s token-bucket and auth-throttle checks **fail open** on a Redis connection error — the request is allowed through (and a warning is logged) rather than rejected.
- **Context:** `api.md` §0.7 and `security.md` §2.4 specify the rate-limiting *behavior* (60/min general, 10/min + daily cap for AI-invoking routes, 5-failure/10-minute auth throttle) but neither specifies what happens if the Redis backend itself is unreachable — flagged as an open implementation decision in `tasks/remediation-plan.md` R1 §4.2, resolved here.
- **Alternatives considered:** **Fail closed** (reject every request with `503` while Redis is down) — rejected because it would turn a rate-limiter outage into a full API outage, directly contradicting `NFR-AVAIL-001`'s "core functionality remains available even if a supporting subsystem is degraded" principle (written for the AI subsystem specifically, but the same reasoning applies to any non-essential supporting service).
- **Reason:** A rate limiter's job is to protect the system from abuse/overload; losing that protection temporarily during a Redis outage is a materially smaller harm than losing the entire API for every legitimate user during the same outage. The brute-force-protection tier (`AuthThrottle`) losing its throttle during a Redis outage is the one place this trade-off has a real security cost — accepted as a bounded, logged, temporary degradation rather than a silent one.
- **Consequences:** Every Redis-unavailable event logs a warning (`rate_limit.redis_unavailable`) so an outage is operationally visible even though it isn't user-visible; `observability.md`'s eventual alerting setup (R12) should alert on this log event specifically, since it marks a period of reduced abuse protection.
- **Status:** Decided.

## ADR-022: StorageProvider default implementation — local filesystem, backdated

- **Decision:** `LocalFilesystemStorageProvider` (`backend/app/core/storage.py`) is the active `StorageProvider` implementation until real cloud storage credentials are configured (`storage_provider` setting), writing uploaded bytes to local disk and serving "presigned" URLs via a small local-only receiving endpoint (`api/v1/routers/local_storage.py`) that stands in for a real provider's presigned-URL mechanism in dev/test. `ADR-009` already decided the *mechanism* (presigned URLs, direct-to-storage upload); this entry records the concrete default *implementation* that mechanism runs against today, mirroring the same "real, working local default until a real credential is supplied" pattern already used for `LLMProvider`/`EmbeddingProvider`/`EmailProvider`.
- **Context:** R2's own code comments (`core/storage.py`) have referenced this ADR number since R2 landed; it was never actually written down — a documentation gap this task (R3) closes while already editing this file for `ADR-023`, rather than leaving a dangling cross-reference. Not an R3 architectural decision itself — backdated to R2, where the actual choice was made.
- **Reason:** A real, working filesystem-backed implementation (not a mock) lets the full upload → confirm → **process** pipeline run end-to-end in local dev/CI without any cloud account, while keeping FastAPI's own request handlers untouched by the actual file bytes either way (the local receiving endpoint plays the browser-facing role a cloud provider's own presigned endpoint would).
- **Status:** Decided (documentation backdated); cloud provider choice remains **Open**, see `OQ-04`.

## ADR-023: Document-processing enqueue failure mode — fail open, mirroring ADR-021

- **Decision:** `backend/app/core/queue.py`'s `enqueue_document_processing` **fails open** on a Redis connection error — the confirm-upload/reprocess request still succeeds (the document is left `queued`, a warning is logged) rather than the request failing with a `500`.
- **Context:** `ADR-008` decided RQ/Redis as the queue mechanism but never addressed what happens if enqueuing itself fails at the moment `DocumentService.confirm_upload`/`reprocess_document` calls it — a gap in the same shape `ADR-021` already resolved for the rate limiter, surfaced here as R3 (`tasks/remediation-plan.md`) actually wires the enqueue call up for the first time.
- **Alternatives considered:** **Fail closed** (reject the confirm/reprocess request with a `5xx` if Redis is unreachable) — rejected for the same reason `ADR-021` rejected it for rate limiting: a transient Redis outage would otherwise take down document uploads entirely, contradicting `NFR-AVAIL-001`.
- **Reason:** A document left `queued` with no job enqueued is a bounded, operationally-visible gap (the logged warning) rather than a user-facing failure of an otherwise-successful upload; a human/alert can notice the warning and manually trigger `POST /documents/{id}/reprocess` once Redis recovers, which re-enqueues cleanly (`FR-PROC-005`).
- **Consequences:** No automatic re-enqueue exists for a document stuck `queued` due to a missed enqueue — recovery is manual (`reprocess`) or a future operational job (not built by this task). `observability.md`'s eventual alerting (R12) should alert on the `document_processing.enqueue_failed` log event, the same way it's expected to alert on `rate_limit.redis_unavailable`.
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
- **Status:** **Decided, confirmed at Phase 8 implementation time.** `app/ai/llm.py`'s `ANTHROPIC_MODEL_IDS` table maps `STANDARD` → Claude Sonnet 5, `FAST` → Claude Haiku 4.5 — the one place a model upgrade happens, matching ai.md §2's "a model upgrade is a config change, not a code change across every node." `LLMProvider` ships with `AnthropicLLMProvider` (this real, tier-mapped default) and `FakeLLMProvider` (deterministic/scriptable — the active default until `ANTHROPIC_API_KEY` is configured, and the required provider for LangGraph node tests per `testing.md` §4.1's "LLM call mocked"), mirroring OQ-03's Phase 6 resolution for embeddings exactly.

### OQ-03 — Embedding provider & dimensionality
- **Question:** OpenAI vs. Voyage AI vs. open-source embeddings?
- **Recommended default:** OpenAI `text-embedding-3-small`, 1536 dimensions (ADR-012).
- **Why:** Cheapest, most documented, sufficient quality for document RAG at MVP scale; swappable later.
- **Status:** **Decided, confirmed at Phase 6 implementation time.** `EmbeddingProvider` (ADR-012) ships with two implementations: `OpenAIEmbeddingProvider` (the real `text-embedding-3-small` default, activated by setting `EMBEDDING_PROVIDER=openai` + `OPENAI_API_KEY`) and `FakeEmbeddingProvider` (deterministic, feature-hashing based, zero-cost — the *active default* until a key is supplied, and permanently the required provider for RAG-layer tests per `testing.md` §4's "never a live embedding API call in this layer"). No product/service code depends on which one is active — only `app/ai/embeddings.py`'s `get_embedding_provider()` reads the setting. Switching to real embeddings for a given environment is a config change, not a code change.

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

### OQ-12 — Nonce-based CSP `script-src` for the frontend
- **Question:** Can the frontend's `script-src` directive drop `'unsafe-inline'` in favor of Next.js 16's per-request Proxy-nonce pattern (`security.md` §11.3)?
- **What was tried:** Implemented during Phase 15 (Security Hardening) as `proxy.ts` (Next.js 16's renamed `middleware.ts` convention), generating a fresh nonce per request and setting `script-src 'self' 'nonce-<value>' 'strict-dynamic'`. Verified working correctly under `next dev` (confirmed via a real browser: no CSP console violations, hydration succeeds, the full E2E suite passes against the dev server). Failed under this project's actual production configuration (`output: "standalone"` + Turbopack, `next build && next start`, the exact setup `playwright.config.ts`'s `webServer` and `Dockerfile` both use): several of Next.js's own static `<script src>` tags in the production HTML response are not nonce-stamped, so the nonce'd policy blocks the app's own hydration scripts — the app renders its server shell but never becomes interactive. Reproduced consistently across multiple clean rebuilds, not a transient flake.
- **Recommended default:** `script-src 'self' 'unsafe-inline'` (and `style-src` identically, needed regardless for `components/ui/chart.tsx`'s injected color-token `<style>` tag, ADR-018) until Next.js's Proxy-nonce auto-stamping is confirmed reliable for this exact build configuration. The residual risk is low today: the XSS audit performed alongside this decision found exactly one `dangerouslySetInnerHTML` in the entire frontend, and its content is always static app config, never document- or user-derived — there is no known path today for an attacker to get their own inline script onto the page even with this directive relaxed.
- **Why:** Shipping a CSP that breaks the app in production is a worse outcome than a real, slightly-less-strict CSP that actually protects the site (blocks all external script/style/image/font/connect origins, framing, and plugin objects) — `'unsafe-inline'` on `script-src` is the one directive not at its strictest possible value, not a broadly weakened policy.
- **Status:** **Assumption** — revisit when upgrading Next.js, and re-run this same before/after production-build verification before attempting the nonce approach again.

### OQ-13 — Container platform destination — RESOLVED: Railway

- **Decision:** **Railway** hosts the FastAPI backend and the RQ worker as two separate Railway services built from the same repository/image (mirroring `docker-compose.yml`'s existing `backend`/`worker` split — same build context, different start command), plus Railway's managed PostgreSQL and Redis add-ons for this project. The Next.js frontend is unaffected by this decision — it continues to deploy to Vercel per `ADR-007` (still Decided, not reopened here).
- **Context:** This question was originally left open because provisioning a container-platform account/project and its API token is an action with real-world side effects (billing, a live deployment target) that only a human with dashboard/billing access can make — the same category as `OQ-04`'s storage-provider provisioning. The product owner has now made that decision explicitly (release-closure pass, 2026-08-29): Railway.
- **Alternatives considered:** Fly.io (this ADR's own prior recommended default, per `ADR-007`'s ordering) and AWS ECS/Fargate (`ADR-007`'s named scale-up path) — both remain valid future migration targets if Railway's platform limits are outgrown, since nothing in the application code is Railway-specific (the `StorageProvider`/`LLMProvider`/`EmbeddingProvider` abstraction pattern this codebase already uses elsewhere has no container-platform equivalent to migrate — the backend/worker images and their env-var-driven configuration are portable as-is).
- **Reason:** Product decision, not a technical re-derivation of `ADR-007`'s recommendation ordering — recorded here as the authoritative resolution regardless of which alternative would have been argued for technically.
- **Consequences:**
  - `backend/Dockerfile` deploys to Railway **unmodified** — Railway supports "deploy from Dockerfile" per service, and the existing multi-stage, non-root, healthcheck-bearing image needs no Railway-specific changes.
  - The worker service reuses the identical image with its start command overridden to `rq worker document_processing extraction comparison summary --url $REDIS_URL` (Railway's per-service "Custom Start Command" setting) — exactly the same pattern `docker-compose.yml`'s `worker` service already uses, not a new mechanism.
  - **Two genuine compatibility points found and flagged, not silently resolved** (full detail in `deployment.md` §15): (1) Railway's auto-generated Postgres `DATABASE_URL` uses the bare `postgresql://` scheme, but this codebase's SQLAlchemy async engine requires `postgresql+asyncpg://` — the backend/worker services' own `DATABASE_URL` variable must be set explicitly (via Railway's `${{Postgres.PGUSER}}`-style variable references) with the correct scheme, not bound directly to Railway's auto-generated reference. (2) Railway's default managed Postgres template's `pgvector` extension availability could not be verified without a live account — `deployment.md` §15 recommends deploying Postgres via a custom Docker image (`pgvector/pgvector:pg16`, the exact image `docker-compose.yml` already uses) as the safe, verified-equivalent option if the managed template doesn't ship the extension.
  - Google OAuth's registered redirect URI must be the **frontend's** (Vercel) production domain + `/api/v1/auth/oauth/google/callback` (`backend/app/api/v1/routers/auth.py`'s `redirect_uri` is built from `settings.frontend_base_url`, not the backend's own origin) — a Railway-specific pitfall only in the sense that it's easy to mistakenly register the Railway domain instead; the underlying behavior predates this ADR and is unchanged by it.
  - `.github/workflows/ci.yml`'s conditional deploy-gate step now checks for `RAILWAY_TOKEN` instead of `FLY_API_TOKEN`, keeping `ADR-019`'s established "builds and pushes to GHCR unconditionally, deploys only if the secret exists" no-op-until-provisioned behavior — no functional change to the gate's safety property, only which secret name it watches for.
- **Status:** **Decided.** Provisioning the actual Railway account/project/secrets and performing the first real deploy remain outstanding, human, non-code actions — tracked as deployment execution steps (`deployment.md` §15), not as an open architectural question anymore.

---

## ADR-024: Chat stop-signal transport — Redis, not an in-process registry

- **Decision:** `POST /chat/conversations/{id}/messages/{message_id}/stop` (`FR-AI-006`) signals an in-flight streaming turn via a short-TTL Redis key (`core/chat_stream_control.py`), keyed by the **user** message's id, polled by the streaming generator between generation steps and during the final chunk-relay — not a plain in-process `dict`/`asyncio.Event` registry.
- **Context:** the API is required to be stateless and horizontally scalable (`NFR-SCALE-001`); a `/stop` request can land on a different replica than the one holding the in-flight generator's task, so any in-process signaling mechanism would silently fail to reach it whenever a deployment runs more than one API replica.
- **Alternatives considered:** an in-process registry (rejected — correct only for a single-replica deployment, a silent trap the moment `NFR-SCALE-001` is actually exercised); a database row/flag (rejected — Redis is already the established low-latency, high-frequency-poll store for this kind of cross-request signal, per `ADR-008`/R1's rate limiter; a DB round-trip per poll would be needless extra load on Postgres for a purely ephemeral signal).
- **Reason:** reuses the already-established Redis infrastructure (`decisions.md` ADR-008, R1's rate limiter) for exactly the kind of cheap, ephemeral, cross-replica coordination it's already used for, rather than inventing a new shared-state mechanism.
- **Consequences:** fails open on a Redis outage (mirrors `ADR-021`/`ADR-023`) — `/stop` would report `409 not_in_progress` rather than actually stopping anything, a bounded, logged degradation rather than a request failure. `tasks/R4-chat.md` documents why the signal is keyed by the *user* message's id (matching `frontend/hooks/use-chat-stream.ts`'s already-built behavior) rather than an assistant message id that doesn't exist yet at the moment a user can click "stop."
- **Status:** Decided.

## ADR-025: Chat streaming answer generation — `LLMProvider.generate()`, not `.stream()`

- **Decision:** `chat_service.py`'s Answer Generator step calls `LLMProvider.generate()` (single-shot, non-streamed) to obtain the complete answer, then chunks the *already citation-validated* final text word-by-word for the client-facing `event: token` stream — it does not call `LLMProvider.stream()` for the live provider-level token feed `ai.md` §2 describes as "used only by the inline chat path."
- **Context:** `langgraph.md` §2's Citation Validator node explicitly "post-processes the **completed** answer" and forces the safe fallback response *after* generation if the answer is ungrounded (`ai.md` §8 point 1: checked "before a response is **returned**") — `FR-AI-004`'s absolute "no fabricated citation" guarantee (`ai.md` calls this "Doxly's core trust promise"). Relaying raw provider tokens live, before that check runs, would let an ungrounded answer reach the user before the safety net could apply, with no way to retract already-sent SSE events.
- **Alternatives considered:** true live token relay via `.stream()`, buffering all tokens server-side before deciding whether to show them — rejected because `.stream()`'s `AsyncIterator[str]` interface carries no accompanying token/usage-count channel; getting `NFR-OBS-001`'s required accurate `input_tokens`/`output_tokens`/`model` would then require an approximate, self-computed token count (a strictly worse substitute for data the provider already returns for free via `generate()`'s `Completion`).
- **Reason:** prioritizes the P0 anti-hallucination guarantee and P0 observability accuracy over literally satisfying `ai.md`'s abstract description of which method chat uses — both requirements are P0; the streaming *transport* to the browser (`FR-AI-005`, P1) is still fully satisfied via the chunked relay, which is observably indistinguishable to the client from true token streaming.
- **Consequences:** `/stop` (`FR-AI-006`, P2) can only interrupt the chunk-relay phase, not the LLM call itself — accepted as a P2-vs-P0 trade-off, documented in `tasks/R4-chat.md`'s Known Limitations. `document_qa.py`'s `classifier_node`/`answer_generator_node` were extended (additively — see their own code comments) to also return the raw provider `Completion`, so this reuse needs no logic duplicated from the graph.
- **Status:** Decided.

## ADR-026: Worker crash recovery — time-based staleness on `reprocess`, not new stale-job infrastructure

- **Decision:** A document stuck in a non-terminal processing stage (`queued`/`extracting`/`chunking`/`embedding`) is recoverable through the existing `POST /documents/{id}/reprocess` endpoint (`FR-PROC-005`) once `document.updated_at` is older than `settings.document_processing_stale_threshold_seconds` (900s / 15 min). `api.md`'s reprocess entry is extended: its `409 invalid_status` guard now permits a stale non-terminal document exactly as it already permits a `failed` one, rather than only the latter. No new endpoint, table, column, or migration is introduced — `Document.updated_at` (`UpdatedAtMixin`) is already bumped by every real stage transition (`DocumentRepository.set_status`), so it is already a trustworthy "last processing activity" timestamp.
- **Context:** the R3 audit (`tasks/R3-document-processing.md`, finding H1) identified that a worker process crash (killed mid-job, OOM, host failure) between two `set_status` calls leaves a document permanently stuck in a non-terminal status — no exception is ever raised for RQ's own `Retry`/`on_failure` machinery (`document_processing_worker.py`) to act on, since the process died rather than the job failing. No prior spec (`requirements.md`, `document-processing.md`, `api.md`) defined any staleness threshold or automatic-recovery mechanism at all.
- **Alternatives considered:** (1) build R12's broader stale-job detection/alerting/health-check/auto-restart infrastructure now — rejected as out of R3's scope and explicitly excluded by the remediation instructions; a worker-fleet health-check system is a distinct, larger capability than "let a user manually recover their own stuck document." (2) A worker heartbeat/lease mechanism (each stage renews a lease; a watcher reaps expired leases) — rejected as the same over-engineering in different clothing: it requires new state, a new background process, and solves a problem (distinguishing "crashed" from "still running slowly") that a generous, documented time threshold already solves well enough for a P0 gate. (3) Inventing a threshold with no anchor — rejected per explicit instruction not to silently invent an arbitrary production policy.
- **Reason:** `performance.md`'s `NFR-PERF-004` is the one concrete number in the specs bearing on "how long should processing normally take" — 60s p95 for a typical 20-page document. 900s is 15x that: generous enough that a legitimately large document (up to the 25MB upload ceiling) still in progress is very unlikely to be misidentified as stuck, while still bounding how long a genuinely crashed document sits unrecoverable before a user can act. Reusing `reprocess` (rather than a new endpoint) keeps the recovery path minimal — same authorization, same chunk-deletion-then-requeue behavior, same tenant scoping, already tested.
- **Consequences:** this is a purely time-based heuristic, not a true liveness check — a real, legitimately-still-running job for an unusually large/slow document *could* theoretically be reprocessed out from under itself if it exceeds 900s, causing a duplicate enqueue for the same document. Accepted as a documented, bounded residual risk (not solved via heartbeats — see alternatives above) given `NFR-PERF-004`'s margin; `tasks/R3-document-processing.md` tracks this explicitly rather than treating it as fully closed. A future R12 stale-job/health-check pass may supersede this with true liveness detection; this ADR does not attempt to anticipate that design.
- **Status:** Decided.

## ADR-027: `generate_structured` returns usage data alongside its result

- **Decision:** `LLMProvider.generate_structured` returns a `StructuredCompletion[T]` (the validated result plus real `input_tokens`/`output_tokens`/`model`), not a bare `T`, mirroring `generate()`'s `Completion` exactly. Both concrete providers (`AnthropicLLMProvider`, `FakeLLMProvider`) and every existing caller (`extraction.py`'s Extraction Agent, `summarization.py`'s Quality Checker, `comparison.py`'s change-classification node — all pre-existing scaffolding) were updated to unwrap `.result`.
- **Context:** R5 (Extraction) needed to log a real, provider-reported `input_tokens`/`output_tokens` pair for the Extraction Agent's structured-output call (`NFR-OBS-001`) — the same quality bar R3's embedding-observability remediation set ("real token counts, not an estimate"). The prior `generate_structured` signature discarded all usage data, making this structurally impossible without either an interface change or a documented, permanent observability gap for the single most expensive call in the whole workflow.
- **Alternatives considered:** (1) leave the interface untouched and log `input_tokens=None`/`output_tokens=None` for this call specifically — rejected as needlessly under-satisfying `NFR-OBS-001`'s cost-visibility intent when a proper fix was cheap and safe. (2) Estimate tokens client-side via the existing `count_tokens()` word-count utility — rejected as a quieter inconsistency (an estimate sitting in the same column as every other operation's real provider-reported counts) than either the fix or an explicit `None`.
- **Reason:** **Flagged to the user via `AskUserQuestion` rather than decided unilaterally** (a real `LLMProvider` ABC change, `CLAUDE.md` §4 rule 4's "major architectural decision" bar) — the user selected extending the return shape. Zero real callers existed outside not-yet-wired scaffolding (summarization/comparison have no router/service yet either), making the change isolated and safe; it also sets up R6/R7 (both already calling `generate_structured`) with the same accurate accounting when they're eventually built.
- **Consequences:** any future caller of `generate_structured` must unwrap `.result` — a one-line change, already applied everywhere it's currently called. No behavior change for any live, wired feature (chat/document-processing are unaffected; neither uses `generate_structured`).
- **Status:** Decided.

## ADR-028: `PRESET_TEMPLATES` restructured into a single field-metadata registry

- **Decision:** `app/ai/graphs/extraction.py`'s `PRESET_TEMPLATES` changed from a flat `dict[str, dict[str, str]]` (field name → type only) to `dict[str, {name, description, fields: [{name, type, description, required}]}]` — one registry serving both the Schema Generator node's internal resolution and `GET /extractions/templates`' response (`api.md` §6). The last-resort generic fallback (`langgraph.md` §4's "generic key-fact schema... so extraction never has nothing to do") was split out as a separate `GENERIC_TEMPLATE_FIELDS` constant, deliberately excluded from `PRESET_TEMPLATES` so it can never be requested via `template_key` or appear in the templates listing.
- **Context:** the prior flat shape (predating R1–R4, from the original phase-scaffolding commit) could not represent per-field `description`/`required` metadata at all — meaning `GET /extractions/templates`' documented response shape and `FR-EXT-003`'s "required field" concept were both structurally unsupported. This surfaced only once R5 actually tried to wire the templates-listing endpoint against the pre-existing scaffold; `CLAUDE.md`'s "do not assume a requirement is implemented merely because similar code exists" applied directly here.
- **Alternatives considered:** a second, separately-maintained metadata dict (template name/description/required-field-names) layered alongside the untouched flat `PRESET_TEMPLATES` — rejected as the exact kind of duplicated business rule (`CLAUDE.md` §5's "a validation rule expressed once, referenced twice, never copy-pasted") that would silently drift the moment a field was added to one dict and not the other.
- **Reason:** a single source of truth for "what fields does this template have" outweighs the larger diff/test-update cost of restructuring — especially since this scaffolding had no wired callers yet (no router existed before this task), so the restructure could not break any real running feature.
- **Consequences:** `test_graph_extraction.py`'s existing assertions (predating this task) were updated to the new shape — same behaviors verified, different data shape. `ExtractionState.requested_schema`/`resolved_schema_json` changed from `dict[str, str]` to `list[dict]`, matching exactly the shape a user-supplied custom `schema` already arrives in from the API request and the shape persisted into `extractions.schema_json` — one shape end-to-end, no adapter needed between "preset" and "custom" schemas.
- **Status:** Decided.

---

## Changelog

- **2026-08-29** — `OQ-13` resolved: Railway selected as the production container platform for backend/worker (release-closure pass, `tasks/release-closure-plan.md`). Two compatibility points flagged (Postgres URL scheme, pgvector availability) — see `deployment.md` §15.
- **2026-08-26** — `ADR-027` (`generate_structured` usage-data return shape) and `ADR-028` (`PRESET_TEMPLATES` single-registry restructure) added — `tasks/R5-extraction.md`.
- **2026-08-26** — `ADR-026` (worker crash recovery via reprocess staleness threshold) added — `tasks/R3-document-processing.md` remediation.
- **2026-08-26** — `ADR-024` (chat stop-signal transport) and `ADR-025` (chat streaming design: `generate()` not `.stream()`) added — `tasks/remediation-plan.md` R4.
- **2026-08-25** — `ADR-022` (StorageProvider default implementation, backdated to R2) and `ADR-023` (document-processing enqueue fail-open, mirroring ADR-021) added — `tasks/remediation-plan.md` R3.
- **2026-08-25** — `ADR-020` (EmailProvider abstraction) and `ADR-021` (rate-limiter Redis-unavailable fail-open) added — `tasks/remediation-plan.md` R1.
- **2026-08-24** — `ADR-019` (CI/CD pipeline implementation) and `OQ-13` (container platform destination) added — `roadmap.md` Phase 18.
- **2026-08-19** — Initial ADR set and open-question defaults established during SDD initialization.
