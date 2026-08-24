"""
R1 remediation, audit finding S1 (CRITICAL) — verifies the api.md §0.5
error envelope applies to Pydantic 422s globally, across more than one
router, not just the one endpoint the original bug happened to be found on.
"""

import uuid

from tests.conftest import auth_cookie_headers


async def test_login_invalid_email_format_returns_envelope(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": "whatever12"}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "request_id" in error
    assert "email" in error["fields"]


async def test_users_me_patch_empty_display_name_returns_envelope(client):
    """A second endpoint, a second router (users, not auth) — proves the
    handler is global (registered once in main.py), not copy-pasted per
    router."""
    user_id = uuid.uuid4()
    response = await client.patch(
        "/api/v1/users/me",
        json={"display_name": ""},
        headers=auth_cookie_headers(user_id),
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "request_id" in error
    assert "display_name" in error["fields"]


async def test_validation_error_response_id_is_unique_per_request(client):
    """request_id correlates one specific failed request — two separate
    422s must not share the same id."""
    first = await client.post(
        "/api/v1/auth/login", json={"email": "bad", "password": "x"}
    )
    second = await client.post(
        "/api/v1/auth/login", json={"email": "bad", "password": "x"}
    )
    assert first.json()["error"]["request_id"] != second.json()["error"]["request_id"]
