"""api.md §12 (/admin) — tasks/remediation-plan.md R10. Every route
declares require_admin (R1 §4.3, the first and only consumer); mutating
routes additionally apply R1's CSRF dependency."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csrf import verify_csrf
from app.core.dependencies import get_db_session, require_admin
from app.core.rate_limit import rate_limit_general
from app.core.security import AccessTokenClaims
from app.repositories.admin_repository import AdminRepository
from app.repositories.observability_repository import AuditLogRepository
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.admin import (
    AdminUserListItem,
    AdminUserListResponse,
    SuspendUserRequest,
    SuspendUserResponse,
    SystemHealthResponse,
    UnsuspendUserResponse,
)
from app.services.admin_service import AdminService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(rate_limit_general), Depends(require_admin)],
)


def get_admin_service(db: AsyncSession = Depends(get_db_session)) -> AdminService:
    return AdminService(
        UserRepository(db),
        RefreshTokenRepository(db),
        AuditLogRepository(db),
        AdminRepository(db),
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    plan: str | None = Query(default=None),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserListResponse:
    users, total = await service.list_users(
        limit=limit, offset=offset, status=status, plan=plan
    )
    return AdminUserListResponse(
        items=[
            AdminUserListItem(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                plan=u.plan,
                status=u.status,
                role=u.role,
                created_at=u.created_at,
            )
            for u in users
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/system/health", response_model=SystemHealthResponse)
async def get_system_health(
    service: AdminService = Depends(get_admin_service),
) -> SystemHealthResponse:
    return await service.system_health()


@router.post(
    "/users/{user_id}/suspend",
    response_model=SuspendUserResponse,
    dependencies=[Depends(verify_csrf)],
)
async def suspend_user(
    user_id: uuid.UUID,
    body: SuspendUserRequest,
    current_user: AccessTokenClaims = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> SuspendUserResponse:
    user = await service.suspend_user(current_user.user_id, user_id, body.reason)
    return SuspendUserResponse(id=user.id, status="suspended")  # type: ignore[arg-type]


@router.post(
    "/users/{user_id}/unsuspend",
    response_model=UnsuspendUserResponse,
    dependencies=[Depends(verify_csrf)],
)
async def unsuspend_user(
    user_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> UnsuspendUserResponse:
    user = await service.unsuspend_user(current_user.user_id, user_id)
    return UnsuspendUserResponse(id=user.id, status="active")  # type: ignore[arg-type]
