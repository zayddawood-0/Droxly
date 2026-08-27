import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User
from app.repositories.base import TenantScopedRepository


class UserRepository:
    """
    Not tenant-scoped by another user_id — a user IS the tenant. Scoped by
    its own id/email instead. Auth business logic (password verification,
    OAuth linking, session issuance) lives in app/services/auth_service.py
    (tasks/remediation-plan.md R1) — this stays query-only, per
    skills/backend.md §4's "repositories are the only layer allowed to
    write SQLAlchemy queries."
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_oauth_identity(
        self, provider: str, provider_id: str
    ) -> User | None:
        """FR-AUTH-003 — match on provider + provider account ID for a
        returning OAuth user, distinct from the email-based lookup used to
        decide "link to existing" vs. "create new" on first sign-in."""
        result = await self.session.execute(
            select(User).where(
                User.oauth_provider == provider, User.oauth_provider_id == provider_id
            )
        )
        return result.scalar_one_or_none()

    async def create(self, **fields) -> User:
        user = User(**fields)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, id: uuid.UUID, **fields) -> User | None:
        user = await self.get_by_id(id)
        if user is None:
            return None
        for key, value in fields.items():
            setattr(user, key, value)
        await self.session.flush()
        return user

    async def list_paginated(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        plan: str | None = None,
    ) -> tuple[Sequence[User], int]:
        """
        api.md §12 `GET /admin/users` (`FR-ADMIN-001`) — the one legitimate
        place in the codebase a query over `users` is deliberately NOT
        scoped to a single caller: `require_admin` (core/dependencies.py)
        is the authorization boundary here, not a `user_id` filter. Every
        route calling this goes through that dependency first
        (security.md §3.1's role-check half of authorization) — this
        method itself does not and must not re-check the caller's role.
        """
        filters = []
        if status is not None:
            filters.append(User.status == status)
        if plan is not None:
            filters.append(User.plan == plan)

        stmt = select(User).where(*filters).order_by(User.created_at.desc())
        count_stmt = select(func.count()).select_from(User).where(*filters)

        items = (
            (await self.session.execute(stmt.limit(limit).offset(offset)))
            .scalars()
            .all()
        )
        total = (await self.session.execute(count_stmt)).scalar_one()
        return items, total


class RefreshTokenRepository(TenantScopedRepository[RefreshToken]):
    """
    Extends the generic tenant-scoped CRUD with the auth-specific query
    shapes login/refresh/logout/session-management need. `revoke` (not the
    base class's `delete`) is deliberate: security.md §2.2 requires a
    revoked token row to remain for audit purposes, never hard-deleted.
    """

    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """
        Not user_id-scoped — at /auth/refresh time the caller is
        identified only by the opaque cookie value, not yet a known
        user_id (that's the point of this lookup: to discover it). Matches
        UserRepository.get_by_email's same "identity lookup precedes
        tenant scoping" shape, not a violation of the tenant-scoping rule
        (which governs *resource* access, not *identity resolution*).
        """
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, user_id: uuid.UUID, id: uuid.UUID) -> bool:
        token = await self.get(user_id, id)
        if token is None or token.revoked_at is not None:
            return False
        token.revoked_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """FR-AUTH-007 (password reset) / FR-ADMIN-003 (suspend) — every
        active token for the account, not just one."""
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        now = datetime.now(UTC)
        for token in result.scalars().all():
            token.revoked_at = now
        await self.session.flush()

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[RefreshToken]:
        """FR-AUTH-008 — Settings → Security's session list: non-revoked,
        non-expired only."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list(result.scalars().all())
