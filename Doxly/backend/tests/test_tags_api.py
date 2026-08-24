"""tasks/remediation-plan.md R2 — FR-DOC-006 (/tags)."""

import uuid

from tests.conftest import auth_cookie_headers, make_user


async def test_create_and_list_tag(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/tags",
        json={"name": "Work", "color": "#ff0000"},
        headers=auth_cookie_headers(user.id),
    )
    assert create.status_code == 201
    assert create.json()["name"] == "Work"
    assert create.json()["color"] == "#ff0000"

    listing = await client.get("/api/v1/tags", headers=auth_cookie_headers(user.id))
    assert listing.status_code == 200
    assert listing.json() == {"items": [create.json()]}


async def test_create_duplicate_tag_name_returns_409(client, db_session):
    user = await make_user(db_session)
    await client.post(
        "/api/v1/tags", json={"name": "Work"}, headers=auth_cookie_headers(user.id)
    )

    response = await client.post(
        "/api/v1/tags", json={"name": "Work"}, headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tag_already_exists"


async def test_create_tag_empty_name_rejected(client, db_session):
    user = await make_user(db_session)
    response = await client.post(
        "/api/v1/tags", json={"name": ""}, headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_same_tag_name_allowed_for_different_users(client, db_session):
    """UNIQUE(user_id, name) — the same tag name is not globally unique."""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    a = await client.post(
        "/api/v1/tags", json={"name": "Work"}, headers=auth_cookie_headers(user_a.id)
    )
    b = await client.post(
        "/api/v1/tags", json={"name": "Work"}, headers=auth_cookie_headers(user_b.id)
    )
    assert a.status_code == 201
    assert b.status_code == 201


async def test_list_tags_scoped_to_owner(client, db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await client.post(
        "/api/v1/tags", json={"name": "A-tag"}, headers=auth_cookie_headers(user_a.id)
    )
    await client.post(
        "/api/v1/tags", json={"name": "B-tag"}, headers=auth_cookie_headers(user_b.id)
    )

    response = await client.get("/api/v1/tags", headers=auth_cookie_headers(user_a.id))
    names = [t["name"] for t in response.json()["items"]]
    assert names == ["A-tag"]


async def test_delete_tag(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/tags", json={"name": "Temp"}, headers=auth_cookie_headers(user.id)
    )
    tag_id = create.json()["id"]

    response = await client.delete(
        f"/api/v1/tags/{tag_id}", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 204

    listing = await client.get("/api/v1/tags", headers=auth_cookie_headers(user.id))
    assert listing.json()["items"] == []


async def test_delete_tag_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    create = await client.post(
        "/api/v1/tags", json={"name": "Mine"}, headers=auth_cookie_headers(owner.id)
    )
    tag_id = create.json()["id"]

    response = await client.delete(
        f"/api/v1/tags/{tag_id}", headers=auth_cookie_headers(attacker.id)
    )
    assert response.status_code == 404

    still_there = await client.get(
        "/api/v1/tags", headers=auth_cookie_headers(owner.id)
    )
    assert len(still_there.json()["items"]) == 1


async def test_delete_unknown_tag_returns_404(client, db_session):
    user = await make_user(db_session)
    response = await client.delete(
        f"/api/v1/tags/{uuid.uuid4()}", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 404


async def test_list_tags_without_cookie_returns_401(client):
    response = await client.get("/api/v1/tags")
    assert response.status_code == 401
