"""
tasks/remediation-plan.md R2 — a genuine persistence test for the upload
flow, deliberately NOT using the `client`/`db_session` fixtures (mirrors
R1's tests/test_db_session_commit.py, added after that task found
get_db_session's commit/rollback bugs the shared-transaction test fixture
structurally cannot catch). Confirms a presigned upload + confirm, driven
across genuinely separate requests/sessions, is actually visible afterward
— not just visible within one shared, never-committed test transaction.
"""

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.csrf import verify_csrf
from app.core.database import engine
from app.core.rate_limit import rate_limit_ai, rate_limit_general
from app.main import app

PDF_BYTES = b"%PDF-1.4\n%real persistence test content\n"


async def test_uploaded_document_persists_across_separate_requests():
    app.dependency_overrides[verify_csrf] = lambda: None
    app.dependency_overrides[rate_limit_general] = lambda: None
    app.dependency_overrides[rate_limit_ai] = lambda: None

    email = "doc-persistence-regression@example.com"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            register = await ac.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "correcthorse9",
                    "display_name": "Persistence Test",
                },
            )
            assert register.status_code == 201
            login = await ac.post(
                "/api/v1/auth/login", json={"email": email, "password": "correcthorse9"}
            )
            assert login.status_code == 200
            cookie_header = f"access_token={login.cookies['access_token']}"

            presign = await ac.post(
                "/api/v1/documents/presign",
                json={
                    "file_name": "persist.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": len(PDF_BYTES),
                },
                headers={"Cookie": cookie_header},
            )
            assert presign.status_code == 201
            document_id = presign.json()["document_id"]
            from urllib.parse import urlparse

            upload_path = urlparse(presign.json()["upload_url"]).path
            put = await ac.put(upload_path, content=PDF_BYTES)
            assert put.status_code == 200

            confirm = await ac.post(
                f"/api/v1/documents/{document_id}/confirm",
                headers={"Cookie": cookie_header},
            )
            assert confirm.status_code == 202

            # A genuinely SEPARATE request — its own AsyncSession from
            # async_session_factory() — must still see the confirmed
            # document. Before R1's get_db_session commit fix, this is
            # exactly the shape of bug that silently rolled everything
            # back on session close.
            detail = await ac.get(
                f"/api/v1/documents/{document_id}", headers={"Cookie": cookie_header}
            )
            assert detail.status_code == 200
            body = detail.json()
            assert body["file_name"] == "persist.pdf"
            assert body["size_bytes"] == len(PDF_BYTES)
            assert len(body["checksum_sha256"]) == 64

            listing = await ac.get(
                "/api/v1/documents", headers={"Cookie": cookie_header}
            )
            assert listing.json()["total"] == 1
    finally:
        app.dependency_overrides.pop(verify_csrf, None)
        app.dependency_overrides.pop(rate_limit_general, None)
        app.dependency_overrides.pop(rate_limit_ai, None)
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "DELETE FROM documents WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :email)"
                ),
                {"email": email},
            )
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
