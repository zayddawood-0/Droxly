"""
Final-release-audit remediation (finding #1, self-disclosed in
tasks/R3-document-processing.md as owned by R2) -- proves
DocumentRepository.confirm_if_unconfirmed is safe against a genuine
concurrent duplicate confirm, not just a sequential retry (the sequential
case -- a client retry after a dropped response -- is covered separately
in tests/test_documents_api.py at the HTTP layer, where the shared
client/db_session fixtures are the right tool).

Deliberately does NOT use the shared client/db_session fixtures here:
conftest.py's db_session fixture binds every session in a test to one
already-open connection/transaction (`session_factory = async_sessionmaker
(bind=conn, ...)`), so two "sessions" built from it never actually race --
there is only one physical connection and one open transaction, so a
second UPDATE from a "different session" bound to the same connection just
runs sequentially inside the same transaction, proving nothing about real
concurrent-request safety. This test uses real, independently-committing
sessions instead (`async_session_factory`, mirroring
test_r11_golden_path.py's established real-session pattern for exactly
this reason), with its own explicit setup/cleanup since nothing here rolls
back automatically like the shared fixtures do.
"""

import asyncio
import uuid

from sqlalchemy import delete

from app.core.database import async_session_factory, engine
from app.models import User
from app.repositories.document_repository import DocumentRepository


async def test_confirm_if_unconfirmed_is_safe_under_real_concurrent_duplicates():
    async with async_session_factory() as setup_session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            display_name="Concurrency Test",
            password_hash="not-a-real-hash",
        )
        setup_session.add(user)
        await setup_session.flush()
        user_id = user.id

        document = await DocumentRepository(setup_session).create(
            user_id,
            file_name="race.pdf",
            storage_key=str(uuid.uuid4()),
            mime_type="application/pdf",
            size_bytes=1000,
            # "" is presign_upload's real sentinel for "not yet
            # confirmed" -- matching production exactly, not a
            # test-only shortcut.
            checksum_sha256="",
        )
        document_id = document.id
        await setup_session.commit()

    try:

        async def _attempt() -> object:
            async with async_session_factory() as session:
                result = await DocumentRepository(session).confirm_if_unconfirmed(
                    user_id,
                    document_id,
                    checksum_sha256="b" * 64,
                    size_bytes=1000,
                )
                await session.commit()
                return result

        # Two genuinely concurrent attempts against the same document, each
        # on its own connection/transaction -- this is what actually
        # exercises Postgres's row-level serialization of the guarded
        # UPDATE, not just the Python-level logic.
        results = await asyncio.gather(_attempt(), _attempt())
        winners = [r for r in results if r is not None]
        losers = [r for r in results if r is None]

        assert len(winners) == 1, (
            f"expected exactly one concurrent confirm to win, got {len(winners)} "
            f"(results={results})"
        )
        assert len(losers) == 1

        async with async_session_factory() as verify_session:
            final = await DocumentRepository(verify_session).get(user_id, document_id)
            assert final is not None
            assert final.checksum_sha256 == "b" * 64
            assert final.size_bytes == 1000
    finally:
        async with async_session_factory() as cleanup_session:
            await cleanup_session.execute(delete(User).where(User.id == user_id))
            await cleanup_session.commit()
        await engine.dispose()
