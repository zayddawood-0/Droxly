# Doxly — Database Engineering Skill

> How to work with Doxly's PostgreSQL + pgvector database well, day to day. `specs/database.md` is authoritative for *what* the schema is — every table, column, constraint, and index, including the HNSW vector index and the denormalized `document_chunks.user_id` — and is never re-derived here. This file is about *how* Claude Code and contributors write migrations, queries, and transactions against that schema without violating its invariants, chief among them multi-tenant isolation (`specs/decisions.md` ADR-013).

## Purpose

Doxly runs one Postgres database as the single system of record for relational data and vector search (`specs/decisions.md` ADR-003) — a deliberate choice to keep transaction boundaries and tenant filtering simple. That simplicity is only real if every contributor follows the same engineering discipline around it. This file is that discipline.

## 1. PostgreSQL Practice

- Connections go through SQLAlchemy 2.x's **async engine**, backed by `asyncpg` (or an async psycopg3 driver) — never a sync driver in request-serving code paths, per the async-native stance in `specs/decisions.md` ADR-002.
- **Transaction boundaries follow the operation, not the table.** A service-layer method that touches multiple tables as one logical unit of work (e.g., inserting a `documents` row and decrementing `users.storage_used_bytes`) commits as a single transaction — never as two independent writes that could leave the database in a half-applied state if the second one fails.
- **Never hold a transaction open across an external API call.** A DB transaction must not still be open while the code is waiting on an LLM call or an embedding provider round trip — that ties up a pooled connection for the duration of unpredictable network latency, defeating the point of a bounded pool. Structure the workflow so the external call happens first (or in its own step), and the transactional write that persists its result happens after, in a fresh, short-lived transaction.

## 2. pgvector Practice

- The vector column, its HNSW index (`vector_cosine_ops`), and the canonical parameterized query pattern are fully specified in `specs/database.md` §4 — that query shape (cosine distance via the `<=>` operator, ordered `ORDER BY embedding <=> :query_embedding`) is the one to reuse, not reinvent per call site.
- **Never run an unfiltered global vector search.** Every similarity query filters by `user_id` before or alongside the distance ordering — the `WHERE user_id = :user_id` predicate is not optional and not something to add "if there's time"; it is the DB-layer half of tenant isolation for retrieval.
- `ef_search` is HNSW's query-time knob for trading recall against latency (higher `ef_search` = better recall, slower query). It is not a value to guess at implementation time — tune it empirically against the retrieval budgets in `specs/performance.md` once real corpus/query patterns exist, and treat any change to it as a measured decision, not a default left untouched forever either.

## 3. SQLAlchemy Practice

- Models use SQLAlchemy 2.x declarative style with typed `Mapped[]` columns throughout — not the legacy `Column()`-only style. A model's relationships, FKs, and cascade rules mirror `specs/database.md` exactly.
- Relationship loading is explicit. Collection loads use `selectinload` to avoid N+1 query patterns — the concrete conventions and folder placement for this live in `skills/backend.md`, referenced rather than restated here.
- No raw SQL string interpolation, ever — this is the database-layer expression of `NFR-SEC-005` in `specs/requirements.md`. All queries go through SQLAlchemy Core/ORM constructs with bound parameters.
- Reach for Core's `text()` only when the ORM genuinely cannot express the query — the clearest example in this schema is the vector similarity query itself, which needs the `<=>` operator. `specs/database.md` §4 already shows the correct parameterized form for that query; follow it rather than building a new one.

## 4. Alembic Practice

- One migration per logical schema change. `--autogenerate` is a starting draft, never a commit-ready diff — it can miss index and constraint nuances, and it does **not** know how to generate pgvector's HNSW index on its own; that has to be written by hand into the migration.
- Migrations are never edited after merge/deploy. A mistake in an already-merged migration is corrected by a new forward migration, not a rewrite of history — reiterating `specs/database.md` §5's rule.
- Name migration files `<timestamp>_<slug>.py` (e.g., `20260819_add_document_summaries_table.py`) — descriptive of the change, never a generic name like `update.py`.
- Locally, migrations are applied automatically on Docker Compose startup — a contributor never runs a manual migration command just to get a working schema; see `skills/devops.md` for the Compose workflow this relies on.

## 5. Transactions

- Use the session-as-context-manager pattern (`async with session.begin(): ...`) so commit/rollback is explicit and automatic on exception — never a manually managed commit that can be skipped by an early return or an uncaught exception path.
- An exception inside a transaction block rolls the transaction back; it is never swallowed and treated as if the write succeeded.
- **Background worker jobs must be idempotent against their own retries.** A job that can be re-delivered or re-run (per the retry policy) must not create duplicate state on a second run. The concrete pattern already established in `specs/document-processing.md` §6 is the template: a reprocessing run deletes any prior `document_chunks` rows for the document before inserting new ones, so re-running the chunk-insert step never produces orphaned or duplicate chunks.

## 6. Constraints

- DB-level `CHECK`, `UNIQUE`, and `FOREIGN KEY` constraints are the **last line of defense**, not the only validation. They exist to prevent invalid state even when application code has a bug or a future code path bypasses the service layer entirely.
- The primary validation layer is Pydantic at the API boundary, per `skills/backend.md` — DB constraints back that up, they don't substitute for it. Both are required; neither is optional because the other exists.

## 7. Indexes

- Add an index deliberately, in response to a real query a new feature introduces — check the new tenant-scoped list/filter query against the indexes already defined in `specs/database.md` before shipping it, per the query-performance guidance in `specs/performance.md`. Don't add an index speculatively "just in case."
- **Leading-column discipline:** for any composite index backing a tenant-scoped query, `user_id` is the first column — matching every index choice already made in `specs/database.md` (e.g., `(user_id, created_at DESC)`, `(user_id, status)`). This keeps the tenant filter cheap and index-friendly rather than an afterthought.
- Avoid index bloat — don't index every column defensively. Each index has a write-time cost; it earns its place by serving a real, identified query pattern.

## 8. Relationships

- Choosing between `ON DELETE CASCADE` and `ON DELETE SET NULL` is about ownership, not convenience:
  - **CASCADE** for data that is *owned* and has no independent meaning once its parent is gone — e.g., `document_chunks` cascading from `documents`: a chunk with no document is meaningless, so it must go when the document does.
  - **SET NULL** for a *loosely associated reference* where the referencing row still has meaning on its own — e.g., `citations.document_chunk_id` (per `specs/database.md` §3.10): a citation still records a useful snippet/page reference even if the underlying chunk was deleted, so the citation survives with a null pointer rather than disappearing.
- When adding a new FK relationship, ask: "does the child row mean anything without the parent?" If no, cascade. If yes, set null (or restrict, if the relationship must never be silently orphaned).

## 9. Query Optimization

- Run `EXPLAIN ANALYZE` on any new non-trivial query before merging — an assumption that a query "is probably fine" is not a substitute for checking it against the budgets in `specs/performance.md`.
- Prefer set-based operations over N+1 loops; a loop issuing one query per row is a red flag in review, not a style choice.
- Paginate everything that lists tenant data — no unbounded `SELECT` over a table that grows with usage.
- Be deliberate about `SELECT *` versus explicit columns, especially for large text columns. A document list view has no reason to fetch `document_chunks.content` (or any large `TEXT`/`JSONB` payload) when it only needs id/name/status — select what the view actually renders.

## 10. Multi-Tenant Isolation — the Core Discipline

This is the discipline every other section supports. `specs/architecture.md` §6 defines the three defense-in-depth enforcement layers (authentication, repository, database); this section operationalizes the repository layer into a concrete coding checklist for anyone touching the data layer:

- [ ] Every new repository method that touches a tenant-scoped table takes `user_id` as its **first parameter**, and that `user_id` appears in the method's `WHERE` clause (or in a join that transitively enforces the same constraint, e.g., reaching `document_chunks` through `documents.user_id`).
- [ ] Every new tenant-scoped table added to the schema gets a `user_id` column and a leading index on it, matching the pattern already used throughout `specs/database.md`.
- [ ] The `user_id` used in any query comes only from the verified identity established at the authentication layer — never from a client-supplied field, query parameter, or request body.
- [ ] Any PR that touches the repository layer is reviewed against this checklist specifically, not folded into a generic code-quality pass.
- [ ] A cross-tenant-access test is added for the new/changed repository method or endpoint, per the mandatory dedicated test category in `specs/testing.md` §3.5 — this is not optional follow-up work, it ships with the feature.
