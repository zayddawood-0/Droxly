# Task P03: Database Schema

## Task ID
P03-001..003

## Feature
Database — Full schema migration (backend)

## Objective
Deliver `specs/roadmap.md` Phase 3 as written: Alembic migrations for every table in `specs/database.md` beyond `users`/`refresh_tokens`, pgvector + HNSW index setup, and repository-layer scaffolding (empty CRUD, `user_id`-first convention). This is a genuine pivot from the frontend-only track (Phases 1–2 of this session series) to the backend (Python/FastAPI/SQLAlchemy/Alembic) — confirmed explicitly with the user, since Phase 3 has no frontend deliverable.

## Specification References
- `specs/database.md` (full) — the schema source of truth every model/migration below mirrors exactly
- `skills/database.md` — PostgreSQL/pgvector/SQLAlchemy/Alembic engineering discipline (transaction boundaries, HNSW hand-authoring, migration authoring conventions, the multi-tenant-isolation checklist)
- `skills/backend.md` — layered architecture (repositories are the only layer writing queries, `user_id`-first), folder structure
- `specs/decisions.md` ADR-002 (FastAPI/SQLAlchemy async/Alembic), ADR-003 (Postgres+pgvector, one database), ADR-006 (Docker), ADR-012/OQ-03 (embedding dimension = 1536), ADR-015 (repo layout — `backend/` sibling to `frontend/`)
- `specs/devops.md` §1–2, §8 (Docker Compose service shape, migration workflow)
- `specs/testing.md` §3.2 (repository/database tests — real test Postgres, never mocked) and §3.5 (mandatory cross-tenant test category, applied at the repository layer as each table's tests are written)

## Requirements
- None directly (`specs/roadmap.md` Phase 3: "Requirements fulfilled: None directly — enables Phases 4–14").

## Dependencies
- **Phase 1 (backend half) and Phase 2 (backend half) do not exist yet in this repo** — this frontend-only session series never built them. Phase 3 explicitly depends on Phase 2's `users` table existing (`roadmap.md`: "Phase 1 (Phase 2's users table must exist first)"). Confirmed with the user: build the minimal backend scaffold and the `users`/`refresh_tokens` **tables** (schema only — no auth business logic, no JWT/OAuth/password hashing, no routers/services) as infrastructure this task genuinely needs, then deliver Phase 3 itself. Full Phase 1/2 backend feature work (routers, services, auth flows) remains out of scope — a separate task when that phase is actually executed.

## Files Affected
- `backend/pyproject.toml`, `backend/alembic.ini`, `backend/.env.example` — new
- `backend/alembic/env.py`, `backend/alembic/script.py.mako` — new
- `backend/alembic/versions/0001_users_and_refresh_tokens.py` — new (prerequisite)
- `backend/alembic/versions/0002_phase3_schema.py` — new (Phase 3 proper: all remaining tables + pgvector/HNSW)
- `backend/app/core/{config,database}.py` — new
- `backend/app/main.py` — new (health-check only, matching Phase 1's own "empty health-check endpoint" expected output — no feature routers)
- `backend/app/models/*.py` — new — SQLAlchemy 2.x declarative models mirroring `database.md` exactly
- `backend/app/repositories/*.py` — new — empty CRUD scaffolding per entity, `user_id`-first signatures (no query bodies beyond the scaffolded shape — implementing real query logic belongs to the phase that first needs each repository method)
- `backend/tests/test_migrations.py` — new — migration up/down + constraint tests
- `docker-compose.yml` (repo root) — modified — adds `postgres` (pgvector/pgvector image) and `redis` services per `devops.md` §1's documented stack; `fastapi-app`/`worker` are **not** added yet (no application logic exists for them to run beyond the health check, which is exercised directly for this task's verification, not via Compose)

## Implementation Notes
- Repositories are scaffolded with method signatures only (`user_id` first parameter, typed return) — no query bodies, per `roadmap.md`'s own Phase 3 description ("repository layer scaffolded (**empty** CRUD methods)"). Real query implementations land with the phase that first calls each one.
- No FastAPI routers or services beyond the existing health check — those are Phase 2 (auth) and Phase 4+ (feature) scope.
- `document_summaries` is included per `database.md` §6's "Open Item," which resolves it as a necessary addition structurally identical to `extractions` — not a silent scope change.
- HNSW index and the `vector_cosine_ops` operator class are hand-written into the migration (Alembic's `--autogenerate` cannot generate them), per `skills/database.md` §4.

## Tests
- Migration up/down (`alembic upgrade head` / `downgrade base`) against a real Postgres+pgvector instance (`testing.md` §3.2 — never mocked)
- Constraint tests: FK cascade behavior (documents → document_chunks), `ON DELETE SET NULL` (citations → document_chunks), `UNIQUE` constraints, `CHECK` constraints (e.g., `comparisons.document_a_id <> document_b_id`)
- HNSW index existence and operator class verification

## Acceptance Criteria
- Schema matches `specs/database.md` exactly (every table, column, constraint, index).
- `alembic upgrade head` and `alembic downgrade base` both succeed cleanly on a fresh database.
- Every tenant-scoped table has a `user_id` column and a leading index on it.
- Every repository has scaffolded methods taking `user_id` as the first parameter.

## Definition of Done
- [x] Code implements the Objective and satisfies the Acceptance Criteria
- [x] Tests listed above are written and passing (12/12, against a real Postgres+pgvector via Docker Compose)
- [x] No requirement silently changed or reinterpreted
- [x] No spec file required a content change (schema was already fully specified in `database.md`)
- [ ] Linked in a PR description with phase (Phase 3) — pending actual PR creation (no git repo yet)
