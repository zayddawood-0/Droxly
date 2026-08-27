"""
tasks/remediation-plan.md R1 §4.3 — require_admin has no route consumer
yet until R10/Admin Integration's own router (test_admin_api.py covers
that real router directly), so it's tested here against a minimal probe
app, mirroring test_csrf.py's pattern for the same reason.

R10 note: get_current_user (which require_admin composes) now checks a
live users.status (FR-ADMIN-003 — see core/dependencies.py's own
docstring), so this probe app needs a real, DB-backed session/user rather
than a bare create_access_token() for an id with no users row — the
probe's dependency override mirrors conftest.py's own `client` fixture.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_admin
from app.core.security import create_access_token
from app.errors import DoxlyError
from app.main import doxly_error_handler
from tests.conftest import make_user


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DoxlyError, doxly_error_handler)

    @app.get("/admin-only")
    async def admin_only(_: object = Depends(require_admin)) -> dict:
        return {"ok": True}

    return app


@pytest.fixture
async def admin_probe_client(db_session: AsyncSession):
    app = _make_app()

    async def _override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_admin_role_is_allowed(admin_probe_client, db_session):
    user = await make_user(db_session)
    user.role = "admin"
    await db_session.flush()
    token = create_access_token(user.id, "admin")

    response = await admin_probe_client.get(
        "/admin-only", headers={"Cookie": f"access_token={token}"}
    )
    assert response.status_code == 200


async def test_non_admin_role_gets_403(admin_probe_client, db_session):
    user = await make_user(db_session)
    token = create_access_token(user.id, "user")

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
