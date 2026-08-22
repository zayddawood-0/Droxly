# Doxly — Performance Requirements

> Expands `requirements.md` §2.1 (`NFR-PERF-001` .. `NFR-PERF-005`) from headline budgets into concrete performance strategies: how each budget is achieved architecturally, what's measured, and what happens under load or at scale. Every budget here is a target the implementation is built toward and validated against (`testing.md` load/perf test hooks), not a guarantee shipped on day one. This file owns performance budgets and technical strategy; it does not redefine loading-state visual design (`ui-ux.md`), LangGraph node design (`langgraph.md`, `ai.md`), or monitoring/alerting setup (`observability.md`) — it references those by filename where relevant.

## 1. Frontend Loading Performance

**Budget:** `NFR-PERF-001` — First Contentful Paint (FCP) on the dashboard ≤ 1.5s, warm cache, broadband connection.

| Metric | Target | Measured via |
|---|---|---|
| First Contentful Paint (dashboard, warm cache, broadband) | ≤ 1.5s (NFR-PERF-001) | Lighthouse CI / Web Vitals RUM |
| Largest Contentful Paint | ≤ 2.5s | Web Vitals RUM |
| Time to Interactive | ≤ 3.5s | Lighthouse CI |
| Initial route JS bundle | ≤ 200KB gzipped | `next build` bundle analyzer, CI budget check |

**Strategy — how the budget is achieved, not just measured:**

- **React Server Components by default.** Per ADR-001, the App Router's server/client split is used deliberately: pages that primarily display data (document list, dashboard, document detail metadata) render as Server Components so their HTML arrives without shipping the data-fetching or rendering logic as client JS. Client Components (`"use client"`) are reserved for genuinely interactive surfaces — chat input, the diff viewer, forms — keeping the initial client JS payload small and directly reducing time-to-FCP.
- **Route-level code splitting.** The App Router splits bundles per route by default; this must not be defeated by importing heavy, route-specific libraries (chart rendering for analytics, the diff-viewer for comparison reports, a rich-text renderer) into a shared layout or root bundle. Such libraries are imported only within the route/component that needs them, or `dynamic()`-imported so they load after first paint.
- **Image optimization.** All images (avatars, document thumbnails/previews) go through Next.js `<Image>` for automatic resizing, modern-format negotiation (AVIF/WebP), and lazy-loading below the fold — avoiding oversized image payloads blocking FCP/LCP.
- **Font loading strategy.** Fonts are loaded via `next/font` (self-hosted, not a render-blocking third-party `<link>` to a font CDN), which inlines `font-display: swap` behavior and eliminates a layout-shift-causing external request on first paint.
- **No waterfall requests on the dashboard.** The dashboard needs several independent pieces of data (recent documents, storage usage, AI usage stats). These are fetched in parallel — either as parallel `await Promise.all(...)`-style data fetches inside a single Server Component tree, or via Next.js parallel routes/`loading.tsx` boundaries per section — never as sequential client-side `fetch` calls awaited one after another, which would compound latency instead of bounding it to the slowest single call. Loading-state UI (skeletons, spinners) for the parallel-fetch panels is a `ui-ux.md` concern; this file only requires that the underlying requests fire in parallel, not sequentially.
- **Caching.** Static assets and prerendered routes are served from Vercel's CDN. API responses are not CDN-cached (per-user, tenant-scoped data), but the frontend uses client-side revalidation caching (SWR-style) for list views so switching tabs/navigating back doesn't re-trigger a full round trip within its cache window.

## 2. API Response Times

**Budget:** `NFR-PERF-002` — non-AI CRUD endpoints respond within 300ms p95.

| Endpoint category | Target (p95) | Notes |
|---|---|---|
| Non-AI CRUD reads (list/get) | ≤ 300ms | Requires pagination — see below |
| Non-AI CRUD writes (create/update/delete) | ≤ 300ms | Excludes the document-upload confirm call, which returns as soon as processing is enqueued (`architecture.md` §4), not when processing finishes |
| Presigned upload URL issuance | ≤ 200ms | No DB write beyond the initial `documents` row |

**Strategy:**

- **Repository-layer query efficiency.** Every repository method that backs a CRUD endpoint is written against an index that already exists in `database.md` (e.g., `(user_id, deleted_at)`, `(user_id, status)`, `(user_id, created_at DESC)`). A query pattern that doesn't hit an existing index is either given one via migration or the query is restructured — it is never shipped as an unindexed scan, since `user_id`-filtered tables are exactly the ones sized to matter at scale.
- **N+1 avoidance.** List views that include related data (e.g., documents with their tags, conversations with document scope) use a single query with a join or an explicit eager-load (SQLAlchemy `selectinload`/`joinedload`), never one query per row. This is checked as part of code review for any new list/detail endpoint touching a joined relation.
- **Pagination is mandatory** on any endpoint that could return unbounded rows: document list (`FR-DOC-002`), search results (`FR-SEARCH-001`), conversation message history, admin user directory (`FR-ADMIN-001`). Cursor or offset pagination with a hard max page size (default 50) — response time must not scale with total corpus size, since a user's document count or a conversation's message count is unbounded over the account's lifetime.
- **Connection pooling.** The SQLAlchemy async engine's connection pool is sized to container concurrency (starting point: pool size 10–20 per API/worker replica), tuned against observed Postgres `max_connections` and total replica count (`deployment.md`) so that request latency under concurrent load doesn't degrade from connection-acquisition wait time rather than actual query time.

## 3. Database Query Performance

Recap of the index strategy from `database.md` §1/§3, applied as a performance discipline:

- **Leading `user_id` columns.** Every tenant-scoped table indexes `user_id` as the leading column of at least one index (`database.md` §1 conventions), because every query touching tenant data filters on it (`NFR-SEC-001`, `architecture.md` §6). This is what keeps the mandatory tenant filter cheap rather than a full-table scan with a filter applied after the fact.
- **HNSW on `document_chunks.embedding`** for vector similarity queries — chosen over IVFFlat specifically because it doesn't require a separate training/list-count tuning step at Doxly's expected per-user corpus scale (`database.md` §3.4, ADR-003). Detailed in §6 below.

**Query patterns to avoid:**
- Unbounded scans — any query without a `LIMIT` and, for list endpoints, without pagination.
- Missing the tenant filter — a query on `document_chunks`, `documents`, `conversations`, etc. that omits `WHERE user_id = :user_id` (or a join that transitively carries it) is both a security bug (`NFR-SEC-001`) and a performance bug: without it, Postgres has no reason to use the `user_id`-leading index and may fall back to a full-table scan as the table grows.
- Filtering/sorting on an unindexed column at list-endpoint scale (e.g., sorting documents by a column with no index) — acceptable at low row counts, silently degrades as a user's document count grows.

**When a query needs an `EXPLAIN ANALYZE` review before shipping:** any new tenant-scoped list or search endpoint, any query added against `document_chunks` (given its embedding column and larger expected row count per user), and any query whose `WHERE`/`ORDER BY` doesn't map directly to an existing index in `database.md`. The review confirms the planner is using the intended index (not a sequential scan) against a realistically-sized seeded dataset — not just against an empty or near-empty dev database, which will hide a scan that only becomes a problem at production data volume.

## 4. Document Processing Performance

**Budget:** `NFR-PERF-004` — a 20-page PDF completes the full pipeline (`queued → extracting → chunking → embedding → ready`) within 60s p95.

| Stage | Approx. budget | Dominated by |
|---|---|---|
| Extraction | ≤ 10s | PDF parsing cost (`pypdf`/`pdfplumber`, ADR-014) — scales with page count and layout complexity |
| Chunking | ≤ 5s | Pure CPU text splitting, no external calls — smallest and most predictable slice of the budget |
| Embedding | ≤ 40s | Embedding-provider API round trips — the largest and most variable slice, and the stage most sensitive to batching (§5) |
| Status transition overhead | ≤ 5s | DB writes between pipeline stages |

This is a rough proportional allocation, not per-stage SLAs individually enforced — the 60s figure is what's measured and validated end-to-end.

**Where this is measured, and why it doesn't block interactive latency:** the entire pipeline runs in the background Worker process, not inline in an API request (ADR-008, `architecture.md` §4). The 60s p95 is measured worker-side, end-to-end from job dequeue to `documents.status=ready`, using the `ai_requests`/pipeline stage-transition logging described in `observability.md`. Because the API only enqueues the job and returns `202 Accepted` immediately (`architecture.md` §4 request flow), this budget is fully decoupled from `NFR-PERF-002`'s 300ms CRUD budget — a slow or backlogged processing pipeline never causes API request latency to degrade; it only delays when a specific document's `status` transitions to `ready`, which the frontend surfaces via polling/SSE (`FR-DOC-008`), not via a held-open request.

**Scaling with document size:** processing time scales roughly linearly with extracted text volume (more pages → more text → more chunks → more embedding calls), bounded in practice by the 25MB file size ceiling (`decisions.md` OQ-06). See §8 for how this ceiling is handled.

## 5. Embeddings Performance

- **Batching is required, not optional.** Chunks for a document are embedded via batched calls to the embedding provider (multiple chunks per API call, up to the provider's batch size limit) rather than one request per chunk. Batching is the primary lever on the embedding-stage budget in §4 — per-chunk requests would multiply round-trip latency (each carrying its own network + provider queueing overhead) by the chunk count instead of amortizing it across a batch.
- **Rate limit handling is queue-level backpressure, not per-document failure.** When the embedding provider returns a rate-limit response, the worker does not fail the whole document. The affected batch is retried with backoff (bounded by `NFR-AVAIL-002`'s max-3-attempts pattern), and sustained rate-limit pressure is absorbed by the job queue itself slowing consumption (fewer concurrent embedding jobs in flight) rather than surfacing as user-facing document failures. A document only reaches `status=failed` on a genuinely unrecoverable error, per `FR-PROC-004`.
- **Batch size is a cost/latency tradeoff.** Larger batches reduce total round-trip count and overhead (favoring throughput and lower cost) but increase the latency of any single batch and the amount of work retried if that batch fails. The default batch size is tuned toward the provider's practical maximum while keeping a single batch's retry cost small relative to the whole document's chunk count — an operational tuning parameter, not a fixed architectural constant.

## 6. Vector Search Performance

**Budget:** `NFR-PERF-005` — tenant-scoped vector similarity search returns within 200ms p95 at up to 50,000 chunks for a single user.

**Why the design in `database.md` achieves this:**

- **HNSW index on `document_chunks.embedding`** (`database.md` §3.4/§4) is what makes similarity search sub-linear in corpus size — without it, `ORDER BY embedding <=> :query_embedding LIMIT :k` would require scanning and scoring every candidate row. HNSW was chosen over IVFFlat specifically because it delivers strong recall without a separate training/list-count tuning step, which matters because Doxly's per-user corpus size varies widely and unpredictably (a student with 10 documents vs. a power user with hundreds) — a scheme that needed re-tuning per corpus size would be an operational burden IVFFlat's list-count parameter would impose.
- **Tenant-filter-first query pattern.** The denormalized `user_id` column on `document_chunks` (`database.md` §3.4 note) exists specifically so the mandatory `WHERE user_id = :user_id` predicate can be applied directly against an indexed column on the same table being searched, without a join back to `documents` to discover ownership. Combined with the `(user_id)` leading index, this keeps the tenant filter — which is present on every single retrieval query, per `NFR-SEC-001` — cheap rather than a per-query join tax. This is the mechanism that lets the 200ms budget hold: retrieval is filtering to one user's slice of the corpus first, then doing approximate nearest-neighbor search within that slice, not searching the whole multi-tenant table and filtering after.

**Scale-triggered future concern (not a current requirement):** the 50,000-chunk budget corresponds to a large but plausible single-user corpus at MVP scale. If a user's corpus grows well beyond this — hundreds of thousands of chunks for one account — two levers exist and are explicitly deferred until triggered by real usage data, not built preemptively:
1. **HNSW `ef_search` tuning** — increasing `ef_search` trades query latency for recall and can be adjusted per-query or globally as corpus size grows, without a schema change.
2. **Migration to a dedicated vector store** — foreshadowed in `decisions.md` ADR-003's consequences: pgvector was chosen for MVP because one transactional database is simpler to operate and keeps tenant isolation uniform, with the explicit acknowledgment that a dedicated vector store (Pinecone, Weaviate, Qdrant) becomes the right move if corpus size or query volume outgrows pgvector's practical envelope. This is called out here as the scale trigger for that migration, isolated behind the retrieval abstraction in `rag.md` so it wouldn't require rewriting retrieval call sites.

## 7. AI Response Performance

**Budget:** `NFR-PERF-003` — chat first-token latency ≤ 3s p95 for documents under 50 pages.

| Operation | Target | Notes |
|---|---|---|
| Chat — time to first token | ≤ 3s p95, docs < 50 pages (NFR-PERF-003) | Streamed inline in the API process, not queued (`architecture.md` §5) |
| Summarization | ≤ 45s p95 for a typical document | Background-worker job, async status pattern |
| Extraction | ≤ 45s p95 for a typical document | Same async pattern |
| Comparison | ≤ 90s p95 for two typical documents | Two documents processed + aligned; async pattern |

**Strategy for the 3s first-token budget:**

- **Streaming is what makes first-token the right metric.** Per `FR-AI-005` and ADR-005, chat responses stream token-by-token over SSE rather than waiting for the full completion. Perceived latency to the user is bounded by time-to-first-token, not total generation time — a long, thorough answer does not need to be fast end-to-end to feel fast, only to start quickly.
- **The hot path stays lean.** The LangGraph Document Q&A workflow (`architecture.md` §5, full node design in `langgraph.md`) runs Classifier → Retriever → Context Analyzer → Answer Generator → Citation Validator before the first token can stream. Only the Answer Generator node needs a full-quality generation-class model; the Classifier and other pre-generation nodes are budgeted to be fast by using a cheap/small model or non-LLM logic where the task doesn't require strong reasoning, per the tiered model strategy in `decisions.md` ADR-011/OQ-02 (Claude Sonnet-class for generation-quality nodes, Claude Haiku-class or non-LLM logic for classification/routing nodes). The rough budget split is retrieval (≤ 300ms, bounded by §6's vector-search budget) plus prompt assembly (≤ 200ms) plus provider time-to-first-token for the remainder — leaving the majority of the 3s allowance to the generation call itself rather than pre-processing.
- **No unnecessary sequential LLM calls in the hot path.** Every additional LLM call before the streamed Answer Generator call adds its own latency serially (LLM calls, unlike retrieval, don't parallelize well against each other when one's output feeds the next). The node design in `langgraph.md`/`ai.md` is the source of truth for which steps are LLM calls vs. cheaper logic; this file's constraint is that any node added ahead of the streaming response must be justified against its cost to the 3s budget, not added by default.

Summarization/extraction/comparison are deliberately budgeted more loosely than chat because the UI never blocks a live connection on them — the user sees a processing state and polls/subscribes for completion (`FR-SUM-001`, `FR-EXT-001`, `FR-COMP-001`), so a slower response costs UX patience, not a broken request.

## 8. Large Document Handling

As a document's size approaches the 25MB cap (`decisions.md` OQ-06), performance degrades predictably rather than falling off a cliff:

- **Chunking volume grows** roughly in proportion to extracted text length — more pages/content means more `document_chunks` rows and more embedding calls.
- **Processing time budget scales, not breaks.** The 60s p95 in `NFR-PERF-004` is defined for a 20-page/typical document; a document near the size ceiling is expected to take proportionally longer through the extract/chunk/embed pipeline (§4), but must still reach a terminal `status` (`ready` or `failed`) — it is never allowed to hang indefinitely (`FR-PROC-004`, `NFR-AVAIL-002`).
- **Retrieval speed stays flat regardless of document size.** This is the key property that makes large documents tolerable: chat/search retrieval (§6, §7) operates over indexed `document_chunks` rows at query time, not over the whole document's raw text. A 25MB document with thousands of chunks and a 2-page document with a handful of chunks both hit the same HNSW-indexed, tenant-filtered query shape — the retrieval budget in `NFR-PERF-005` is a function of the user's total corpus size (up to 50,000 chunks across all their documents), not of any single document's size. A large document costs more at ingestion time; it does not cost more at every subsequent question asked of it.

## 9. Concurrent Users

Horizontal scalability is the strategy for handling concurrent load, not vertical headroom on a single instance:

- **Stateless API replicas (`NFR-SCALE-001`).** The FastAPI backend holds no in-process session state — auth state lives in JWTs/DB (ADR-010), so any replica behind the load balancer can serve any request. This means API capacity scales by adding replicas (`architecture.md` §7 production environment: ≥2 API replicas), with no sticky-session constraint forcing load onto a subset of instances.
- **Worker pool scaled independently by queue depth (`NFR-SCALE-002`).** Document processing and async AI workflow load does not correlate 1:1 with interactive API request load — a burst of uploads doesn't mean a burst of chat requests, and vice versa. The worker pool's replica count is driven by Redis queue depth, not tied to API replica count, so processing throughput can be scaled up independently when the queue backs up (`architecture.md` §2.3, ADR-008).
- **Redis-backed rate limiting protects shared capacity.** Per `decisions.md` OQ-08 and `security.md`, per-user token-bucket rate limits (general API and, more tightly, AI-invoking endpoints) are enforced in Redis middleware ahead of the request reaching business logic. This is a performance property as much as a security one: it bounds how much of the shared API/worker/LLM-provider capacity any single user (or compromised/runaway account) can consume, so one user's burst of activity cannot degrade the response-time budgets in §2/§6/§7 for everyone else.
- **Connection pool sizing under concurrent load.** As API and worker replica counts scale out, the aggregate number of Postgres connections (replica count × pool size, §2) must stay within Postgres's `max_connections`; this is a deployment-time tuning concern (`deployment.md`) that becomes more pressing as concurrent user count and replica count both grow, not a fixed constant.

## 10. Performance Testing & Monitoring

- **Automated regression checks where feasible.** Budgets with a clear, repeatable query shape are good candidates for a lightweight automated check in CI or a scheduled job — for example, a load test against the vector-search query pattern in §6 run against a realistically seeded dataset (per the `EXPLAIN ANALYZE` guidance in §3), catching a regression before it reaches production rather than after. Frontend budgets (§1) are checked via Lighthouse CI bundle/FCP budgets on every build.
- **Production monitoring is out of scope for this file.** The actual metrics collected, dashboards, and alerting thresholds for latency, queue depth, error rates, and AI request cost/latency are defined in `observability.md`, which is being written as a parallel effort — this file defines what the targets are and why the design should hit them; `observability.md` defines how those targets are watched in production.

## 11. Performance Budget Summary

| Requirement ID | Budget | Primary strategy | Measured where |
|---|---|---|---|
| NFR-PERF-001 | Dashboard FCP ≤ 1.5s | Server Components, parallel data fetching, code splitting, optimized fonts/images (§1) | Lighthouse CI / Web Vitals RUM |
| NFR-PERF-002 | Non-AI CRUD p95 ≤ 300ms | Indexed repository queries, N+1 avoidance, mandatory pagination, connection pooling (§2) | API middleware timing / APM, per `observability.md` |
| NFR-PERF-003 | Chat first-token p95 ≤ 3s (docs < 50 pages) | Streaming, tiered model strategy for pre-generation nodes, lean hot path (§7) | Inline API/SSE timing, `ai_requests` table |
| NFR-PERF-004 | 20-page PDF pipeline p95 ≤ 60s | Async worker pipeline decoupled from API, batched embedding calls (§4, §5) | Worker-side stage-transition logging, end-to-end job duration |
| NFR-PERF-005 | Vector search p95 ≤ 200ms at ≤ 50k chunks/user | HNSW index + tenant-filter-first query pattern on denormalized `user_id` (§6) | DB query timing, load test against seeded corpus |
| (derived) | Summarization/extraction p95 ≤ 45s | Async worker job, no held-open request | Worker-side job duration |
| (derived) | Comparison p95 ≤ 90s | Async worker job, two-document alignment | Worker-side job duration |
| (derived) | Initial JS bundle ≤ 200KB gzipped | Route-level code splitting, dynamic import of heavy libs | `next build` bundle analyzer, CI budget check |
| NFR-SCALE-001 / 002 | Horizontal scale under concurrent load | Stateless API replicas, independently-scaled worker pool, Redis rate limiting (§9) | Replica count vs. load, queue depth monitoring (`observability.md`) |
