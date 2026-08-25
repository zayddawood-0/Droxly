import asyncio
import sys
from collections.abc import AsyncIterator, Iterator

import pytest
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


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limit_state() -> AsyncIterator[None]:
    """
    Found while writing the R1 remediation pass's new throttle tests
    (audit findings S5/S6): unlike db_session's Postgres SAVEPOINT rollback,
    core/rate_limit.py's Redis-backed counters have no per-test isolation
    of their own — they're real, persistent state in the same Redis
    instance across the whole test session (and across separate `pytest`
    invocations, since nothing ever expires them faster than their own
    TTL). Tests that use fresh `uuid4()` identifiers (test_rate_limit.py)
    were never affected, but new tests using fixed, human-readable emails
    for readability (test_auth_api.py's throttle/audit-log tests) silently
    accumulated AuthThrottle/resend-cooldown counts across repeated runs
    until a later run's 6th call unexpectedly saw an already-primed
    counter and 429'd. Deleting only the `rl:*` keys this app itself
    writes — not a blanket FLUSHDB — keeps this scoped to what these tests
    actually touch.
    """
    import redis.asyncio as redis_lib

    from app.core.rate_limit import redis_client

    async def _clear() -> None:
        try:
            async for key in redis_client.scan_iter(match="rl:*"):
                await redis_client.delete(key)
        except redis_lib.RedisError:
            # Same fail-open posture as the app code itself (decisions.md
            # ADR-021): tests that never touched rate limiting before this
            # fixture was added (e.g. test_security.py, test_chunking.py)
            # shouldn't newly require Redis just to run.
            pass

    await _clear()
    yield
    await _clear()


@pytest.fixture(autouse=True)
def _reset_document_processing_queue() -> Iterator[None]:
    """
    tasks/remediation-plan.md R3 — app/core/queue.py's RQ queue is real,
    unmocked Redis (matching this suite's existing rate-limit-fixture
    convention above, not a fake/in-memory queue) so tests exercise the
    actual enqueue call `DocumentService.confirm_upload`/`reprocess_document`
    make. Nothing in this test suite runs an `rq worker` process to consume
    jobs, so left-over queue/job keys would otherwise accumulate across
    runs — cleared the same targeted way (`rq:*` keys this app itself
    writes, not a blanket FLUSHDB) as the rate-limiter's `rl:*` cleanup.
    """
    from app.core.queue import redis_connection

    def _clear() -> None:
        for key in redis_connection.scan_iter(match="rq:*"):
            redis_connection.delete(key)

    _clear()
    yield
    _clear()


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


async def make_user(
    db_session: AsyncSession, *, email: str | None = None, plan: str = "free"
):
    """
    tasks/remediation-plan.md R2 — creates a User row directly (bypassing
    register/login) for tests that need an owning user but aren't
    themselves testing the auth flow, mirroring R1's own
    test_auth_api.py::test_login_oauth_only_account_rejects_password
    pattern rather than inventing a new one.
    """
    import uuid

    from app.models import User

    user = User(
        email=email or f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
        plan=plan,
    )
    db_session.add(user)
    await db_session.flush()
    return user
