import uuid
from collections.abc import Sequence

from app.core.queue import (
    get_comparison_queue,
    get_document_processing_queue,
    get_extraction_queue,
    get_summary_queue,
)
from app.errors import NotFoundError, NotSuspendedError
from app.models import User
from app.repositories.admin_repository import AdminRepository
from app.repositories.observability_repository import AuditLogRepository
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.admin import SystemHealthResponse


class AdminService:
    """
    api.md §12 (`/admin`), `FR-ADMIN-001..003` — every method here is
    reached only through routes declaring `require_admin`
    (`core/dependencies.py`); this service does not re-check the caller's
    role itself (`security.md` §3.1: the role check lives at the route
    dependency layer, not duplicated in every service method).
    `NFR-PRIV-004`/`FR-ADMIN-001`: nothing here ever touches document
    content, chat content, or extracted field values — only account/
    operational metadata, by construction (the repositories this composes
    never select those columns).
    """

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        audit_log_repository: AuditLogRepository,
        admin_repository: AdminRepository,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_token_repository
        self._audit_logs = audit_log_repository
        self._admin = admin_repository

    async def list_users(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        plan: str | None = None,
    ) -> tuple[Sequence[User], int]:
        return await self._users.list_paginated(
            limit=limit, offset=offset, status=status, plan=plan
        )

    async def system_health(self) -> SystemHealthResponse:
        """
        `FR-ADMIN-002` — `queue_depth` sums all four RQ queues (R3/R5/R6/R7
        each own one); a genuine cross-domain aggregate, not something any
        single existing repository could answer alone.
        """
        queue_depth = sum(
            q.count
            for q in (
                get_document_processing_queue(),
                get_extraction_queue(),
                get_comparison_queue(),
                get_summary_queue(),
            )
        )
        return SystemHealthResponse(
            queue_depth=queue_depth,
            processing_failure_rate_24h=await self._admin.processing_failure_rate_24h(),
            ai_requests_24h=await self._admin.ai_requests_24h(),
            ai_error_rate_24h=await self._admin.ai_error_rate_24h(),
        )

    async def suspend_user(
        self, admin_user_id: uuid.UUID, target_user_id: uuid.UUID, reason: str
    ) -> User:
        """
        `FR-ADMIN-003` — sets `users.status='suspended'`, revokes every
        active refresh token immediately (blocks re-authentication;
        `core/dependencies.py`'s `get_current_user` status check blocks the
        current access token too — the two together are what makes
        "immediately revoking all sessions" actually immediate, not just
        "blocked at next login"), and writes the required `audit_logs` row.
        Never touches the target user's documents/conversations/content —
        `security.md` §3.1's "admin is never a tenant-ownership bypass."
        """
        target = await self._users.get_by_id(target_user_id)
        if target is None:
            raise NotFoundError()

        updated = await self._users.update(target_user_id, status="suspended")
        assert updated is not None  # existence just verified above
        await self._refresh_tokens.revoke_all_for_user(target_user_id)
        await self._audit_logs.log(
            user_id=admin_user_id,
            target_user_id=target_user_id,
            action="admin_suspend_user",
            metadata_json={"reason": reason},
        )
        return updated

    async def unsuspend_user(
        self, admin_user_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> User:
        target = await self._users.get_by_id(target_user_id)
        if target is None:
            raise NotFoundError()
        if target.status != "suspended":
            raise NotSuspendedError()

        updated = await self._users.update(target_user_id, status="active")
        assert updated is not None
        await self._audit_logs.log(
            user_id=admin_user_id,
            target_user_id=target_user_id,
            action="admin_unsuspend_user",
        )
        return updated
