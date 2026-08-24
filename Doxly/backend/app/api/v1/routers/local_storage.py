"""
Dev/test-only stand-in for the real object store's own presigned-URL
receiving endpoint (core/storage.py's LocalFilesystemStorageProvider).
Mounted only when settings.storage_provider == "local" (main.py) — never
present against a real cloud StorageProvider. Deliberately NOT under
/api/v1 — it isn't part of api.md's documented contract, and never will be;
a real deployment's presigned URL points directly at Vercel Blob/S3, not at
this backend at all (deployment.md §7). Not authenticated the same way
/documents/* is: the storage key itself — generated server-side,
non-guessable per security.md §5 — is the only credential a real presigned
URL carries either, so this matches that property rather than adding a
second, inconsistent auth layer just for local dev.
"""

from fastapi import APIRouter, Request, Response

from app.core.storage import LocalFilesystemStorageProvider, get_storage_provider
from app.errors import NotFoundError

router = APIRouter(prefix="/internal/local-storage", tags=["internal"])


def _local_provider() -> LocalFilesystemStorageProvider:
    provider = get_storage_provider()
    assert isinstance(provider, LocalFilesystemStorageProvider)
    return provider


@router.put("/{key:path}")
async def put_object(key: str, request: Request) -> Response:
    body = await request.body()
    _local_provider().write_object(key, body)
    return Response(status_code=200)


@router.get("/{key:path}")
async def get_object(key: str) -> Response:
    provider = _local_provider()
    metadata = await provider.get_object_metadata(key)
    if metadata is None:
        raise NotFoundError()
    return Response(
        content=provider.read_object_bytes(key), media_type="application/octet-stream"
    )
