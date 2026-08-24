"""tasks/remediation-plan.md R1 — FR-USER-001 (profile), FR-USER-003 (usage)."""

import uuid

import pytest

from app.core.email import FakeEmailProvider, get_email_provider
from app.main import app
from tests.conftest import auth_cookie_headers


@pytest.fixture
def email_provider() -> FakeEmailProvider:
    fake = FakeEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_email_provider, None)


async def _register_and_login(client, email: str) -> uuid.UUID:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correcthorse9",
            "display_name": "Profile User",
        },
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correcthorse9"}
    )
    return uuid.UUID(login.json()["id"])


async def test_get_me_returns_profile(client, email_provider):
    user_id = await _register_and_login(client, "profile1@example.com")
    response = await client.get(
        "/api/v1/users/me", headers=auth_cookie_headers(user_id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "profile1@example.com"
    assert body["role"] == "user"
    assert body["plan"] == "free"
    # R1 remediation, audit finding S3 — api.md requires this field; a
    # freshly-registered user has uploaded nothing yet, so 0 is correct,
    # not a placeholder.
    assert body["storage_used_bytes"] == 0


async def test_update_me_changes_display_name(client, email_provider):
    user_id = await _register_and_login(client, "profile2@example.com")
    response = await client.patch(
        "/api/v1/users/me",
        json={"display_name": "New Name"},
        headers=auth_cookie_headers(user_id),
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "New Name"


async def test_update_me_email_change_requires_reverification(client, email_provider):
    """FR-USER-001 — email change requires re-verification."""
    user_id = await _register_and_login(client, "profile3@example.com")
    # Verify original email first.
    token = email_provider.sent[0].body.split("token=")[1].split("\n")[0]
    await client.post("/api/v1/auth/verify-email", json={"token": token})
    email_provider.sent.clear()

    response = await client.patch(
        "/api/v1/users/me",
        json={"email": "profile3-new@example.com"},
        headers=auth_cookie_headers(user_id),
    )
    assert response.status_code == 200
    assert response.json()["email"] == "profile3-new@example.com"
    assert response.json()["email_verified"] is False
    assert len(email_provider.sent) == 1
    assert email_provider.sent[0].to == "profile3-new@example.com"


async def test_get_usage_reports_plan_and_quota(client, email_provider):
    user_id = await _register_and_login(client, "usage@example.com")
    response = await client.get(
        "/api/v1/users/me/usage", headers=auth_cookie_headers(user_id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["storage_quota_bytes"] == 100 * 1024 * 1024
    assert body["ai_requests_daily_limit"] == 30
    assert body["ai_requests_today"] == 0
    # R1 remediation, audit finding S4 — api.md requires both fields.
    # document_count is contractually 0 (no documents exist — R2 hasn't
    # landed), never invented; document_quota is already decided by
    # decisions.md OQ-07 regardless of R2's status.
    assert body["document_count"] == 0
    assert body["document_quota"] == 10


async def test_get_usage_document_quota_is_null_for_pro_plan(
    client, email_provider, db_session
):
    """decisions.md OQ-07 — Pro plan is unlimited documents (null quota),
    distinct from Free's numeric cap (R1 remediation, audit finding S4)."""
    from app.repositories.user_repository import UserRepository

    user_id = await _register_and_login(client, "prousage@example.com")
    await UserRepository(db_session).update(user_id, plan="pro")

    response = await client.get(
        "/api/v1/users/me/usage", headers=auth_cookie_headers(user_id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_quota"] is None
    assert body["storage_quota_bytes"] == 5 * 1024 * 1024 * 1024


async def test_get_me_cross_tenant_never_leaks_another_users_profile(
    client, email_provider
):
    """testing.md §3.5 — a JWT for user A must only ever resolve to A's own
    profile; there is no request-parameter path to another user's data at
    all in this endpoint's design (user_id comes only from the verified
    JWT), which this test exists to keep true under future changes."""
    user_a = await _register_and_login(client, "usera@example.com")
    user_b = await _register_and_login(client, "userb@example.com")

    response_a = await client.get(
        "/api/v1/users/me", headers=auth_cookie_headers(user_a)
    )
    response_b = await client.get(
        "/api/v1/users/me", headers=auth_cookie_headers(user_b)
    )

    assert response_a.json()["email"] == "usera@example.com"
    assert response_b.json()["email"] == "userb@example.com"
