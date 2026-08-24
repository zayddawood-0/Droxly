"""
tasks/remediation-plan.md R2 — object storage abstraction (decisions.md
ADR-009: StorageProvider interface, provider choice open per OQ-04).
Mirrors the LLMProvider/EmbeddingProvider/EmailProvider "real ABC + a
working local/fake default" pattern already established in this codebase.
No implementation existed before this task — confirmed by search before
writing this file. Documented as decisions.md ADR-022.
"""

import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


@dataclass
class PresignedUpload:
    upload_url: str
    upload_method: str
    upload_headers: dict[str, str]
    expires_in: int


@dataclass
class PresignedDownload:
    download_url: str
    expires_in: int


@dataclass
class ObjectMetadata:
    size_bytes: int
    header_bytes: bytes  # first few bytes, for magic-byte sniffing (security.md §5)


def generate_storage_key(user_id: uuid.UUID) -> str:
    """
    security.md §5 — "every stored object's storage_key is a generated,
    opaque identifier ... never derived from the user-supplied file_name."
    Namespaced by user_id as a path-like prefix purely for operational
    tidiness (browsing a bucket by owner) — the actual security property
    (non-guessable, no path traversal) comes entirely from the random
    suffix, not from this structure.
    """
    return f"documents/{user_id}/{uuid.uuid4()}-{secrets.token_urlsafe(8)}"


class StorageProvider(ABC):
    @abstractmethod
    async def generate_presigned_upload(
        self, key: str, *, mime_type: str
    ) -> PresignedUpload: ...

    @abstractmethod
    async def generate_presigned_download(self, key: str) -> PresignedDownload: ...

    @abstractmethod
    async def get_object_metadata(self, key: str) -> ObjectMetadata | None:
        """None if the object doesn't exist (e.g. the browser never
        completed the PUT, or the presign window expired without one)."""

    @abstractmethod
    async def read_object_text(self, key: str) -> str:
        """Reads the full object as UTF-8 text — used only by R2's own
        confirm-time text-decodability check for TXT/CSV and, until R3's
        real parsing pipeline exists, is NOT how document content
        eventually reaches document_chunks (that's the worker's job)."""

    @abstractmethod
    async def delete_object(self, key: str) -> None: ...


class LocalFilesystemStorageProvider(StorageProvider):
    """
    The active default until real cloud storage credentials are configured
    (decisions.md ADR-022) — a real, working implementation (writes actual
    bytes to local disk), not a mock. "Presigned" upload/download URLs
    point at a small local-only receiving endpoint
    (api/v1/routers/local_storage.py, mounted only when
    settings.storage_provider == "local") that stands in for Vercel
    Blob/S3's own presigned-URL mechanism in dev/test — FastAPI's
    /documents endpoints themselves still never touch file bytes directly,
    preserving ADR-009's actual architectural property.
    """

    def __init__(self, base_dir: str, base_url: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")

    def _path_for(self, key: str) -> Path:
        # `key` is always this module's own generate_storage_key() output
        # (never client-supplied) — safe to join directly.
        path = self._base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def generate_presigned_upload(
        self, key: str, *, mime_type: str
    ) -> PresignedUpload:
        return PresignedUpload(
            upload_url=f"{self._base_url}/internal/local-storage/{key}",
            upload_method="PUT",
            upload_headers={"Content-Type": mime_type},
            expires_in=settings.storage_presigned_url_expires_in_seconds,
        )

    async def generate_presigned_download(self, key: str) -> PresignedDownload:
        return PresignedDownload(
            download_url=f"{self._base_url}/internal/local-storage/{key}",
            expires_in=settings.storage_presigned_url_expires_in_seconds,
        )

    async def get_object_metadata(self, key: str) -> ObjectMetadata | None:
        path = self._path_for(key)
        if not path.is_file():
            return None
        size_bytes = path.stat().st_size
        with path.open("rb") as f:
            header_bytes = f.read(16)
        return ObjectMetadata(size_bytes=size_bytes, header_bytes=header_bytes)

    async def read_object_text(self, key: str) -> str:
        return self._path_for(key).read_text(encoding="utf-8")

    async def delete_object(self, key: str) -> None:
        path = self._path_for(key)
        path.unlink(missing_ok=True)

    # --- Local-provider-only methods (not part of the StorageProvider ABC:
    # a real cloud provider never receives bytes through backend code at
    # all — the browser talks to it directly). Used exclusively by
    # api/v1/routers/local_storage.py, the dev/test stand-in receiving
    # endpoint for this provider's own presigned URLs, and by tests that
    # need to seed/inspect local-storage objects directly. ---

    def write_object(self, key: str, data: bytes) -> None:
        self._path_for(key).write_bytes(data)

    def read_object_bytes(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()


_provider_singleton: StorageProvider | None = None


def get_storage_provider() -> StorageProvider:
    """
    A module-level singleton (unlike get_email_provider's per-call
    construction) because LocalFilesystemStorageProvider's local-storage
    router (mounted once, at app startup) and this function's callers must
    agree on the same base directory for the whole process lifetime — a
    fresh instance per call would still work correctly (same settings),
    but the singleton avoids redundant directory-existence checks per
    request.
    """
    global _provider_singleton
    if _provider_singleton is None:
        _provider_singleton = LocalFilesystemStorageProvider(
            base_dir=settings.storage_local_dir,
            base_url=settings.backend_public_base_url,
        )
    return _provider_singleton
