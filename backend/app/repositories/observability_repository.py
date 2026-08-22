import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiRequest, AuditLog
from app.repositories.base import TenantScopedRepository


class AiRequestRepository(TenantScopedRepository[AiRequest]):
    model = AiRequest


class AuditLogRepository:
    """
    specs/database.md §3.14 — append-only; `user_id` (actor) is nullable for
    system-initiated events, which doesn't fit TenantScopedRepository's
    non-null-owner assumption. No update/delete method exists here on
    purpose (specs/security.md §12 — the audit trail is never mutated).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(self, **fields) -> AuditLog:
        entry = AuditLog(**fields)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_actor(
        self, user_id: uuid.UUID, *, limit: int = 20, offset: int = 0
    ) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
