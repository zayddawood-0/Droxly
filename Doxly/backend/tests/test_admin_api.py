"""
api.md §12 (/admin) — tasks/remediation-plan.md R10. Full HTTP-layer
contract tests: exact response shapes, error envelopes, the role-check
authorization suite (non-admin gets 403 on every route, per
remediation-plan.md §13's explicit requirement), the FR-ADMIN-003 "suspend
immediately revokes the CURRENT session, not just future logins" cross-role
test, audit logging, and the NFR-PRIV-004 "never document content" check.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Document
from app.repositories.observability_repository import AuditLogRepository
from app.repositories.user_repository import RefreshTokenRepository
from tests.conftest import auth_cookie_headers, make_user


async def _make_admin(db_session):
    admin = await make_user(db_session)
    admin.role = "admin"
    await db_session.flush()
    return admin


async def _make_document(db_session, user_id) -> Document:
    document = Document(
        user_id=user_id,
        file_name="report.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    return document


# --- Authorization: role check on every route (remediation-plan.md §13) ---


async def test_non_admin_gets_403_on_every_admin_route(client, db_session):
    user = await make_user(db_session)
    headers = auth_cookie_headers(user.id)

    routes = [
        ("GET", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/system/health"),
        ("POST", f"/api/v1/admin/users/{uuid.uuid4()}/suspend"),
        ("POST", f"/api/v1/admin/users/{uuid.uuid4()}/unsuspend"),
    ]
    for method, path in routes:
        response = await client.request(
            method,
            path,
            headers=headers,
            json={"reason": "x"} if method == "POST" else None,
        )
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
        assert response.json()["error"]["code"] == "forbidden"


async def test_unauthenticated_gets_401_not_403_on_admin_routes(client, db_session):
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_admin_user_succeeds_on_every_admin_route(client, db_session):
    admin = await _make_admin(db_session)
    headers = auth_cookie_headers(admin.id, role="admin")

    users_resp = await client.get("/api/v1/admin/users", headers=headers)
    assert users_resp.status_code == 200

    health_resp = await client.get("/api/v1/admin/system/health", headers=headers)
    assert health_resp.status_code == 200


# --- GET /admin/users ---


async def test_list_users_returns_the_exact_documented_shape(client, db_session):
    admin = await _make_admin(db_session)
    await make_user(db_session)

    response = await client.get(
        "/api/v1/admin/users", headers=auth_cookie_headers(admin.id, role="admin")
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    item = body["items"][0]
    assert set(item.keys()) == {
        "id",
        "email",
        "display_name",
        "plan",
        "status",
        "role",
        "created_at",
    }


async def test_list_users_never_returns_document_content(client, db_session):
    """NFR-PRIV-004 / FR-ADMIN-001's explicit acceptance criterion."""
    admin = await _make_admin(db_session)
    other = await make_user(db_session)
    await _make_document(db_session, other.id)

    response = await client.get(
        "/api/v1/admin/users", headers=auth_cookie_headers(admin.id, role="admin")
    )

    assert response.status_code == 200
    body_text = response.text
    assert "report.pdf" not in body_text
    assert "storage_key" not in body_text


async def test_list_users_filters_by_status(client, db_session):
    admin = await _make_admin(db_session)
    suspended = await make_user(db_session)
    suspended.status = "suspended"
    await db_session.flush()

    response = await client.get(
        "/api/v1/admin/users",
        params={"status": "suspended"},
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(suspended.id) in ids
    assert str(admin.id) not in ids


# --- GET /admin/system/health ---


async def test_system_health_returns_the_exact_documented_shape(client, db_session):
    admin = await _make_admin(db_session)

    response = await client.get(
        "/api/v1/admin/system/health",
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "queue_depth",
        "processing_failure_rate_24h",
        "ai_requests_24h",
        "ai_error_rate_24h",
    }
    assert isinstance(body["queue_depth"], int)


# --- POST /admin/users/{id}/suspend ---


async def test_suspend_user_returns_the_documented_shape_and_sets_status(
    client, db_session
):
    admin = await _make_admin(db_session)
    target = await make_user(db_session)

    response = await client.post(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"reason": "ToS violation"},
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 200
    assert response.json() == {"id": str(target.id), "status": "suspended"}
    await db_session.refresh(target)
    assert target.status == "suspended"


async def test_suspend_user_revokes_all_active_refresh_tokens(client, db_session):
    admin = await _make_admin(db_session)
    target = await make_user(db_session)

    token_repo = RefreshTokenRepository(db_session)
    token = await token_repo.create(
        target.id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    await client.post(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"reason": "abuse"},
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    active = await token_repo.list_active_for_user(target.id)
    assert token.id not in {t.id for t in active}


async def test_suspend_user_writes_an_audit_log_row(client, db_session):
    admin = await _make_admin(db_session)
    target = await make_user(db_session)

    await client.post(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"reason": "spam"},
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    logs = await AuditLogRepository(db_session).list_for_actor(admin.id)
    entry = next(log for log in logs if log.action == "admin_suspend_user")
    assert entry.target_user_id == target.id
    assert entry.metadata_json == {"reason": "spam"}


async def test_suspend_user_404s_for_an_unknown_id(client, db_session):
    admin = await _make_admin(db_session)

    response = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/suspend",
        json={"reason": "x"},
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_suspend_user_immediately_invalidates_the_targets_current_session(
    client, db_session
):
    """
    FR-ADMIN-003's explicit "immediately revoking all sessions" clause
    (remediation-plan.md §13's own cross-role test requirement): the
    suspended user's *already-issued, still-unexpired* access token must
    be rejected on their very next request, not merely blocked at their
    next login/refresh.
    """
    admin = await _make_admin(db_session)
    target = await make_user(db_session)
    target_headers = auth_cookie_headers(target.id)

    pre_suspend = await client.get("/api/v1/users/me", headers=target_headers)
    assert pre_suspend.status_code == 200

    await client.post(
        f"/api/v1/admin/users/{target.id}/suspend",
        json={"reason": "policy violation"},
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    post_suspend = await client.get("/api/v1/users/me", headers=target_headers)
    assert post_suspend.status_code == 403
    assert post_suspend.json()["error"]["code"] == "account_suspended"


# --- POST /admin/users/{id}/unsuspend ---


async def test_unsuspend_user_returns_the_documented_shape_and_restores_access(
    client, db_session
):
    admin = await _make_admin(db_session)
    target = await make_user(db_session)
    target.status = "suspended"
    await db_session.flush()

    response = await client.post(
        f"/api/v1/admin/users/{target.id}/unsuspend",
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 200
    assert response.json() == {"id": str(target.id), "status": "active"}

    now_works = await client.get(
        "/api/v1/users/me", headers=auth_cookie_headers(target.id)
    )
    assert now_works.status_code == 200


async def test_unsuspend_user_writes_an_audit_log_row(client, db_session):
    admin = await _make_admin(db_session)
    target = await make_user(db_session)
    target.status = "suspended"
    await db_session.flush()

    await client.post(
        f"/api/v1/admin/users/{target.id}/unsuspend",
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    logs = await AuditLogRepository(db_session).list_for_actor(admin.id)
    assert any(log.action == "admin_unsuspend_user" for log in logs)


async def test_unsuspend_user_404s_for_an_unknown_id(client, db_session):
    admin = await _make_admin(db_session)

    response = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/unsuspend",
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_unsuspend_user_409s_when_not_currently_suspended(client, db_session):
    admin = await _make_admin(db_session)
    target = await make_user(db_session)  # status defaults to "active"

    response = await client.post(
        f"/api/v1/admin/users/{target.id}/unsuspend",
        headers=auth_cookie_headers(admin.id, role="admin"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_suspended"
