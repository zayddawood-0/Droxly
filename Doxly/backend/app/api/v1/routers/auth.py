"""api.md §1 (/auth) — tasks/remediation-plan.md R1."""

import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.csrf import generate_csrf_token, set_csrf_cookie, verify_csrf
from app.core.dependencies import get_current_user, get_db_session
from app.core.email import EmailProvider, get_email_provider
from app.core.rate_limit import auth_throttle, rate_limit_general
from app.core.security import (
    GOOGLE_AUTHORIZE_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_USERINFO_URL,
    AccessTokenClaims,
    google_oauth_client,
)
from app.errors import (
    NotFoundError,
    OAuthFailedError,
    OAuthNotConfiguredError,
    UnauthorizedError,
)
from app.repositories.observability_repository import AuditLogRepository
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    RegisterRequest,
    RegisterResponse,
    SessionResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth", tags=["auth"], dependencies=[Depends(rate_limit_general)]
)

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_CALLBACK_PATH = "/api/v1/auth/oauth/google/callback"


def get_auth_service(
    db: AsyncSession = Depends(get_db_session),
    email_provider: EmailProvider = Depends(get_email_provider),
) -> AuthService:
    return AuthService(
        UserRepository(db),
        RefreshTokenRepository(db),
        AuditLogRepository(db),
        email_provider,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _cookies_secure() -> bool:
    return settings.environment != "local"


def _set_session_cookies(
    response: Response, *, access_token: str, refresh_token: str
) -> None:
    secure = _cookies_secure()
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # security.md §2.3 — the refresh cookie is scoped narrowly to the /auth
    # path (its only two consumers: this endpoint's own rotation, and
    # /auth/logout) rather than the whole API, reducing its exposure surface.
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    set_csrf_cookie(response, generate_csrf_token())


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/api/v1/auth")
    response.delete_cookie("csrf_token", path="/")


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    body: RegisterRequest, service: AuthService = Depends(get_auth_service)
) -> RegisterResponse:
    user = await service.register(
        email=body.email, password=body.password, display_name=body.display_name
    )
    return RegisterResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified=False,
    )


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    body: VerifyEmailRequest, service: AuthService = Depends(get_auth_service)
) -> VerifyEmailResponse:
    await service.verify_email(body.token)
    return VerifyEmailResponse()


@router.post(
    "/verify-email/resend", status_code=202, dependencies=[Depends(verify_csrf)]
)
async def resend_verification(
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.resend_verification(current_user.user_id)


@router.get("/oauth/google")
async def oauth_google_start() -> RedirectResponse:
    client = google_oauth_client()
    if client is None:
        raise OAuthNotConfiguredError()

    redirect_uri = f"{settings.frontend_base_url}{OAUTH_CALLBACK_PATH}"
    uri, state = client.create_authorization_url(
        GOOGLE_AUTHORIZE_URL, redirect_uri=redirect_uri
    )

    redirect = RedirectResponse(uri, status_code=302)
    redirect.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        secure=_cookies_secure(),
        samesite="lax",
        path="/api/v1/auth/oauth",
        max_age=600,
    )
    return redirect


@router.get("/oauth/google/callback")
async def oauth_google_callback(
    request: Request,
    code: str,
    state: str,
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    client = google_oauth_client()
    if client is None:
        raise OAuthNotConfiguredError()

    stored_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not stored_state or stored_state != state:
        raise OAuthFailedError()

    redirect_uri = f"{settings.frontend_base_url}{OAUTH_CALLBACK_PATH}"
    try:
        await client.fetch_token(GOOGLE_TOKEN_URL, code=code, redirect_uri=redirect_uri)
        userinfo = (await client.get(GOOGLE_USERINFO_URL)).json()
    except Exception as exc:  # authlib/httpx transport or Google-side failure
        raise OAuthFailedError() from exc

    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not google_sub or not email:
        raise OAuthFailedError()

    user = await service.oauth_login_or_link(
        provider_id=google_sub,
        email=email,
        display_name=userinfo.get("name") or email,
        avatar_url=userinfo.get("picture"),
    )
    access_token, raw_refresh = await service.issue_tokens_for_user(
        user,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    redirect = RedirectResponse(
        f"{settings.frontend_base_url}/dashboard", status_code=302
    )
    _set_session_cookies(redirect, access_token=access_token, refresh_token=raw_refresh)
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/oauth")
    return redirect


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    ip = _client_ip(request) or "unknown"
    await auth_throttle.check(body.email, ip)

    try:
        user, access_token, refresh_token = await service.login(
            email=body.email,
            password=body.password,
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:
        await auth_throttle.record_failure(body.email, ip)
        raise

    await auth_throttle.reset(body.email, ip)
    _set_session_cookies(
        response, access_token=access_token, refresh_token=refresh_token
    )
    return LoginResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        plan=user.plan,
    )


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not raw_refresh_token:
        raise UnauthorizedError()

    _user, access_token, new_refresh = await service.refresh(
        raw_refresh_token=raw_refresh_token,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookies(response, access_token=access_token, refresh_token=new_refresh)
    return {}


@router.post("/logout", status_code=204, dependencies=[Depends(verify_csrf)])
async def logout(
    request: Request,
    response: Response,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(
        user_id=current_user.user_id,
        raw_refresh_token=request.cookies.get(REFRESH_TOKEN_COOKIE),
    )
    _clear_session_cookies(response)


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(
    body: PasswordResetRequestRequest, service: AuthService = Depends(get_auth_service)
) -> None:
    await service.request_password_reset(body.email)


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    body: PasswordResetConfirmRequest, service: AuthService = Depends(get_auth_service)
) -> dict:
    await service.confirm_password_reset(
        token=body.token, new_password=body.new_password
    )
    return {}


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> list[SessionResponse]:
    sessions = await service.list_sessions(current_user.user_id)
    return [SessionResponse.model_validate(s) for s in sessions]


@router.delete(
    "/sessions/{session_id}", status_code=204, dependencies=[Depends(verify_csrf)]
)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: AccessTokenClaims = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    revoked = await service.revoke_session(current_user.user_id, session_id)
    if not revoked:
        raise NotFoundError()
