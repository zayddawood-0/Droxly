"""tasks/remediation-plan.md R1 — FR-USER-001 (profile), FR-USER-003 (usage)."""

import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.core.email import EmailProvider
from app.core.security import create_action_token
from app.errors import NotFoundError
from app.models import User
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    AI_DAILY_CAP_FREE,
    AI_DAILY_CAP_PRO,
    STORAGE_QUOTA_BYTES_FREE,
    STORAGE_QUOTA_BYTES_PRO,
)
from app.services.auth_service import VERIFY_EMAIL_TOKEN_TTL


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        ai_request_repo: AiRequestRepository,
        email_provider: EmailProvider,
    ) -> None:
        self.user_repo = user_repo
        self.ai_request_repo = ai_request_repo
        self.email_provider = email_provider

    async def get_profile(self, user_id: uuid.UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError()
        return user

    async def update_profile(
        self,
        user_id: uuid.UUID,
        *,
        display_name: str | None,
        avatar_url: str | None,
        email: str | None,
    ) -> User:
        """FR-USER-001 — email change requires re-verification: setting a
        new email clears email_verified_at and re-sends the verification
        email, reusing R1's own verify_email mechanism rather than a
        second, parallel implementation."""
        fields: dict[str, object] = {}
        if display_name is not None:
            fields["display_name"] = display_name
        if avatar_url is not None:
            fields["avatar_url"] = avatar_url

        email_changed = email is not None
        if email_changed:
            fields["email"] = email
            fields["email_verified_at"] = None

        user = await self.user_repo.update(user_id, **fields)
        if user is None:
            raise NotFoundError()

        if email_changed:
            token = create_action_token(
                user.id, purpose="verify_email", expires_in=VERIFY_EMAIL_TOKEN_TTL
            )
            link = f"{settings.frontend_base_url}/verify-email?token={token}"
            await self.email_provider.send(
                to=user.email,
                subject="Verify your new email address",
                body=f"Verify your new email: {link}\nThis link expires in 24 hours.",
            )
        return user

    async def get_usage(self, user_id: uuid.UUID) -> dict:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError()

        is_pro = user.plan == "pro"
        today_start = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        ai_requests_today = await self.ai_request_repo.count_since(user_id, today_start)

        return {
            "plan": user.plan,
            "storage_used_bytes": user.storage_used_bytes,
            "storage_quota_bytes": (
                STORAGE_QUOTA_BYTES_PRO if is_pro else STORAGE_QUOTA_BYTES_FREE
            ),
            "ai_requests_today": ai_requests_today,
            "ai_requests_daily_limit": (
                AI_DAILY_CAP_PRO if is_pro else AI_DAILY_CAP_FREE
            ),
        }
