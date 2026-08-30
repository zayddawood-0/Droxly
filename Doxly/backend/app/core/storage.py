"""
tasks/remediation-plan.md R2 — object storage abstraction (decisions.md
ADR-009: StorageProvider interface, provider choice open per OQ-04).
Mirrors the LLMProvider/EmbeddingProvider/EmailProvider "real ABC + a
working local/fake default" pattern already established in this codebase.
No implementation existed before this task — confirmed by search before
writing this file. Documented as decisions.md ADR-022.

R2StorageProvider (decisions.md OQ-04, resolved 2026-08-31 to Cloudflare
R2) added by the Railway pre-deployment closure pass.
"""

import asyncio
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

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
        confirm-time text-decodability check for TXT/CSV; not how document
        content reaches document_chunks (that's read_object_bytes + the
        R3 parsing pipeline's job)."""

    @abstractmethod
    async def read_object_bytes(self, key: str) -> bytes:
        """
        tasks/remediation-plan.md R3 — the raw bytes a `DocumentParser`
        parses (document-processing.md §7: "the worker downloads the raw
        file into ephemeral memory... for the duration of parsing only").
        Promoted from a `LocalFilesystemStorageProvider`-only helper (R2) to
        a real abstract method here: every future cloud provider needs this
        exact capability too, not just the local dev/test one.
        """

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

    async def read_object_bytes(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    async def delete_object(self, key: str) -> None:
        path = self._path_for(key)
        path.unlink(missing_ok=True)

    # --- Local-provider-only methods (not part of the StorageProvider ABC:
    # a real cloud provider never receives bytes through backend code at
    # all — the browser talks to it directly). Used exclusively by
    # api/v1/routers/local_storage.py, the dev/test stand-in receiving
    # endpoint for this provider's own presigned URLs, and by tests that
    # need to seed local-storage objects directly. ---

    def write_object(self, key: str, data: bytes) -> None:
        self._path_for(key).write_bytes(data)


class R2StorageProvider(StorageProvider):
    """
    Cloudflare R2 (decisions.md OQ-04, resolved) via R2's S3-compatible
    API — a plain `boto3` S3 client pointed at R2's account-specific
    endpoint, not a Cloudflare-specific SDK (none exists). Unlike
    LocalFilesystemStorageProvider, presigned URLs point directly at R2 —
    the browser talks to R2 itself, never through this backend
    (ADR-009's "uploads go directly from the browser to storage").

    boto3 is synchronous; every call below runs off the event loop via
    `asyncio.to_thread` per skills/backend.md §13's async-everywhere rule
    for I/O-bound work, rather than blocking it or pulling in aioboto3 as
    a second, less-maintained dependency.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        presigned_url_expires_in_seconds: int,
    ) -> None:
        self._bucket = bucket_name
        self._expires_in = presigned_url_expires_in_seconds
        # region_name="auto" is R2's own documented convention for its
        # S3-compatible API — R2 has no concept of AWS regions, but boto3's
        # SigV4 signing requires some value.
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    async def generate_presigned_upload(
        self, key: str, *, mime_type: str
    ) -> PresignedUpload:
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": mime_type},
            ExpiresIn=self._expires_in,
        )
        return PresignedUpload(
            upload_url=url,
            upload_method="PUT",
            upload_headers={"Content-Type": mime_type},
            expires_in=self._expires_in,
        )

    async def generate_presigned_download(self, key: str) -> PresignedDownload:
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._expires_in,
        )
        return PresignedDownload(download_url=url, expires_in=self._expires_in)

    async def get_object_metadata(self, key: str) -> ObjectMetadata | None:
        try:
            head = await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=key
            )
        except ClientError as exc:
            # R2 (like S3) reports a missing key as 404/NoSuchKey — the one
            # expected, non-exceptional case this method's contract handles
            # by returning None (e.g. the browser never completed the PUT).
            # Any other error code is a real failure and must propagate.
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                return None
            raise
        # Same 16-byte header window LocalFilesystemStorageProvider reads —
        # every DocumentParser.sniff_matches() implementation checks at
        # most a 5-byte magic-number prefix (document_service.py's
        # expected_prefix check), so a ranged GET avoids downloading the
        # full object just to confirm its type.
        ranged = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket, Key=key, Range="bytes=0-15"
        )
        header_bytes = ranged["Body"].read()
        return ObjectMetadata(
            size_bytes=head["ContentLength"], header_bytes=header_bytes
        )

    async def read_object_text(self, key: str) -> str:
        return (await self.read_object_bytes(key)).decode("utf-8")

    async def read_object_bytes(self, key: str) -> bytes:
        def _get() -> bytes:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
            body: bytes = obj["Body"].read()
            return body

        return await asyncio.to_thread(_get)

    async def delete_object(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=key
        )


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

    R12 (Production Deployment Readiness) fix: this used to construct
    `LocalFilesystemStorageProvider` unconditionally, never actually
    reading `settings.storage_provider` — so setting `STORAGE_PROVIDER` to
    anything else in a real deployment would silently keep using local
    container-filesystem storage rather than failing loudly. That's a
    materially worse failure mode here than the identical-looking
    `get_llm_provider()`/`get_embedding_provider()` "unrecognized value
    silently falls back to fake" pattern elsewhere in this codebase: an
    AI-provider fallback degrades a feature visibly (canned responses); a
    silent storage fallback in a multi-replica deployment
    (`deployment.md` §3's "minimum 2 replicas") means a file uploaded via
    one replica is invisible to (or lost when) a request lands on another
    — real, silent data loss, not a degraded-but-working feature. Any
    `STORAGE_PROVIDER` value other than "local"/"r2" still fails loudly at
    startup, matching `get_llm_provider`'s own "raise, don't silently
    substitute" behavior for a real-but-misconfigured case — the same
    property `R2StorageProvider`'s own missing-config check below extends
    to "r2" configured without its required settings.
    """
    if settings.storage_provider not in ("local", "r2"):
        raise RuntimeError(
            f"STORAGE_PROVIDER={settings.storage_provider!r} has no real "
            "implementation — set STORAGE_PROVIDER=local or "
            "STORAGE_PROVIDER=r2 (decisions.md OQ-04), or implement and "
            "register a real StorageProvider for this value before "
            "deploying with it."
        )
    global _provider_singleton
    if _provider_singleton is None:
        if settings.storage_provider == "r2":
            endpoint_url = settings.storage_endpoint_url
            bucket_name = settings.storage_bucket_name
            access_key_id = settings.storage_access_key_id
            secret_access_key = settings.storage_secret_access_key
            missing = [
                name
                for name, value in (
                    ("STORAGE_ENDPOINT_URL", endpoint_url),
                    ("STORAGE_BUCKET_NAME", bucket_name),
                    ("STORAGE_ACCESS_KEY_ID", access_key_id),
                    ("STORAGE_SECRET_ACCESS_KEY", secret_access_key),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "STORAGE_PROVIDER=r2 requires "
                    f"{', '.join(missing)} to be set — none of these have a "
                    "usable default (R2's endpoint is account-specific)."
                )
            assert endpoint_url and bucket_name and access_key_id and secret_access_key
            _provider_singleton = R2StorageProvider(
                endpoint_url=endpoint_url,
                bucket_name=bucket_name,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                presigned_url_expires_in_seconds=settings.storage_presigned_url_expires_in_seconds,
            )
        else:
            _provider_singleton = LocalFilesystemStorageProvider(
                base_dir=settings.storage_local_dir,
                base_url=settings.backend_public_base_url,
            )
    return _provider_singleton
