"""
tasks/remediation-plan.md R1 §4.3 — require_admin has no route consumer
yet (R10/Admin Integration is the first), so it's tested directly against
a minimal probe app rather than through a real router, mirroring
test_csrf.py's pattern for the same reason.
"""

import uuid

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import require_admin
from app.core.security import create_access_token
from app.errors import DoxlyError
from app.main import doxly_error_handler


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DoxlyError, doxly_error_handler)

    @app.get("/admin-only")
    async def admin_only(_: object = Depends(require_admin)) -> dict:
        return {"ok": True}

    return app


@pytest.fixture
async def admin_probe_client():
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_admin_role_is_allowed(admin_probe_client):
    token = create_access_token(uuid.uuid4(), "admin")
    response = await admin_probe_client.get(
        "/admin-only", headers={"Cookie": f"access_token={token}"}
    )
    assert response.status_code == 200


async def test_non_admin_role_gets_403(admin_probe_client):
    token = create_access_token(uuid.uuid4(), "user")
    response = await admin_probe_client.get(
        "/admin-only", headers={"Cookie": f"access_token={token}"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_unauthenticated_gets_401_not_403(admin_probe_client):
    """api.md §0.4 — 401 for no/invalid token, distinct from 403's
    valid-token-wrong-role case; require_admin must not conflate them."""
    response = await admin_probe_client.get("/admin-only")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
