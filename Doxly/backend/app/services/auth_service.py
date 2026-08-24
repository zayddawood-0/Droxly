"""
tasks/remediation-plan.md R1 — registration, login, refresh rotation,
logout/revocation, password reset, email verification, OAuth
linking/creation, session management. skills/backend.md §3: business rules
live here, never in the router.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.email import EmailProvider
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_action_token,
    decode_action_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    parse_device_label,
    verify_password,
)
from app.errors import (
    AccountSuspendedError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    RegistrationFailedError,
    UnauthorizedError,
)
from app.models import RefreshToken, User
from app.repositories.observability_repository import AuditLogRepository
from app.repositories.user_repository import RefreshTokenRepository, UserRepository

VERIFY_EMAIL_TOKEN_TTL = timedelta(hours=24)
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_token_repo: RefreshTokenRepository,
        audit_log_repo: AuditLogRepository,
        email_provider: EmailProvider,
    ) -> None:
        self.user_repo = user_repo
        self.refresh_token_repo = refresh_token_repo
        self.audit_log_repo = audit_log_repo
        self.email_provider = email_provider

    # --- FR-AUTH-001 ---
    async def register(self, *, email: str, password: str, display_name: str) -> User:
        existing = await self.user_repo.get_by_email(email)
        if existing is not None:
            # NFR-SEC-006 — identical error whether the email is taken or
            # any other registration failure; never a distinguishable
            # "email already exists" response.
            raise RegistrationFailedError()

        user = await self.user_repo.create(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            plan="free",
        )
        await self._send_verification_email(user)
        return user

    async def _send_verification_email(self, user: User) -> None:
        token = create_action_token(
            user.id, purpose="verify_email", expires_in=VERIFY_EMAIL_TOKEN_TTL
        )
        link = f"{settings.frontend_base_url}/verify-email?token={token}"
        await self.email_provider.send(
            to=user.email,
            subject="Verify your Doxly account",
            body=f"Verify your email: {link}\nThis link expires in 24 hours.",
        )

    # --- FR-AUTH-002 ---
    async def verify_email(self, token: str) -> None:
        try:
            user_id = decode_action_token(token, expected_purpose="verify_email")
        except InvalidTokenError as exc:
            raise InvalidOrExpiredTokenError() from exc

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise InvalidOrExpiredTokenError()
        await self.user_repo.update(user_id, email_verified_at=datetime.now(UTC))

    async def resend_verification(self, user_id: uuid.UUID) -> None:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise InvalidOrExpiredTokenError()
        await self._send_verification_email(user)

    # --- FR-AUTH-004 ---
    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[User, str, str]:
        """Returns (user, access_token, raw_refresh_token)."""
        user = await self.user_repo.get_by_email(email)

        # OAuth-only accounts (password_hash IS NULL) rejected with the
        # same generic error as a wrong password (security.md §2.1) — no
        # branch that would let a caller distinguish "no such account,"
        # "OAuth-only account," and "wrong password" from each other.
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            # security.md §2.4 — "every login attempt, success or failure,
            # is written to audit_logs," with no carve-out for unknown
            # emails. audit_logs.user_id is nullable for exactly this case
            # (system/unattributable events); the attempted email is
            # recorded in metadata_json — non-sensitive operational
            # metadata identifying WHAT was targeted, the same category as
            # document_deleted's document_id (security.md §12), not a
            # credential or content value — so enumeration/credential-
            # stuffing patterns against nonexistent accounts remain visible
            # to an admin, which was silently lost before this fix (R1
            # remediation, audit finding S7).
            await self.audit_log_repo.log(
                user_id=user.id if user is not None else None,
                action="login_failed",
                ip_address=ip_address,
                metadata_json=None if user is not None else {"attempted_email": email},
            )
            raise InvalidCredentialsError()

        if user.status == "suspended":
            raise AccountSuspendedError()

        await self.audit_log_repo.log(
            user_id=user.id, action="login_success", ip_address=ip_address
        )
        access_token = create_access_token(user.id, user.role)
        raw_refresh, _ = await self._issue_refresh_token(
            user.id, ip_address, user_agent
        )
        return user, access_token, raw_refresh

    async def issue_tokens_for_user(
        self, user: User, *, ip_address: str | None, user_agent: str | None
    ) -> tuple[str, str]:
        """Public entry point for flows that have already resolved a User
        outside of password login (currently: OAuth) but still need a
        fresh access/refresh pair issued the same way login() does."""
        access_token = create_access_token(user.id, user.role)
        raw_refresh, _ = await self._issue_refresh_token(
            user.id, ip_address, user_agent
        )
        return access_token, raw_refresh

    async def _issue_refresh_token(
        self, user_id: uuid.UUID, ip_address: str | None, user_agent: str | None
    ) -> tuple[str, RefreshToken]:
        raw = generate_refresh_token()
        row = await self.refresh_token_repo.create(
            user_id,
            token_hash=hash_refresh_token(raw),
            device_label=parse_device_label(user_agent),
            ip_address=ip_address,
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
        return raw, row

    # --- FR-AUTH-005 ---
    async def refresh(
        self, *, raw_refresh_token: str, ip_address: str | None, user_agent: str | None
    ) -> tuple[User, str, str]:
        """Returns (user, new_access_token, new_raw_refresh_token). Rotates
        on every use and revokes the old token (security.md §2.2)."""
        token_hash = hash_refresh_token(raw_refresh_token)
        row = await self.refresh_token_repo.get_by_token_hash(token_hash)
        if row is None:
            raise UnauthorizedError()

        if row.revoked_at is not None:
            # Reuse of an already-rotated-away token — a strong theft
            # signal (security.md §2.2): revoke the whole family.
            await self.refresh_token_repo.revoke_all_for_user(row.user_id)
            raise UnauthorizedError()

        if row.expires_at <= datetime.now(UTC):
            raise UnauthorizedError()

        user = await self.user_repo.get_by_id(row.user_id)
        if user is None or user.status == "suspended":
            raise UnauthorizedError()

        await self.refresh_token_repo.revoke(row.user_id, row.id)
        access_token = create_access_token(user.id, user.role)
        new_raw, _ = await self._issue_refresh_token(user.id, ip_address, user_agent)
        return user, access_token, new_raw

    # --- FR-AUTH-006 ---
    async def logout(
        self, *, user_id: uuid.UUID, raw_refresh_token: str | None
    ) -> None:
        if raw_refresh_token:
            row = await self.refresh_token_repo.get_by_token_hash(
                hash_refresh_token(raw_refresh_token)
            )
            if row is not None and row.user_id == user_id:
                await self.refresh_token_repo.revoke(user_id, row.id)
        await self.audit_log_repo.log(user_id=user_id, action="logout")

    # --- FR-AUTH-007 ---
    async def request_password_reset(self, email: str) -> None:
        """Always returns normally (202 unconditionally, per api.md §1 /
        NFR-SEC-006) — silently no-ops if the email isn't registered."""
        user = await self.user_repo.get_by_email(email)
        if user is None:
            return
        token = create_action_token(
            user.id, purpose="password_reset", expires_in=PASSWORD_RESET_TOKEN_TTL
        )
        link = f"{settings.frontend_base_url}/reset-password?token={token}"
        await self.email_provider.send(
            to=user.email,
            subject="Reset your Doxly password",
            body=f"Reset your password: {link}\nThis link expires in 1 hour.",
        )

    async def confirm_password_reset(self, *, token: str, new_password: str) -> None:
        try:
            user_id = decode_action_token(token, expected_purpose="password_reset")
        except InvalidTokenError as exc:
            raise InvalidOrExpiredTokenError() from exc

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise InvalidOrExpiredTokenError()

        await self.user_repo.update(user_id, password_hash=hash_password(new_password))
        # "Revokes ALL existing refresh tokens for the account" — the one
        # side effect testing.md §3.4 flags as easy to omit.
        await self.refresh_token_repo.revoke_all_for_user(user_id)
        await self.audit_log_repo.log(user_id=user_id, action="password_reset")

    # --- FR-AUTH-008 ---
    async def list_sessions(self, user_id: uuid.UUID) -> list[RefreshToken]:
        return await self.refresh_token_repo.list_active_for_user(user_id)

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        return await self.refresh_token_repo.revoke(user_id, session_id)

    # --- FR-AUTH-003 ---
    async def oauth_login_or_link(
        self,
        *,
        provider_id: str,
        email: str,
        display_name: str,
        avatar_url: str | None,
    ) -> User:
        """
        First checks for a returning OAuth user (provider + provider_id),
        then falls back to linking an existing password-signup account with
        the same email (never creating a duplicate), then creates a new
        user only if neither exists — matching FR-AUTH-003's acceptance
        criteria exactly.
        """
        existing_by_oauth = await self.user_repo.get_by_oauth_identity(
            "google", provider_id
        )
        if existing_by_oauth is not None:
            return existing_by_oauth

        existing_by_email = await self.user_repo.get_by_email(email)
        if existing_by_email is not None:
            linked = await self.user_repo.update(
                existing_by_email.id,
                oauth_provider="google",
                oauth_provider_id=provider_id,
            )
            assert linked is not None
            return linked

        return await self.user_repo.create(
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            oauth_provider="google",
            oauth_provider_id=provider_id,
            email_verified_at=datetime.now(UTC),
            plan="free",
        )
