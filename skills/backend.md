# Doxly — Backend Engineering Standards

> How Claude must write FastAPI backend code for Doxly. This file defines binding conventions for the FastAPI + Pydantic v2 + SQLAlchemy 2.x (async) + Alembic stack (`specs/decisions.md` ADR-002). It implements the layering mandated by `specs/architecture.md` §2.2 and `specs/requirements.md` NFR-MAINT-001 ("API routes never touch the DB directly") and the multi-tenancy enforcement point defined in `specs/architecture.md` §6 (every repository method takes `user_id` as a mandatory first argument). It does not restate the API contract (`specs/api.md`), the schema (`specs/database.md`), the security control set (`specs/security.md`), or the observability spec (`specs/observability.md`) — it tells you how to write code that satisfies them.

## 1. Layered architecture discipline — the core rule

```
Router  →  Service  →  Repository  →  Database
 (HTTP)     (business)   (queries)
                 ↘
                  AI layer / Document-Processing layer
```

Per `specs/architecture.md` §2.2, every request flows API (routers) → Service → Repository → DB. Services are also the only layer permitted to call into the AI layer (LangGraph graphs, `LLMProvider`/`EmbeddingProvider`) or the Document-Processing layer (`DocumentParser`) — routers never invoke either directly.

- **Routers** own request/response shape and the auth dependency only: parse and validate the incoming request (via Pydantic), call exactly one service method, shape the HTTP response. No business logic, no direct DB session usage, no query construction, no `if` statements implementing a business rule.
- **Services** hold business logic: orchestration across one or more repositories, transaction boundaries (a service method that touches multiple tables commits once, atomically), business-rule enforcement that isn't pure shape validation (e.g., storage quota checks before accepting an upload per `FR-DOC-001`), and invocation of the AI layer / Document-Processing layer.
- **Repositories** are the *only* layer that constructs SQLAlchemy queries, and the *only* layer where tenant filtering is applied.

**This is enforced by code review discipline, not convention alone.** Every PR touching `app/api/` or `app/services/` is reviewed against this layering explicitly; a router or service that contains a `select(`, `.where(`, or `.filter(` call is a blocking review comment, not a style nit. Where feasible, back this with tooling rather than relying on reviewers to catch it every time — an import-linter/architecture-test rule (e.g., forbidding `app/api/` and `app/services/` from importing `sqlalchemy` query constructs, or a CI grep check) is the recommended direction so the rule is machine-checkable, not just remembered. Until that tooling exists, the **auditability rule** stands as the manual fallback: a reviewer must be able to grep the codebase for `select(`, `.where(`, `.filter(` and confirm every match lives under `app/repositories/`. This single-choke-point design is what makes `NFR-SEC-001` (cross-tenant isolation) verifiable by inspection, not just by hoping every route remembered to filter.

## 2. FastAPI routers

- **Router-per-domain**: one `APIRouter` per resource domain, one module per domain, mirroring `specs/api.md`'s endpoint groups exactly: `auth.py`, `users.py`, `documents.py`, `chat.py`, `extractions.py`, `comparisons.py`, `search.py`, `analytics.py`, `settings.py`, `admin.py`, `export.py`. Each router sets an explicit `prefix` and `tags` so the generated OpenAPI schema stays grouped and matches `specs/api.md` 1:1.
- **Current-user dependency**: a single `get_current_user` FastAPI dependency (JWT verification against the httpOnly access-token cookie, per `specs/decisions.md` ADR-010) is the only path by which a router learns who is calling. It is never re-implemented per route, and routers never accept a `user_id` from the request body/query string for "which user am I acting as" purposes.
- Routers declare their request/response Pydantic schemas explicitly on the route decorator (`response_model=...`) so FastAPI enforces the response contract, not just documents it.
- A router function body is typically three lines: extract dependencies (current user, DB session, request schema), call one service method, return its result (or let `response_model` shape it). Anything longer than that is a sign business logic has leaked into the router.

## 3. Services

Services are where Doxly's actual business rules live — the layer that answers "is this operation allowed / correct / complete" beyond pure request shape. Concretely:

- **Quota and plan-tier checks**: e.g., a document upload service method checks `users.storage_used_bytes` against the plan limit (`decisions.md` OQ-06/07) *before* calling the repository to insert — the router never sees this logic.
- **Orchestrating AI workflows**: a service method (e.g., `ChatService.ask`) is what invokes a LangGraph graph (`specs/langgraph.md`) with the assembled state (`query`, `conversation_id`, `user_id`), not the router and not the repository.
- **Coordinating multi-step/multi-repository operations**: e.g., `ExtractionService.run_extraction` validates the source document's state via the document repository, invokes the extraction workflow, then persists the result via the extraction repository — all within one service method that owns the transaction boundary.
- **Enqueuing background work** (§12) instead of doing it inline, when the operation crosses the inline/queued line defined in `specs/decisions.md` ADR-008.

Services are constructor-injected with the repositories (and AI/document-processing clients) they depend on, never reaching for a global singleton — this is what makes a service **unit-testable in isolation with its repositories mocked/faked**, without spinning up a database or the full FastAPI dependency graph. This is the primary unit-test target described in `specs/testing.md`; a new business rule is not considered done until it has a service-layer test that exercises it with a mock repository, independent of any HTTP or DB integration test.

## 4. Repositories

**Repositories are the only layer allowed to write SQLAlchemy queries — full stop.** No `select()`, `.where()`, `.filter()`, or raw `text()` query appears anywhere outside `app/repositories/`.

- Every tenant-scoped repository method takes `user_id` as its **first parameter**, and every query it builds includes (directly, or via a join that transitively enforces it, e.g. `document_chunks` joined through `documents.user_id`) `WHERE user_id = :user_id`.
- **This is prominently the primary enforcement point for `NFR-SEC-001`** (`specs/architecture.md` §6 names the repository layer as *the* primary enforcement point among the three defense-in-depth layers — authentication, repository, database). If a query path exists that reads or writes tenant data without a `user_id` filter, that is a cross-tenant data leak, not a style issue, regardless of how many other layers "should have" caught it.
- Repository methods return typed results — SQLAlchemy models or explicit DTOs (e.g., `DocumentDTO`) — **never raw rows, raw dicts, or a bare `Result`/`CursorResult` object**. The service layer should never need to know whether a repository used the ORM or Core to fetch data.
- Soft-deletion (`deleted_at IS NULL`) and other standing row-visibility rules from `specs/database.md` §1 are applied inside the repository by default, not left to every call site to remember.

## 5. Pydantic schemas

- Schemas are the single validation boundary for all request and response data (this is the code-level implementation of the input-validation posture described in `specs/security.md`) — every field crossing the API boundary in either direction is declared, typed, and constrained in a Pydantic model. Nothing is deserialized from a raw request body or serialized to a raw dict by hand.
- Per resource, define separate schema variants **only where the shape genuinely differs**: typically `*Create` (fields a client may set on creation), `*Update` (a smaller, often-partial set of mutable fields), and `*Response`/`*Read` (the shape returned to a client, which may include server-computed fields like `id`, `created_at`, `status` that are never client-writable). An `*InDB` variant is added only when the persisted shape genuinely diverges from what's ever returned to a client (e.g., a schema carrying `password_hash` for internal use, which must never be reachable from a `*Response` model). **Do not manufacture a fourth or fifth schema variant when two of them would be identical** — a resource with no server-computed fields and no internal-only fields may legitimately need only `*Create` and `*Response`; collapsing schemas that don't differ is correct, not lazy.
- **Never** return a SQLAlchemy model directly from a route (declare `response_model=...`, and construct/validate the response schema from the ORM object), and never accept a SQLAlchemy model as a request body type. Decoupling the wire contract from the storage shape means either can change independently.
- The `*Response` schema is the enforcement point for "never over-expose fields": because the schema declares exactly which fields serialize, any extra attribute present on the underlying ORM object (or accidentally joined in) is dropped automatically. This is preferred over manually redacting fields per endpoint, which is easy to forget.
- **Pydantic v2 patterns**: use `model_config = ConfigDict(from_attributes=True)` on response schemas that are built from ORM objects (replaces v1's `orm_mode`); use `@field_validator` (not the deprecated v1 `@validator`) for field-level shape/format rules (password strength regex, MIME-type allowlist, file-size ceiling); use `Field(...)` constraints (`min_length`/`max_length`, `pattern`, `gt`/`le`, enum membership) as the default mechanism before reaching for a custom validator function.

## 6. SQLAlchemy models

- Async ORM throughout: `AsyncSession`, `async def` repository methods, `await session.execute(...)`.
- Models live in `app/models/`, structurally distinct from `app/schemas/` (Pydantic). A model's columns, foreign keys, cascade rules, and indexes must mirror `specs/database.md` exactly — that spec is the source of truth for table structure and is not redefined here; if a model needs to diverge, `specs/database.md` is updated first.
- **Relationship loading is always explicit.** Every relationship access on a route/service code path that will actually be traversed must be eagerly loaded via `selectinload()` (default choice for one-to-many/collections, e.g. `documents.chunks`, `conversations.messages`) or `joinedload()` (for to-one relationships fetched alongside the parent in a single query, e.g. `citation.document_chunk`), specified explicitly in the repository query — never left to default lazy-loading.
- **Implicit lazy-loading is not just a performance smell here, it is a bug.** Accessing an unloaded relationship attribute on an object bound to an `AsyncSession` outside of an explicit `await` (SQLAlchemy's default lazy-load emits a synchronous, blocking query) raises `MissingGreenlet`/`InvalidRequestError` at runtime in an async context. Every relationship a caller needs must be loaded up front by the repository method that fetches the parent object, matching exactly what the caller is known to need — not "load everything just in case," which reintroduces N+1s and over-fetching in the other direction.
- No raw SQL string interpolation, ever. All queries use SQLAlchemy Core/ORM constructs with bound parameters (`NFR-SEC-005`). A raw `text()` query is permitted only for a documented performance reason and must still use bound parameters, never f-string/`.format()` interpolation of values.

## 7. Dependency injection

- `Depends()` is used for: current-user extraction (`get_current_user`, §8), DB session provisioning, and repository/service instantiation.
- **DB session lifecycle**: one `AsyncSession` per request, provided by a `get_db_session` dependency that yields the session and guarantees it is closed (and any uncommitted transaction rolled back) when the request completes, including on an unhandled exception — a route/service never opens its own session or holds one across requests.
- **Wiring**: services and repositories are constructor-injected — a service's `__init__` takes the repositories it needs, a repository's `__init__` takes the `AsyncSession` — assembled via a chain of `Depends()` functions (e.g., `get_document_service` depends on `get_document_repository`, which depends on `get_db_session`). This lets any service or repository be instantiated directly with a test session/fake in a unit test, without spinning up the full FastAPI dependency graph.
- **Do not introduce a heavier DI framework** (e.g., `dependency-injector`, a custom IoC container) — FastAPI's native `Depends()` chaining is sufficient for this codebase's dependency graph and keeps wiring visible at each call site instead of behind container configuration. Reach for something heavier only if a concrete, demonstrated need emerges (matches the anti-overengineering principle in the root `CLAUDE.md`), not preemptively.

## 8. Authentication & authorization in code

- A route declares its auth requirement through its dependency list, not an in-body check: a route requiring any authenticated user depends on `get_current_user`; a route requiring the admin role depends on `require_admin`, which composes `get_current_user` and additionally checks `role == 'admin'`. There is never an inline `if user.role != "admin": raise ...` duplicated per admin route — that check exists in exactly one place.
- **The code-level flow**: `get_current_user` verifies the JWT access token from the httpOnly cookie (mechanism defined in `specs/decisions.md` ADR-010; token/rotation/revocation policy defined in `specs/security.md` — not redefined here) and extracts `user_id` from its verified claims — never from a client-supplied body/query field. That `user_id` is then the value threaded, unmodified, as the first argument through every service call and on into every repository call for the duration of the request. `user_id` is never re-derived, re-trusted from a nested object, or passed as an optional/nullable value "just in case" on a tenant-scoped path.
- HTTP status convention (must match `specs/api.md` exactly): **401** for missing/expired/invalid token, **403** for a valid token lacking the required role (e.g., non-admin calling an admin route), **404** — not 403 — when a resource exists but is owned by a different user, to avoid confirming the resource's existence to an unauthorized caller.

## 9. Validation

- Pydantic schemas at the API boundary (§5) are the **authoritative** validator for shape, type, format, and simple constraints. Frontend validation (`skills/frontend.md`) is a UX convenience only — fast feedback, prevents obviously-invalid submissions — and is never trusted as the security or correctness boundary; every backend endpoint must behave correctly even if the frontend's validation were entirely bypassed.
- **Domain-level validation lives in the service layer, not scattered in routers.** Anything that requires knowledge of business state — not just the shape of the incoming payload — is a service-layer check. Example: "a document must have `status = 'ready'` before extraction can run" is not a Pydantic field constraint (the extraction request payload has no `status` field to validate) and is not a router `if` check; it is `ExtractionService.run_extraction` fetching the document via the repository, checking its `status`, and raising a typed domain exception (§10) if the precondition fails.
- Rule of thumb: if the check can be expressed purely from the shape of the request body (format, range, enum membership), it belongs in a Pydantic schema. If it requires reading current database/business state to evaluate, it belongs in a service method.

## 10. Error handling

- All domain errors derive from a single base exception, `DoxlyError`, with typed subclasses for each error category: `NotFoundError`, `ValidationError` (domain-level, distinct from Pydantic's own request-validation errors), `QuotaExceededError`, `UnauthorizedError`, `ConflictError`, etc. Services and repositories raise these typed exceptions — they never construct or return a raw `HTTPException`/JSON error response inline. Keeping error construction out of routers and services means the error shape is defined in exactly one place.
- A single global FastAPI exception handler catches `DoxlyError` (and its subclasses) and maps each to the standard error envelope from `specs/api.md`: `{"error": {"code": string, "message": string, "request_id": string}}`, with `code` a stable machine-readable string (e.g. `document_not_found`, `quota_exceeded`) and `message` a sanitized, user-safe string. The handler also catches unexpected/unhandled exceptions as a fallback, logging the full detail (§11) but returning a generic sanitized envelope — never a stack trace, SQL fragment, or internal file path in the response body (`NFR-SEC-009`).
- Because every error passes through the one global handler, adding a new error type is: define the `DoxlyError` subclass, map it to a status code and `code` string in the handler's mapping table, done — no route needs to know about it individually.

## 11. Logging

- Structured (JSON) logs carry a request ID that propagates across Next.js → FastAPI → Worker, obtained from a request-scoped context rather than threaded manually through every function signature (`specs/observability.md`).
- **The practical rule**: log IDs and operation metadata — `user_id`, `document_id`, `conversation_id`, operation name, status, latency — never the content those IDs point to. A log statement must never serialize a full Pydantic request/response model when that model might carry document text, chat content, or extracted field values; log the model's identifying fields explicitly instead of `log.info(payload)`/`log.info(payload.dict())`. This is the backend-code-level enforcement of the Never-Log List defined in `specs/observability.md` §1 (authoritative list, not redefined here).
- Business-significant events (document uploaded, processing completed, extraction run, account deleted) are logged at the **service layer**, where the business meaning is known — not scattered as ad hoc `print`/log calls in routers or repositories.

## 12. Background processing

- **How a service enqueues work**: when a service method determines an operation belongs on the queued side of the inline-vs-queued line (below), it calls the Redis/RQ enqueue helper (`specs/decisions.md` ADR-008) with the job function reference and its arguments (typically `user_id` plus the relevant resource ID, e.g. `document_id`) — never a serialized ORM object or an open DB session — and returns immediately, having already written the resource's initial state (e.g. `documents.status = 'queued'`) via the repository so the client has something to poll against.
- **The worker job entrypoint reuses the same service layer as the API — never a parallel code path.** A job function in `app/workers/` is a thin wrapper: it obtains its own DB session and repository/service instances (via the same constructor-injection pattern as the API, just outside the `Depends()` chain since there's no HTTP request), then calls the identical service method the API would call for an inline equivalent (e.g. the worker's `process_document` job calls `DocumentProcessingService.process`, the same method a hypothetical inline path would call). Business logic — quota checks, state transitions, orchestration — is never duplicated between the interactive and background paths; the only thing that differs is who invokes the service (a router vs. a job entrypoint) and whether the caller waits for the result.
- Decide at design time which side of the line a new endpoint is on:

| Handle inline in the API request | Enqueue to the worker |
|---|---|
| Standard CRUD (list/get/update/delete) | Document processing pipeline (extract/chunk/embed) |
| Streaming Document Q&A chat (`FR-AI-001`) — the one AI workflow that runs inline because it streams token-by-token per `specs/architecture.md` §5 | Summarization, Extraction, Comparison workflows |
| Auth, settings, search queries | Full-account data export generation |

Anything that can plausibly take more than ~2 seconds, or that must survive longer than a single HTTP request/response cycle, is a queued job — never a slow inline endpoint "for now."

## 13. Async programming

- `async`/`await` is used consistently, end-to-end, for all I/O-bound work: async SQLAlchemy sessions for every DB query, an async HTTP client (e.g. `httpx.AsyncClient`) for every call to an LLM or embedding provider, async calls to object storage.
- Blocking calls must never run directly inside an `async def` route handler or service method — a synchronous call stalls the event loop for every concurrent request on that worker process, not just the caller. **Known risk**: the document-parsing libraries selected in `specs/decisions.md` ADR-014 (`pypdf`/`pdfplumber`, `python-docx`, `pandas`/`csv`) are synchronous, not async-native. Because parsing runs in the background worker (§12), this matters less there (a worker process can dedicate a thread/process to one job), but any synchronous parsing or other CPU-bound/blocking library call that must run inside the API process (rare, and should be avoided by design) must be offloaded via `run_in_executor` (or an async-native alternative library, if one exists), never called directly.
- **Common pitfall — mixing sync and async DB sessions**: a codebase with both a sync SQLAlchemy `Session` (e.g., pulled in by a script, a notebook, or a copy-pasted example) and the async `AsyncSession` used everywhere else will fail confusingly (blocking calls inside async code, or session-binding errors) if the two are ever mixed in the same code path. There is exactly one session type in this codebase: `AsyncSession`, used by every repository, every service, and every worker job — a sync `Session`/`sessionmaker` has no legitimate use here and its presence in a diff is a review flag.

## 14. API versioning

- All routes are mounted under `/api/v1` (`specs/decisions.md` ADR-005). A future `/api/v2` would be introduced as an additive, parallel router mount — not an in-place breaking change to `/api/v1` — allowing existing clients to keep working during a migration window.
- **Introduce a new version only for a genuinely breaking change** (removing/renaming a field or endpoint, changing a field's type or meaning, changing required-vs-optional in an incompatible direction). Additive, backward-compatible changes — a new optional request field, a new response field, a new endpoint, a new enum value a client can safely ignore — ship within the existing `/api/v1` version; they do not justify a new version on their own.
- This is a stated policy, not yet an active concern, since no `v1` has shipped and no `v2` exists yet.

## 15. Recommended backend folder structure

```
app/
├── main.py                      # FastAPI app instantiation, router mounting, middleware
├── core/
│   ├── config.py                 # env-var driven settings
│   ├── security.py                # JWT issuance/verification, password hashing
│   └── dependencies.py            # get_current_user, require_admin, get_db_session
├── api/
│   └── v1/
│       └── routers/
│           ├── auth.py
│           ├── users.py
│           ├── documents.py
│           ├── chat.py
│           ├── extractions.py
│           ├── comparisons.py
│           ├── search.py
│           ├── analytics.py
│           ├── settings.py
│           ├── admin.py
│           └── export.py
├── schemas/                      # Pydantic Create/Update/Response(/InDB) models, one module per domain
├── models/                       # SQLAlchemy ORM models, mirroring specs/database.md
├── repositories/                 # The only layer building queries; user_id-first methods
├── services/                     # Business logic/orchestration/transactions; calls AI + doc-processing layers
├── errors.py                     # DoxlyError base + typed subclasses, global exception handler
├── ai/                           # LLMProvider/EmbeddingProvider abstractions, LangGraph graphs
├── document_processing/          # DocumentParser implementations per MIME type, chunking
├── workers/                      # RQ job entrypoints — thin wrappers calling the same services/ layer
└── tests/
    ├── unit/                      # Service tests with repositories mocked (specs/testing.md)
    ├── api/
    └── integration/
```

The `workers/` entrypoints deliberately call into the same `services/` layer used by the API routers — business logic is never duplicated between the request path and the job path (§12).
