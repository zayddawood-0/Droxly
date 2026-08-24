"""tasks/remediation-plan.md R2 — repository-level tests (testing.md §3.2:
real test Postgres, never mocked) for the methods added this task."""

import uuid

from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
    DocumentTagRepository,
    TagRepository,
)
from tests.conftest import make_user


async def _make_document(repo: DocumentRepository, user_id, **overrides):
    fields = {
        "file_name": "a.pdf",
        "storage_key": str(uuid.uuid4()),
        "mime_type": "application/pdf",
        "size_bytes": 100,
        "checksum_sha256": "a" * 64,
    }
    fields.update(overrides)
    return await repo.create(user_id, **fields)


async def test_get_excludes_soft_deleted_documents(db_session):
    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    document = await _make_document(repo, user.id)

    await repo.soft_delete(user.id, document.id)

    assert await repo.get(user.id, document.id) is None


async def test_soft_delete_does_not_hard_delete_the_row(db_session):
    """The row survives soft-delete — only get()'s visibility changes,
    per FR-DOC-005's "soft-delete now, hard-delete via background job
    within the retention window.\" """
    from sqlalchemy import select

    from app.models import Document

    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    document = await _make_document(repo, user.id)
    await repo.soft_delete(user.id, document.id)

    result = await db_session.execute(
        select(Document).where(Document.id == document.id)
    )
    assert result.scalar_one_or_none() is not None


async def test_list_paginated_excludes_soft_deleted(db_session):
    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    kept = await _make_document(repo, user.id, file_name="kept.pdf")
    deleted = await _make_document(repo, user.id, file_name="deleted.pdf")
    await repo.soft_delete(user.id, deleted.id)

    items, total = await repo.list_paginated(user.id, limit=20, offset=0)
    assert total == 1
    assert items[0].id == kept.id


async def test_list_paginated_never_returns_another_users_documents(db_session):
    """testing.md §3.5."""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    repo = DocumentRepository(db_session)
    await _make_document(repo, user_a.id)
    await _make_document(repo, user_b.id)

    items, total = await repo.list_paginated(user_a.id, limit=20, offset=0)
    assert total == 1
    assert all(item.user_id == user_a.id for item in items)


async def test_count_for_user_excludes_soft_deleted(db_session):
    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    await _make_document(repo, user.id)
    deleted = await _make_document(repo, user.id)
    await repo.soft_delete(user.id, deleted.id)

    assert await repo.count_for_user(user.id) == 1


async def test_purge_for_user_removes_all_documents_and_returns_storage_keys(
    db_session,
):
    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    doc1 = await _make_document(repo, user.id, storage_key="key-1")
    doc2 = await _make_document(repo, user.id, storage_key="key-2")

    storage_keys = await repo.purge_for_user(user.id)

    assert sorted(storage_keys) == ["key-1", "key-2"]
    from sqlalchemy import select

    from app.models import Document

    result = await db_session.execute(
        select(Document).where(Document.id.in_([doc1.id, doc2.id]))
    )
    assert result.scalars().all() == []


async def test_purge_for_user_cascades_to_chunks(db_session):
    """database.md §3.4 — document_chunks ON DELETE CASCADE."""
    from sqlalchemy import select

    from app.models import DocumentChunk

    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    document = await _make_document(repo, user.id)
    await DocumentChunkRepository(db_session).bulk_create(
        user.id, document.id, [{"chunk_index": 0, "content": "hi", "token_count": 1}]
    )

    await repo.purge_for_user(user.id)

    result = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    assert result.scalars().all() == []


async def test_purge_for_user_does_not_touch_other_users_documents(db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    repo = DocumentRepository(db_session)
    await _make_document(repo, user_a.id)
    doc_b = await _make_document(repo, user_b.id)

    await repo.purge_for_user(user_a.id)

    assert await repo.get(user_b.id, doc_b.id) is not None


async def test_purge_for_user_empty_account_returns_empty_list(db_session):
    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    assert await repo.purge_for_user(user.id) == []


async def test_replace_tags_for_document_swaps_full_set(db_session):
    user = await make_user(db_session)
    doc_repo = DocumentRepository(db_session)
    tag_repo = TagRepository(db_session)
    doc_tag_repo = DocumentTagRepository(db_session)
    document = await _make_document(doc_repo, user.id)
    tag_a = await tag_repo.create(user.id, name="A", color=None)
    tag_b = await tag_repo.create(user.id, name="B", color=None)

    await doc_tag_repo.replace_for_document(document.id, [tag_a.id])
    assert await doc_tag_repo.list_tag_ids_for_document(document.id) == [tag_a.id]

    await doc_tag_repo.replace_for_document(document.id, [tag_b.id])
    assert await doc_tag_repo.list_tag_ids_for_document(document.id) == [tag_b.id]

    await doc_tag_repo.replace_for_document(document.id, [])
    assert await doc_tag_repo.list_tag_ids_for_document(document.id) == []


async def test_list_tags_for_documents_batches_correctly(db_session):
    user = await make_user(db_session)
    doc_repo = DocumentRepository(db_session)
    tag_repo = TagRepository(db_session)
    doc_tag_repo = DocumentTagRepository(db_session)
    doc1 = await _make_document(doc_repo, user.id, storage_key="k1")
    doc2 = await _make_document(doc_repo, user.id, storage_key="k2")
    tag = await tag_repo.create(user.id, name="Shared", color=None)
    await doc_tag_repo.add(doc1.id, tag.id)

    result = await doc_tag_repo.list_tags_for_documents([doc1.id, doc2.id])

    assert [t.id for t in result[doc1.id]] == [tag.id]
    assert result[doc2.id] == []


async def test_tag_get_by_name_scoped_to_owner(db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    tag_repo = TagRepository(db_session)
    await tag_repo.create(user_a.id, name="Shared", color=None)

    assert await tag_repo.get_by_name(user_a.id, "Shared") is not None
    assert await tag_repo.get_by_name(user_b.id, "Shared") is None
