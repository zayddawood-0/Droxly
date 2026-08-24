import asyncio
import sys
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import engine

# asyncpg's connection-cancellation path on Windows isn't fully compatible
# with ProactorEventLoop (surfaces as "Event loop is closed" during
# connection teardown after an IntegrityError-driven rollback) — a documented
# asyncpg/Windows interaction, not specific to this schema. SelectorEventLoop
# is the standard workaround; only applied for the test run, on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

"""
Real test Postgres, never mocked (specs/testing.md §3.2 — query correctness,
especially constraints, is exactly what a mock cannot catch). Each test runs
inside a transaction + SAVEPOINT that rolls back on teardown, so tests are
isolated without hand-written cleanup (skills/testing.md's stated pattern).
Requires migrations already applied (`alembic upgrade head`) against
DATABASE_URL before running this suite.
"""


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with session_factory() as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """
    tasks/remediation-plan.md R1 — httpx.AsyncClient against the real
    FastAPI app (testing.md §3.3), routed through the same rolled-back
    transaction db_session uses so API-level tests get the same
    per-test isolation as repository tests. CSRF and rate-limiting are
    overridden to no-ops here — they're cross-cutting concerns tested in
    their own dedicated suites (test_csrf.py, test_rate_limit.py) against
    the real, unmocked dependency; every other test exercises business
    logic, not transport-layer security middleware.
    """
    from httpx import ASGITransport, AsyncClient

    from app.core.csrf import verify_csrf
    from app.core.dependencies import get_db_session
    from app.core.rate_limit import rate_limit_ai, rate_limit_general
    from app.main import app

    async def _override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_db_session
    app.dependency_overrides[verify_csrf] = lambda: None
    app.dependency_overrides[rate_limit_general] = lambda: None
    app.dependency_overrides[rate_limit_ai] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def auth_cookie_headers(user_id, role: str = "user") -> dict[str, str]:
    """Mints a real, valid access-token cookie header for a given user
    without going through the login endpoint — used by API tests that need
    an authenticated caller but aren't themselves testing the login flow."""
    from app.core.security import create_access_token

    token = create_access_token(user_id, role)
    return {"Cookie": f"access_token={token}"}
