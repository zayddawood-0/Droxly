"""
tasks/remediation-plan.md R1 — FR-AUTH-003's account-linking business logic,
tested at the service layer against the real DB-backed repositories (the
same pattern testing.md §3.2 uses elsewhere) since the OAuth *transport*
(redirecting to Google, exchanging a code) cannot be exercised without real
Google credentials, which this environment doesn't have (documented in
tasks/R1-authentication.md). What CAN and must be tested without any
network call is the create-vs-link decision AuthService.oauth_login_or_link
makes — exactly the part FR-AUTH-003's acceptance criteria are about.
"""

from app.core.email import FakeEmailProvider
from app.repositories.observability_repository import AuditLogRepository
from app.repositories.user_repository import RefreshTokenRepository, UserRepository
from app.services.auth_service import AuthService


def _service(db_session) -> AuthService:
    return AuthService(
        UserRepository(db_session),
        RefreshTokenRepository(db_session),
        AuditLogRepository(db_session),
        FakeEmailProvider(),
    )


async def test_oauth_creates_new_user_on_first_sign_in(db_session):
    """FR-AUTH-003 — "Given a Google account not previously seen, when
    OAuth completes, then a new user is created and logged in.\" """
    service = _service(db_session)

    user = await service.oauth_login_or_link(
        provider_id="google-sub-new",
        email="fresh-oauth@example.com",
        display_name="Fresh User",
        avatar_url="https://example.com/avatar.png",
    )

    assert user.oauth_provider == "google"
    assert user.oauth_provider_id == "google-sub-new"
    assert user.password_hash is None
    assert user.email_verified_at is not None  # Google already verified it
    assert user.plan == "free"


async def test_oauth_returning_user_matches_by_provider_identity(db_session):
    service = _service(db_session)
    first = await service.oauth_login_or_link(
        provider_id="google-sub-returning",
        email="returning@example.com",
        display_name="Returning User",
        avatar_url=None,
    )

    second = await service.oauth_login_or_link(
        provider_id="google-sub-returning",
        email="returning@example.com",
        display_name="Returning User",
        avatar_url=None,
    )

    assert second.id == first.id


async def test_oauth_links_existing_password_account_instead_of_duplicating(db_session):
    """FR-AUTH-003 — "Given an email that already exists via password
    signup, when the same email completes Google OAuth, then the accounts
    are linked, not duplicated.\" """
    service = _service(db_session)
    password_user = await service.register(
        email="linkme@example.com",
        password="correcthorse9",
        display_name="Password User",
    )

    linked = await service.oauth_login_or_link(
        provider_id="google-sub-link",
        email="linkme@example.com",
        display_name="Password User",
        avatar_url=None,
    )

    assert linked.id == password_user.id
    assert linked.oauth_provider == "google"
    assert linked.oauth_provider_id == "google-sub-link"
    # The password credential is preserved, not wiped by linking — the user
    # can still log in with either method afterward.
    assert linked.password_hash is not None
