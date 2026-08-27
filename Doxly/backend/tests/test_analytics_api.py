"""
api.md §9 (/analytics) — tasks/remediation-plan.md R9. Full HTTP-layer
contract tests: exact response shape, period validation, and the dedicated
cross-tenant suite remediation-plan.md §12.1 requires (an aggregate query
missing its WHERE user_id clause is exactly the bug class that category
exists to catch — not folded into general correctness tests).
"""

import uuid

from app.models import Document
from app.repositories.observability_repository import AiRequestRepository
from tests.conftest import auth_cookie_headers, make_user


async def _make_document(db_session, user_id, *, status: str = "ready") -> Document:
    document = Document(
        user_id=user_id,
        file_name="report.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status=status,
    )
    db_session.add(document)
    await db_session.flush()
    return document


async def _make_ai_request(db_session, user_id, *, operation: str):
    return await AiRequestRepository(db_session).create(
        user_id,
        operation=operation,
        provider="fake",
        model="fake-model",
        input_tokens=10,
        output_tokens=None,
        latency_ms=5,
        status="success",
        error_code=None,
    )


# --- Shape / validation ---


async def test_dashboard_returns_the_exact_documented_shape(client, db_session):
    user = await make_user(db_session)
    await _make_document(db_session, user.id, status="ready")
    await _make_ai_request(db_session, user.id, operation="chat")

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "documents_processed",
        "documents_over_time",
        "ai_requests",
        "ai_requests_over_time",
        "storage_used_bytes",
        "most_used_features",
    }
    assert body["documents_processed"] == 1
    assert body["ai_requests"] == 1
    assert isinstance(body["storage_used_bytes"], int)
    for point in body["documents_over_time"]:
        assert set(point.keys()) == {"date", "count"}
    for point in body["ai_requests_over_time"]:
        assert set(point.keys()) == {"date", "count"}
    for feature in body["most_used_features"]:
        assert set(feature.keys()) == {"feature", "count"}
    assert {"feature": "chat", "count": 1} in body["most_used_features"]


async def test_dashboard_defaults_to_30d_period(client, db_session):
    user = await make_user(db_session)

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["documents_over_time"]) == 31  # inclusive of today
    assert len(body["ai_requests_over_time"]) == 31


async def test_dashboard_accepts_7d_and_90d_periods(client, db_session):
    user = await make_user(db_session)

    for period, expected_days in (("7d", 8), ("90d", 91)):
        response = await client.get(
            "/api/v1/analytics/dashboard",
            params={"period": period},
            headers=auth_cookie_headers(user.id),
        )
        assert response.status_code == 200
        assert len(response.json()["documents_over_time"]) == expected_days


async def test_dashboard_422s_for_an_invalid_period(client, db_session):
    user = await make_user(db_session)

    response = await client.get(
        "/api/v1/analytics/dashboard",
        params={"period": "1y"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_dashboard_requires_auth(client, db_session):
    response = await client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_dashboard_zero_state_for_a_brand_new_user(client, db_session):
    user = await make_user(db_session)

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["documents_processed"] == 0
    assert body["ai_requests"] == 0
    assert body["storage_used_bytes"] == 0
    assert body["most_used_features"] == []
    assert all(p["count"] == 0 for p in body["documents_over_time"])


# --- Cross-tenant isolation (remediation-plan.md §12.1, mandatory dedicated suite) ---


async def test_document_counts_are_scoped_to_the_caller(client, db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _make_document(db_session, user_a.id, status="ready")
    for _ in range(5):
        await _make_document(db_session, user_b.id, status="ready")

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user_a.id)
    )

    assert response.status_code == 200
    assert response.json()["documents_processed"] == 1


async def test_storage_used_bytes_is_scoped_to_the_caller(client, db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    user_b.storage_used_bytes = 999_999_999
    await db_session.flush()

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user_a.id)
    )

    assert response.status_code == 200
    assert response.json()["storage_used_bytes"] == 0


async def test_ai_request_volume_is_scoped_to_the_caller(client, db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _make_ai_request(db_session, user_a.id, operation="chat")
    for op in ("chat", "extraction", "comparison", "summarization"):
        await _make_ai_request(db_session, user_b.id, operation=op)

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user_a.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_requests"] == 1
    assert body["most_used_features"] == [{"feature": "chat", "count": 1}]


async def test_time_filtered_metrics_stay_isolated_across_every_period(
    client, db_session
):
    """The same isolation holds under every supported date-range filter,
    not just the unfiltered default view (remediation-plan.md §12.1)."""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _make_ai_request(db_session, user_b.id, operation="chat")

    for period in ("7d", "30d", "90d"):
        response = await client.get(
            "/api/v1/analytics/dashboard",
            params={"period": period},
            headers=auth_cookie_headers(user_a.id),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ai_requests"] == 0
        assert body["most_used_features"] == []


async def test_most_used_features_never_aggregates_across_the_full_user_base(
    client, db_session
):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _make_ai_request(db_session, user_a.id, operation="extraction")
    for _ in range(10):
        await _make_ai_request(db_session, user_b.id, operation="chat")

    response = await client.get(
        "/api/v1/analytics/dashboard", headers=auth_cookie_headers(user_a.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["most_used_features"] == [{"feature": "extraction", "count": 1}]
