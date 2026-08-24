"""
tasks/remediation-plan.md R1 §5.1 / R2 — FR-USER-002's document-owned half
of the account-deletion cascade: DELETE /users/me (immediate side effects)
and DocumentService.purge_account_data (the callable, tested hard-delete
mechanism — not yet wired to a scheduled job; see its own docstring for the
documented R3 gap).
"""

import uuid
from datetime import UTC, datetime, timedelta

from tests.conftest import auth_cookie_headers, make_user


async def test_delete_me_requires_matching_confirmation_email(client, db_session):
    user = await make_user(db_session, email="deleteme@example.com")
    response = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"confirmation_email": "wrong@example.com"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "confirmation_mismatch"


async def test_delete_me_success_sets_pending_deletion_and_revokes_sessions(
    client, db_session
):
    from app.repositories.user_repository import RefreshTokenRepository, UserRepository

    user = await make_user(db_session, email="deleteme2@example.com")
    await RefreshTokenRepository(db_session).create(
        user.id,
        token_hash="irrelevant",
        device_label="Test Device",
        ip_address=None,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    response = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"confirmation_email": "deleteme2@example.com"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 202
    assert response.json() == {
        "status": "pending_deletion",
        "purge_scheduled_after_days": 30,
    }

    refreshed = await UserRepository(db_session).get_by_id(user.id)
    assert refreshed.status == "pending_deletion"

    active_sessions = await RefreshTokenRepository(db_session).list_active_for_user(
        user.id
    )
    assert active_sessions == []


async def test_delete_me_without_cookie_returns_401(client):
    response = await client.request(
        "DELETE", "/api/v1/users/me", json={"confirmation_email": "x@example.com"}
    )
    assert response.status_code == 401


async def test_purge_account_data_removes_documents_and_storage_objects(db_session):
    from app.core.storage import LocalFilesystemStorageProvider, get_storage_provider
    from app.repositories.document_repository import (
        DocumentChunkRepository,
        DocumentRepository,
        DocumentTagRepository,
        TagRepository,
    )
    from app.repositories.user_repository import UserRepository
    from app.services.document_service import DocumentService

    user = await make_user(db_session)
    storage_provider = get_storage_provider()
    assert isinstance(storage_provider, LocalFilesystemStorageProvider)
    storage_key = f"documents/{user.id}/{uuid.uuid4()}"
    storage_provider.write_object(storage_key, b"some file bytes")

    document_repo = DocumentRepository(db_session)
    await document_repo.create(
        user.id,
        file_name="a.pdf",
        storage_key=storage_key,
        mime_type="application/pdf",
        size_bytes=15,
        checksum_sha256="a" * 64,
    )

    service = DocumentService(
        document_repo,
        DocumentChunkRepository(db_session),
        TagRepository(db_session),
        DocumentTagRepository(db_session),
        UserRepository(db_session),
        storage_provider,
    )

    purged_count = await service.purge_account_data(user.id)

    assert purged_count == 1
    assert await document_repo.count_for_user(user.id) == 0
    assert await storage_provider.get_object_metadata(storage_key) is None


async def test_purge_account_data_empty_account_returns_zero(db_session):
    from app.core.storage import get_storage_provider
    from app.repositories.document_repository import (
        DocumentChunkRepository,
        DocumentRepository,
        DocumentTagRepository,
        TagRepository,
    )
    from app.repositories.user_repository import UserRepository
    from app.services.document_service import DocumentService

    user = await make_user(db_session)
    service = DocumentService(
        DocumentRepository(db_session),
        DocumentChunkRepository(db_session),
        TagRepository(db_session),
        DocumentTagRepository(db_session),
        UserRepository(db_session),
        get_storage_provider(),
    )

    assert await service.purge_account_data(user.id) == 0
