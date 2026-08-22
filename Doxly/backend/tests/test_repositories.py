import uuid

from app.models import User
from app.repositories.document_repository import DocumentRepository


async def _make_user(session, email: str | None = None) -> User:
    user = User(
        email=email or f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def test_repository_create_and_get_round_trip(db_session):
    user = await _make_user(db_session)
    repo = DocumentRepository(db_session)

    created = await repo.create(
        user.id,
        file_name="invoice.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=2048,
        checksum_sha256="b" * 64,
    )

    fetched = await repo.get(user.id, created.id)
    assert fetched is not None
    assert fetched.file_name == "invoice.pdf"


async def test_repository_cross_tenant_get_returns_none(db_session):
    """
    Mandatory cross-tenant isolation test (specs/testing.md §3.5,
    skills/database.md §10): User A must never be able to read User B's
    document through the repository layer, even by guessing the ID.
    """
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    repo = DocumentRepository(db_session)

    owned = await repo.create(
        owner.id,
        file_name="private.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="c" * 64,
    )

    leaked = await repo.get(other_user.id, owned.id)
    assert leaked is None


async def test_repository_list_excludes_other_users_rows(db_session):
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    repo = DocumentRepository(db_session)

    await repo.create(
        user_a.id,
        file_name="a.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1,
        checksum_sha256="d" * 64,
    )
    await repo.create(
        user_b.id,
        file_name="b.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1,
        checksum_sha256="e" * 64,
    )

    results = await repo.list(user_a.id)
    assert [doc.file_name for doc in results] == ["a.pdf"]


async def test_repository_delete_is_owner_scoped(db_session):
    """Deleting via another user's id must not remove the row (mirrors FR-DOC-005's 404-not-403 pattern at the data layer)."""
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    repo = DocumentRepository(db_session)

    doc = await repo.create(
        owner.id,
        file_name="keep-me.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1,
        checksum_sha256="f" * 64,
    )

    deleted = await repo.delete(other_user.id, doc.id)
    assert deleted is False

    still_there = await repo.get(owner.id, doc.id)
    assert still_there is not None
