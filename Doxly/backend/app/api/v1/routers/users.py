"""api.md §2 (/users) — tasks/remediation-plan.md R1."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csrf import verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.email import EmailProvider, get_email_provider
from app.core.rate_limit import rate_limit_general
from app.core.security import AccessTokenClaims
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UsageResponse, UserResponse, UserUpdateRequest
from app.services.user_service import UserService

router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(rate_limit_general)]
)


def get_user_service(
    db: AsyncSession = Depends(get_db_session),
    email_provider: EmailProvider = Depends(get_email_provider),
) -> UserService:
    return UserService(UserRepository(db), AiRequestRepository(db), email_provider)


def _to_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        role=user.role,
        plan=user.plan,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.get_profile(current_user.user_id)
    return _to_response(user)


@router.patch("/me", response_model=UserResponse, dependencies=[Depends(verify_csrf)])
async def update_me(
    body: UserUpdateRequest,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.update_profile(
        current_user.user_id,
        display_name=body.display_name,
        avatar_url=body.avatar_url,
        email=body.email,
    )
    return _to_response(user)


@router.get("/me/usage", response_model=UsageResponse)
async def get_usage(
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UsageResponse:
    usage = await service.get_usage(current_user.user_id)
    return UsageResponse(**usage)
