import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User
from app.repositories.base import TenantScopedRepository


class UserRepository:
    """
    Not tenant-scoped by another user_id — a user IS the tenant. Scoped by
    its own id/email instead. Real auth business logic (password
    verification, OAuth linking) lands with Phase 2 (Authentication); this
    is schema-level CRUD scaffolding only (specs/roadmap.md Phase 3).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, **fields) -> User:
        user = User(**fields)
        self.session.add(user)
        await self.session.flush()
        return user


class RefreshTokenRepository(TenantScopedRepository[RefreshToken]):
    model = RefreshToken
