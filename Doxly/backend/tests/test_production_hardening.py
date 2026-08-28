"""
tasks/remediation-plan.md R12 (Production Deployment Readiness) — CORS
(deployment.md §11), security headers (security.md §11.3, NFR-SEC-011),
request-ID correlation (observability.md §2.2) applied by
`request_context_middleware` (app/main.py) to every response, and the
storage-provider misconfiguration guard (core/storage.py).
"""

import pytest

from app.core import storage as storage_module
from app.core.config import settings


async def test_every_response_carries_the_baseline_security_headers(client):
    response = await client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


async def test_hsts_is_only_set_outside_local_environment(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "local")
    local_response = await client.get("/health")
    assert "Strict-Transport-Security" not in local_response.headers

    monkeypatch.setattr(settings, "environment", "production")
    prod_response = await client.get("/health")
    assert "Strict-Transport-Security" in prod_response.headers
    assert "max-age=" in prod_response.headers["Strict-Transport-Security"]


async def test_response_carries_an_x_request_id(client):
    response = await client.get("/health")
    assert response.headers["X-Request-ID"]


async def test_inbound_x_request_id_is_echoed_back(client):
    """observability.md §2.2 — a request_id the BFF already generated is
    reused, not silently replaced with a second one."""
    response = await client.get(
        "/health", headers={"X-Request-ID": "test-fixed-request-id-123"}
    )
    assert response.headers["X-Request-ID"] == "test-fixed-request-id-123"


async def test_error_response_request_id_matches_the_response_header(client):
    """The id in the JSON error envelope (api.md §0.5) must be the exact
    same id as the X-Request-ID response header for the same request --
    two independently-generated ids would defeat correlation entirely."""
    response = await client.get(
        "/api/v1/documents/not-a-real-uuid",
        headers={"X-Request-ID": "test-error-correlation-id"},
    )
    assert response.headers["X-Request-ID"] == "test-error-correlation-id"
    assert response.json()["error"]["request_id"] == "test-error-correlation-id"


async def test_cors_allows_the_configured_origin(client):
    response = await client.get(
        "/health", headers={"Origin": settings.cors_allowed_origins_list[0]}
    )
    assert (
        response.headers.get("access-control-allow-origin")
        == settings.cors_allowed_origins_list[0]
    )


async def test_cors_rejects_an_unconfigured_origin(client):
    response = await client.get(
        "/health", headers={"Origin": "https://attacker.example.com"}
    )
    assert "access-control-allow-origin" not in response.headers


def test_cors_allowed_origins_list_never_contains_a_wildcard_in_production():
    """deployment.md §11 — 'never a wildcard origin in production', and
    FastAPI's CORSMiddleware itself refuses `allow_origins=["*"]` combined
    with `allow_credentials=True` (raises at startup) -- this test asserts
    the actual configured default is a concrete origin, not a wildcard,
    independent of that library-level guard."""
    assert "*" not in settings.cors_allowed_origins_list


def test_get_storage_provider_raises_loudly_for_an_unimplemented_provider(
    monkeypatch,
):
    """
    decisions.md OQ-04 — no real cloud StorageProvider exists yet.
    get_storage_provider() must fail loudly for any STORAGE_PROVIDER value
    other than "local" rather than silently keeping local (ephemeral,
    per-container) storage in what a deployer believes is a real cloud
    config -- the exact silent-data-loss shape a multi-replica production
    deployment (deployment.md §3) would hit.
    """
    monkeypatch.setattr(storage_module, "_provider_singleton", None)
    monkeypatch.setattr(settings, "storage_provider", "s3")

    with pytest.raises(RuntimeError, match="STORAGE_PROVIDER"):
        storage_module.get_storage_provider()


def test_get_storage_provider_still_returns_local_by_default(monkeypatch):
    monkeypatch.setattr(storage_module, "_provider_singleton", None)
    monkeypatch.setattr(settings, "storage_provider", "local")

    provider = storage_module.get_storage_provider()

    assert isinstance(provider, storage_module.LocalFilesystemStorageProvider)
