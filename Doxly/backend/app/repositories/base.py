import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base


class TenantScopedRepository[ModelT: Base]:
    """
    Generic empty-CRUD scaffolding (specs/roadmap.md Phase 3 expected
    output) for every tenant-scoped table. Every method takes `user_id` as
    its first parameter and filters on it directly — this is the primary
    enforcement point for NFR-SEC-001 (specs/architecture.md §6,
    skills/database.md §10's checklist). Domain-specific queries (joins,
    status filters, the pgvector similarity search) are added by the phase
    that first needs them, as a method on the relevant subclass below — this
    base class intentionally goes no further than generic CRUD.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID, id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id, self.model.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, user_id: uuid.UUID, *, limit: int = 20, offset: int = 0
    ) -> Sequence[ModelT]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.user_id == user_id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_many(
        self, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> Sequence[ModelT]:
        """Batch fetch (e.g. Phase 7's context-assembly provenance lookup) — still owner-scoped, never trusts the id list alone."""
        if not ids:
            return []
        result = await self.session.execute(
            select(self.model).where(
                self.model.id.in_(ids), self.model.user_id == user_id
            )
        )
        return result.scalars().all()

    async def create(self, user_id: uuid.UUID, **fields) -> ModelT:
        instance = self.model(user_id=user_id, **fields)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, user_id: uuid.UUID, id: uuid.UUID) -> bool:
        instance = await self.get(user_id, id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True
