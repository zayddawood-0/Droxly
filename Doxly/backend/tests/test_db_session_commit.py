"""
Regression test for a critical bug found while verifying the R1
remediation pass (audit findings S1-S7): app/core/database.py's
get_db_session never called session.commit(), so nothing written through
it actually persisted outside of tests/conftest.py's test-transaction
override — every OTHER test in this suite routes through that override and
so could not have caught this. This file deliberately does NOT use the
`client`/`db_session` fixtures — it exercises the real, production
get_db_session dependency end-to-end, the only way to prove data survives
across separate requests/sessions rather than merely being visible within
one shared test transaction.
"""

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.csrf import verify_csrf
from app.core.database import engine
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.main import app


async def test_registered_user_persists_across_separate_requests():
    """The real regression: register (request 1, its own DB session) then
    log in with the same credentials (request 2, a DIFFERENT DB session).
    Before the fix, request 1's INSERT was silently rolled back when its
    session closed, so request 2 always saw no such user."""
    # Only CSRF/rate-limit are overridden (pure test-harness convenience,
    # unrelated to persistence) — get_db_session is deliberately NOT
    # overridden here, unlike every other test file's `client` fixture.
    app.dependency_overrides[verify_csrf] = lambda: None
    app.dependency_overrides[rate_limit_general] = lambda: None
    app.dependency_overrides[rate_limit_ai] = lambda: None

    email = "db-commit-regression@example.com"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            register = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "correcthorse9",
                    "display_name": "Commit Regression",
                },
            )
            assert register.status_code == 201

            # A genuinely separate request → a genuinely separate
            # AsyncSession from async_session_factory(). If the register
            # request's transaction was never committed, this 404s into
            # invalid_credentials exactly as it did before the fix.
            login = await ac.post(
                "/api/v1/auth/login", json={"email": email, "password": "correcthorse9"}
            )
            assert login.status_code == 200
            assert login.json()["email"] == email
    finally:
        app.dependency_overrides.pop(verify_csrf, None)
        app.dependency_overrides.pop(rate_limit_general, None)
        app.dependency_overrides.pop(rate_limit_ai, None)
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "DELETE FROM refresh_tokens WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :email)"
                ),
                {"email": email},
            )
            await conn.execute(
                text(
                    "DELETE FROM audit_logs WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :email)"
                ),
                {"email": email},
            )
            await conn.execute(
                text("DELETE FROM users WHERE email = :email"), {"email": email}
            )
            await conn.commit()


async def test_failed_request_does_not_persist_partial_writes():
    """The rollback half of the same fix: a request that raises after a
    flush() (duplicate-email registration, which flushes nothing new here
    but exercises the same session lifecycle) must not leave the session in
    a state that silently commits on close — verified by confirming the
    duplicate attempt correctly errors rather than corrupting the row.
    """
    app.dependency_overrides[verify_csrf] = lambda: None
    app.dependency_overrides[rate_limit_general] = lambda: None
    app.dependency_overrides[rate_limit_ai] = lambda: None

    email = "db-commit-rollback-regression@example.com"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            first = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "correcthorse9",
                    "display_name": "First",
                },
            )
            assert first.status_code == 201

            duplicate = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "correcthorse9",
                    "display_name": "Second",
                },
            )
            assert duplicate.status_code == 400

            login = await ac.post(
                "/api/v1/auth/login", json={"email": email, "password": "correcthorse9"}
            )
            assert login.status_code == 200
            assert login.json()["display_name"] == "First"
    finally:
        app.dependency_overrides.pop(verify_csrf, None)
        app.dependency_overrides.pop(rate_limit_general, None)
        app.dependency_overrides.pop(rate_limit_ai, None)
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "DELETE FROM refresh_tokens WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :email)"
                ),
                {"email": email},
            )
            await conn.execute(
                text(
                    "DELETE FROM audit_logs WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :email)"
                ),
                {"email": email},
            )
            await conn.execute(
                text("DELETE FROM users WHERE email = :email"), {"email": email}
            )
            await conn.commit()
