from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.errors import DoxlyError

# Async engine only, per skills/database.md §1 — never a sync driver in
# request-serving code paths (decisions.md ADR-002).
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


class Base(DeclarativeBase):
    """Shared declarative base — every model in app/models/ inherits this."""


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    One AsyncSession per request, closed on completion including on an
    unhandled exception (skills/backend.md §7) — a route/service never opens
    its own session.

    Commits on clean exit, rolls back on exception. **Fixed during R1's
    compliance-remediation pass** (found while writing a persistence test
    for audit finding S2, outside this codebase's test suite): this
    function was scaffolded in Phase 3 with a docstring noting "not wired
    into any router yet," and no router existed to need transactional
    commit semantics until R1 (tasks/remediation-plan.md) built the first
    ones. Without an explicit commit here, `session.flush()` inside a
    service method (e.g. `UserRepository.create`) makes a row visible
    *within that same request's transaction* — enough to return a real ID
    in the response — but the transaction was never committed, so it
    silently rolled back when the session closed at the end of the
    request. Confirmed directly: a real (non-test-override) register →
    login round trip failed with `invalid_credentials`, because the
    registered row never actually persisted. Every one of this codebase's
    existing tests routes through `tests/conftest.py`'s `client` fixture,
    which overrides this dependency entirely with a single shared,
    intentionally-never-committed test session (by design, for per-test
    rollback isolation) — so this bug was invisible to the test suite by
    construction, regardless of how much coverage existed elsewhere.

    **A second bug found and fixed in the same pass**: the first version of
    this fix rolled back on *any* exception, including a `DoxlyError` — but
    a `DoxlyError` is an expected, well-formed business outcome
    (skills/backend.md §10), not a crash, and code that deliberately writes
    something before raising one (R1's own S7 fix: `AuthService.login`
    writes an `audit_logs` row, *then* raises `InvalidCredentialsError`)
    needs that write to survive. A blanket rollback silently discarded
    exactly the audit-log row S7 added — confirmed live: a real server run
    showed zero `audit_logs` rows for an unknown-email login attempt, even
    though the equivalent test passed (the test's session-override has no
    commit/rollback logic at all, so it could not have caught this). Only a
    genuinely *unexpected* exception (anything that isn't a `DoxlyError`)
    now rolls back — a `DoxlyError` commits whatever was flushed, then
    still re-raises so the global exception handler returns the correct
    HTTP response.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except DoxlyError:
            await session.commit()
            raise
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
