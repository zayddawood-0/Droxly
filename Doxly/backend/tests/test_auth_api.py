"""
tasks/remediation-plan.md R1 — testing.md §3.3 API tests +
§3.4 Authentication tests (FR-AUTH-001..008) + §3.5 cross-tenant tests.
"""

import uuid

import pytest

from app.core.email import FakeEmailProvider, get_email_provider
from app.main import app
from tests.conftest import auth_cookie_headers


@pytest.fixture
def email_provider() -> FakeEmailProvider:
    """A test-controlled FakeEmailProvider, overridden into the real DI
    chain — see conftest.py's note on why a fresh instance per app-level
    get_email_provider() call is otherwise uninspectable."""
    fake = FakeEmailProvider()
    app.dependency_overrides[get_email_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_email_provider, None)


def _extract_token(body: str) -> str:
    return body.split("token=")[1].split("\n")[0]


# --- FR-AUTH-001 registration ---


async def test_register_creates_unverified_user(client, email_provider):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "correcthorse9",
            "display_name": "New User",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["email_verified"] is False
    assert len(email_provider.sent) == 1
    assert email_provider.sent[0].to == "new@example.com"


async def test_register_duplicate_email_returns_generic_error(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "password": "correcthorse9",
            "display_name": "B",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "registration_failed"


async def test_register_weak_password_rejected_before_any_db_write(
    client, email_provider
):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short", "display_name": "A"},
    )
    assert response.status_code == 422
    # R1 remediation, audit finding S1 — a 422 must carry api.md §0.5's
    # envelope, not FastAPI's default {"detail": [...]}. Every key is
    # asserted, not just presence, so a regression to the default shape
    # (which has none of these keys, only "detail") fails loudly here.
    body = response.json()
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert error["code"] == "validation_error"
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["request_id"], str) and error["request_id"]
    assert error["fields"]["password"]
    assert len(email_provider.sent) == 0

    # Confirms no partial account was created — the same email can still register.
    ok = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    assert ok.status_code == 201


# --- FR-AUTH-002 email verification ---


async def test_verify_email_sets_verified_flag(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "verify@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    token = _extract_token(email_provider.sent[0].body)

    response = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200
    assert response.json()["verified"] is True

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "verify@example.com", "password": "correcthorse9"},
    )
    profile = await client.get(
        "/api/v1/users/me", headers=auth_cookie_headers(uuid.UUID(login.json()["id"]))
    )
    assert profile.json()["email_verified"] is True


async def test_verify_email_invalid_token_rejected(client, email_provider):
    response = await client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_or_expired_token"


# --- FR-AUTH-004 login ---


async def test_login_success_sets_cookies(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "correcthorse9"},
    )
    assert response.status_code == 200
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    assert "csrf_token" in response.cookies


async def test_login_wrong_password_generic_error(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpw@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "wrongwrong1"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_unknown_email_same_error_as_wrong_password(client, email_provider):
    """NFR-SEC-006 — never reveals whether the email exists."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever12"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_oauth_only_account_rejects_password(client, db_session):
    from app.models import User

    user = User(
        email="oauthonly@example.com",
        display_name="OAuth User",
        password_hash=None,
        oauth_provider="google",
        oauth_provider_id="google-sub-1",
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "oauthonly@example.com", "password": "anything12"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


# --- FR-AUTH-005 session refresh ---


async def test_refresh_issues_new_access_token_and_rotates_refresh_token(
    client, email_provider
):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "correcthorse9"},
    )
    old_refresh = login.cookies["refresh_token"]

    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    new_refresh = response.cookies["refresh_token"]
    assert new_refresh != old_refresh


async def test_refresh_reused_rotated_token_revokes_family(client, email_provider):
    """security.md §2.2 — reuse of an already-rotated-away refresh token is
    a theft signal; the whole family is revoked, so even the CURRENT valid
    token stops working."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "reuse@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reuse@example.com", "password": "correcthorse9"},
    )
    old_refresh = login.cookies["refresh_token"]

    first_refresh = await client.post("/api/v1/auth/refresh")
    assert first_refresh.status_code == 200
    current_refresh = first_refresh.cookies["refresh_token"]

    # Replay the OLD (already-rotated-away) token.
    client.cookies.set("refresh_token", old_refresh)
    replay = await client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401

    # The legitimate, currently-valid token is now also revoked.
    client.cookies.set("refresh_token", current_refresh)
    should_also_fail = await client.post("/api/v1/auth/refresh")
    assert should_also_fail.status_code == 401


async def test_refresh_without_cookie_rejected(client):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


# --- FR-AUTH-006 logout ---


async def test_logout_revokes_refresh_token(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "correcthorse9"},
    )

    logout = await client.post(
        "/api/v1/auth/logout",
        headers=auth_cookie_headers(uuid.UUID(login.json()["id"])),
    )
    assert logout.status_code == 204

    refresh_attempt = await client.post("/api/v1/auth/refresh")
    assert refresh_attempt.status_code == 401


# --- FR-AUTH-007 password reset ---


async def test_password_reset_flow_revokes_all_sessions(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "reset@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "correcthorse9"},
    )
    assert login.status_code == 200

    email_provider.sent.clear()
    req = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "reset@example.com"}
    )
    assert req.status_code == 202
    reset_token = _extract_token(email_provider.sent[0].body)

    confirm = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "newpassword2"},
    )
    assert confirm.status_code == 200

    # "Revokes ALL existing refresh tokens for the account" — the prior
    # session's refresh token no longer works.
    refresh_attempt = await client.post("/api/v1/auth/refresh")
    assert refresh_attempt.status_code == 401

    # New password works; old one doesn't.
    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "correcthorse9"},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "newpassword2"},
    )
    assert new_login.status_code == 200


async def test_password_reset_request_unconditionally_202_for_unknown_email(
    client, email_provider
):
    """NFR-SEC-006 — never reveals whether the email is registered."""
    response = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "nobody-at-all@example.com"},
    )
    assert response.status_code == 202
    assert len(email_provider.sent) == 0


# --- FR-AUTH-008 session/device management + cross-tenant (testing.md §3.5) ---


async def test_sessions_list_shows_active_session(client, email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "sessions@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "sessions@example.com", "password": "correcthorse9"},
    )
    user_id = uuid.UUID(login.json()["id"])

    response = await client.get(
        "/api/v1/auth/sessions", headers=auth_cookie_headers(user_id)
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


async def test_revoke_session_cross_tenant_returns_404_not_403(client, email_provider):
    """testing.md §3.5 — User A must never be able to revoke User B's
    session, and the response must be 404 (not 403), so User A can't even
    infer the session exists."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "victim@example.com",
            "password": "correcthorse9",
            "display_name": "V",
        },
    )
    victim_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "victim@example.com", "password": "correcthorse9"},
    )
    victim_id = uuid.UUID(victim_login.json()["id"])
    victim_sessions = await client.get(
        "/api/v1/auth/sessions", headers=auth_cookie_headers(victim_id)
    )
    victim_session_id = victim_sessions.json()["items"][0]["id"]

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "attacker@example.com",
            "password": "correcthorse9",
            "display_name": "X",
        },
    )
    attacker_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "attacker@example.com", "password": "correcthorse9"},
    )
    attacker_id = uuid.UUID(attacker_login.json()["id"])

    response = await client.delete(
        f"/api/v1/auth/sessions/{victim_session_id}",
        headers=auth_cookie_headers(attacker_id),
    )
    assert response.status_code == 404

    # The victim's session is untouched.
    still_active = await client.get(
        "/api/v1/auth/sessions", headers=auth_cookie_headers(victim_id)
    )
    assert len(still_active.json()["items"]) == 1


# --- unauthenticated access ---


async def test_protected_endpoint_without_cookie_returns_401(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_protected_endpoint_with_garbage_cookie_returns_401(client):
    response = await client.get(
        "/api/v1/users/me", headers={"Cookie": "access_token=not-a-real-jwt"}
    )
    assert response.status_code == 401


# --- R1 remediation (audit findings S2, S5, S6, S7) ---


async def test_sessions_response_shape_and_is_current(client, email_provider):
    """R1 remediation, audit finding S2 — exact api.md contract: an `items`
    wrapper, `expires_at`, and `is_current` computed from the request's own
    refresh_token cookie."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "shapecheck@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "shapecheck@example.com", "password": "correcthorse9"},
    )
    cookie_header = (
        f"access_token={login.cookies['access_token']}; "
        f"refresh_token={login.cookies['refresh_token']}"
    )

    response = await client.get(
        "/api/v1/auth/sessions", headers={"Cookie": cookie_header}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items"}
    assert len(body["items"]) == 1

    session = body["items"][0]
    assert set(session.keys()) == {
        "id",
        "device_label",
        "ip_address",
        "created_at",
        "expires_at",
        "is_current",
    }
    assert session["is_current"] is True


async def test_sessions_is_current_false_for_a_different_session(
    client, email_provider
):
    """The current request's own session is flagged true; a second,
    unrelated session for the same user is flagged false."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "twosessions@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    first_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "twosessions@example.com", "password": "correcthorse9"},
    )
    second_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "twosessions@example.com", "password": "correcthorse9"},
    )
    cookie_header = (
        f"access_token={second_login.cookies['access_token']}; "
        f"refresh_token={second_login.cookies['refresh_token']}"
    )

    response = await client.get(
        "/api/v1/auth/sessions", headers={"Cookie": cookie_header}
    )
    items = response.json()["items"]
    assert len(items) == 2
    current_flags = sorted(item["is_current"] for item in items)
    assert current_flags == [False, True]
    assert first_login.cookies["refresh_token"] != second_login.cookies["refresh_token"]


async def test_register_throttled_after_five_attempts(client, email_provider):
    """R1 remediation, audit finding S5 — registration shares login's
    account+IP AuthThrottle, independent of the general per-IP tier
    (which conftest.py's `client` fixture overrides to a no-op, so any
    429 observed here can only come from AuthThrottle)."""
    payload = {
        "email": "throttlereg@example.com",
        "password": "correcthorse9",
        "display_name": "A",
    }
    for _ in range(5):
        await client.post("/api/v1/auth/register", json=payload)

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in response.headers


async def test_password_reset_request_throttled_after_five_attempts(
    client, email_provider
):
    """R1 remediation, audit finding S5."""
    payload = {"email": "throttlereset@example.com"}
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/password-reset/request", json=payload
        )
        assert response.status_code == 202

    blocked = await client.post("/api/v1/auth/password-reset/request", json=payload)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_verify_email_resend_cooldown(client, email_provider):
    """R1 remediation, audit finding S6 — api.md: "Rate-limited to 1 per 5
    minutes per account ... independent of the general per-minute limit.\" """
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "resendcooldown@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "resendcooldown@example.com", "password": "correcthorse9"},
    )
    user_id = uuid.UUID(login.json()["id"])

    first = await client.post(
        "/api/v1/auth/verify-email/resend", headers=auth_cookie_headers(user_id)
    )
    assert first.status_code == 202

    second = await client.post(
        "/api/v1/auth/verify-email/resend", headers=auth_cookie_headers(user_id)
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"


async def test_login_success_writes_audit_log(client, email_provider, db_session):
    """R1 remediation, audit finding S7."""
    from app.repositories.observability_repository import AuditLogRepository

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "auditsuccess@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "auditsuccess@example.com", "password": "correcthorse9"},
    )
    user_id = uuid.UUID(login.json()["id"])

    logs = await AuditLogRepository(db_session).list_for_actor(user_id)
    assert any(log.action == "login_success" for log in logs)


async def test_login_wrong_password_writes_audit_log(
    client, email_provider, db_session
):
    """R1 remediation, audit finding S7."""
    from app.repositories.observability_repository import AuditLogRepository
    from app.repositories.user_repository import UserRepository

    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "auditwrongpw@example.com",
            "password": "correcthorse9",
            "display_name": "A",
        },
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "auditwrongpw@example.com", "password": "wrongwrong1"},
    )

    user = await UserRepository(db_session).get_by_email("auditwrongpw@example.com")
    logs = await AuditLogRepository(db_session).list_for_actor(user.id)
    assert any(log.action == "login_failed" for log in logs)


async def test_login_unknown_email_writes_audit_log(client, db_session):
    """R1 remediation, audit finding S7 — previously silently skipped;
    audit_logs.user_id is nullable specifically for this case, and the
    attempted email is preserved in metadata_json so enumeration attempts
    against nonexistent accounts remain visible."""
    from sqlalchemy import select

    from app.models import AuditLog

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "totally-unknown-account@example.com", "password": "whatever12"},
    )
    assert response.status_code == 401

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "login_failed", AuditLog.user_id.is_(None)
        )
    )
    logs = result.scalars().all()
    assert any(
        log.metadata_json
        and log.metadata_json.get("attempted_email")
        == "totally-unknown-account@example.com"
        for log in logs
    )
