"""
tasks/remediation-plan.md R1 §4.1 — dedicated CSRF suite against the real,
unmocked verify_csrf dependency (contrast with tests/conftest.py's `client`
fixture, which overrides it to a no-op for every other test file).
"""

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    generate_csrf_token,
    verify_csrf,
)
from app.errors import DoxlyError
from app.main import doxly_error_handler


def _make_app() -> FastAPI:
    app = FastAPI()
    # Registers the same global handler app/main.py's real app uses, so this
    # minimal probe app produces the identical api.md §0.5 envelope/status
    # code a real router would — otherwise an uncaught CsrfError here would
    # surface as a generic 500, not the 403 the real app actually returns.
    app.add_exception_handler(DoxlyError, doxly_error_handler)

    @app.get("/probe")
    async def get_probe(_: None = Depends(verify_csrf)) -> dict:
        return {"ok": True}

    @app.post("/probe")
    async def post_probe(_: None = Depends(verify_csrf)) -> dict:
        return {"ok": True}

    return app


@pytest.fixture
async def csrf_client():
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_get_request_never_requires_csrf(csrf_client):
    """Safe methods are exempt (security.md §6.3's SameSite=Lax parallel)."""
    response = await csrf_client.get("/probe")
    assert response.status_code == 200


async def test_post_without_any_csrf_token_rejected(csrf_client):
    response = await csrf_client.post("/probe")
    assert response.status_code == 403


async def test_post_with_cookie_but_no_header_rejected(csrf_client):
    csrf_client.cookies.set(CSRF_COOKIE_NAME, generate_csrf_token())
    response = await csrf_client.post("/probe")
    assert response.status_code == 403


async def test_post_with_header_but_no_cookie_rejected(csrf_client):
    response = await csrf_client.post(
        "/probe", headers={CSRF_HEADER_NAME: generate_csrf_token()}
    )
    assert response.status_code == 403


async def test_post_with_mismatched_header_and_cookie_rejected(csrf_client):
    csrf_client.cookies.set(CSRF_COOKIE_NAME, generate_csrf_token())
    response = await csrf_client.post(
        "/probe", headers={CSRF_HEADER_NAME: generate_csrf_token()}
    )
    assert response.status_code == 403


async def test_post_with_matching_header_and_cookie_succeeds(csrf_client):
    token = generate_csrf_token()
    csrf_client.cookies.set(CSRF_COOKIE_NAME, token)
    response = await csrf_client.post("/probe", headers={CSRF_HEADER_NAME: token})
    assert response.status_code == 200


async def test_error_code_is_csrf_mismatch(csrf_client):
    response = await csrf_client.post("/probe")
    assert response.json()["error"]["code"] == "csrf_mismatch"
