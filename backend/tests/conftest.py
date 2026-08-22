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
