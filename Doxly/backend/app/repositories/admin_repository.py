from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiRequest, Document

# api.md §12's system-health metrics are all rolling 24h windows.
HEALTH_WINDOW = timedelta(hours=24)
_AI_ERROR_STATUSES = ("error", "timeout")


class AdminRepository:
    """
    api.md §12 (`GET /admin/system/health`), `FR-ADMIN-002` — aggregate,
    system-wide operational metrics across every user's `documents`/
    `ai_requests` rows. Deliberately **not** a `TenantScopedRepository`
    subclass and deliberately **not** added to `DocumentRepository`/
    `AiRequestRepository`: both of those are explicitly user_id-scoped by
    contract (`skills/database.md` §10's checklist — "every method takes
    user_id as its first parameter"), and this is the one place that
    contract must NOT apply, since an admin's own dashboard is meant to see
    across the whole user base. Keeping that as a separate, distinctly-named
    repository — rather than an unscoped method living inside a repository
    whose entire contract is "always scoped" — is what keeps the tenant-
    isolation invariant checkable by inspection everywhere else. Every
    caller reaches this repository only through `require_admin`
    (`core/dependencies.py`) — the same authorization-boundary note as
    `UserRepository.list_paginated`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def processing_failure_rate_24h(self) -> float:
        since = datetime.now(UTC) - HEALTH_WINDOW
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(Document)
                .where(Document.created_at >= since)
            )
        ).scalar_one()
        if total == 0:
            return 0.0
        failed = (
            await self.session.execute(
                select(func.count())
                .select_from(Document)
                .where(Document.created_at >= since, Document.status == "failed")
            )
        ).scalar_one()
        return failed / total

    async def ai_requests_24h(self) -> int:
        since = datetime.now(UTC) - HEALTH_WINDOW
        return (
            await self.session.execute(
                select(func.count())
                .select_from(AiRequest)
                .where(AiRequest.created_at >= since)
            )
        ).scalar_one()

    async def ai_error_rate_24h(self) -> float:
        since = datetime.now(UTC) - HEALTH_WINDOW
        total = (
            await self.session.execute(
                select(func.count())
                .select_from(AiRequest)
                .where(AiRequest.created_at >= since)
            )
        ).scalar_one()
        if total == 0:
            return 0.0
        errors = (
            await self.session.execute(
                select(func.count())
                .select_from(AiRequest)
                .where(
                    AiRequest.created_at >= since,
                    AiRequest.status.in_(_AI_ERROR_STATUSES),
                )
            )
        ).scalar_one()
        return errors / total
