from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

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
    its own session. Not wired into any router yet (none exist this phase);
    the dependency is scaffolded here so Phase 2/4+ routers use it directly
    rather than each inventing session handling.
    """
    async with async_session_factory() as session:
        yield session
