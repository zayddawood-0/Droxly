"""
decisions.md OQ-04 (resolved to Cloudflare R2) — R2StorageProvider tests.
Mirrors test_llm_provider.py's pattern (monkeypatch settings for factory
behavior; monkeypatch the provider's own low-level dependency — here
`_client`, boto3's S3 client — rather than the HTTP wire layer, since
`R2StorageProvider` already encapsulates that boundary itself, same
reasoning as AnthropicLLMProvider's `_call` in test_llm_provider.py).
"""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import app.core.storage as storage_module
from app.core.config import settings
from app.core.storage import (
    LocalFilesystemStorageProvider,
    R2StorageProvider,
    get_storage_provider,
)


@pytest.fixture(autouse=True)
def _reset_provider_singleton(monkeypatch):
    # get_storage_provider() caches a module-level singleton across calls
    # (docstring: local-storage router and callers must agree on one
    # instance) — each test needs a clean slate regardless of what a prior
    # test configured.
    monkeypatch.setattr(storage_module, "_provider_singleton", None)


def _r2_provider() -> R2StorageProvider:
    return R2StorageProvider(
        endpoint_url="https://test-account.r2.cloudflarestorage.com",
        bucket_name="doxly-test",
        access_key_id="test-key-id",
        secret_access_key="test-secret",
        presigned_url_expires_in_seconds=900,
    )


# --- get_storage_provider() factory behavior ---


def test_get_storage_provider_defaults_to_local(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "local")
    assert isinstance(get_storage_provider(), LocalFilesystemStorageProvider)


def test_get_storage_provider_rejects_unknown_value(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "vercel_blob")
    with pytest.raises(RuntimeError):
        get_storage_provider()


def test_get_storage_provider_r2_requires_all_four_settings(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "r2")
    monkeypatch.setattr(settings, "storage_endpoint_url", None)
    monkeypatch.setattr(settings, "storage_bucket_name", "doxly-test")
    monkeypatch.setattr(settings, "storage_access_key_id", "key")
    monkeypatch.setattr(settings, "storage_secret_access_key", "secret")
    with pytest.raises(RuntimeError, match="STORAGE_ENDPOINT_URL"):
        get_storage_provider()


def test_get_storage_provider_returns_r2_when_fully_configured(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "r2")
    monkeypatch.setattr(
        settings, "storage_endpoint_url", "https://acct.r2.cloudflarestorage.com"
    )
    monkeypatch.setattr(settings, "storage_bucket_name", "doxly-test")
    monkeypatch.setattr(settings, "storage_access_key_id", "key")
    monkeypatch.setattr(settings, "storage_secret_access_key", "secret")
    assert isinstance(get_storage_provider(), R2StorageProvider)


# --- R2StorageProvider behavior (boto3 client mocked — no real network) ---


async def test_generate_presigned_upload_returns_a_put_url():
    provider = _r2_provider()
    provider._client = MagicMock()
    provider._client.generate_presigned_url.return_value = "https://r2.example/put-url"

    result = await provider.generate_presigned_upload(
        "documents/x/y", mime_type="application/pdf"
    )

    assert result.upload_url == "https://r2.example/put-url"
    assert result.upload_method == "PUT"
    assert result.upload_headers == {"Content-Type": "application/pdf"}
    assert result.expires_in == 900
    provider._client.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "doxly-test",
            "Key": "documents/x/y",
            "ContentType": "application/pdf",
        },
        ExpiresIn=900,
    )


async def test_generate_presigned_download_returns_a_get_url():
    provider = _r2_provider()
    provider._client = MagicMock()
    provider._client.generate_presigned_url.return_value = "https://r2.example/get-url"

    result = await provider.generate_presigned_download("documents/x/y")

    assert result.download_url == "https://r2.example/get-url"
    assert result.expires_in == 900


async def test_get_object_metadata_returns_none_when_key_missing():
    provider = _r2_provider()
    provider._client = MagicMock()
    provider._client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )

    assert await provider.get_object_metadata("documents/missing") is None


async def test_get_object_metadata_propagates_unexpected_errors():
    provider = _r2_provider()
    provider._client = MagicMock()
    provider._client.head_object.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject"
    )

    with pytest.raises(ClientError):
        await provider.get_object_metadata("documents/forbidden")


async def test_get_object_metadata_returns_size_and_header_bytes():
    provider = _r2_provider()
    provider._client = MagicMock()
    provider._client.head_object.return_value = {"ContentLength": 1234}
    body = MagicMock()
    body.read.return_value = b"%PDF-1.4"
    provider._client.get_object.return_value = {"Body": body}

    metadata = await provider.get_object_metadata("documents/x/y")

    assert metadata is not None
    assert metadata.size_bytes == 1234
    assert metadata.header_bytes == b"%PDF-1.4"
    provider._client.get_object.assert_called_once_with(
        Bucket="doxly-test", Key="documents/x/y", Range="bytes=0-15"
    )


async def test_read_object_bytes_returns_the_full_body():
    provider = _r2_provider()
    provider._client = MagicMock()
    body = MagicMock()
    body.read.return_value = b"raw bytes"
    provider._client.get_object.return_value = {"Body": body}

    assert await provider.read_object_bytes("documents/x/y") == b"raw bytes"


async def test_read_object_text_decodes_utf8():
    provider = _r2_provider()
    provider._client = MagicMock()
    body = MagicMock()
    body.read.return_value = b"hello, doxly"
    provider._client.get_object.return_value = {"Body": body}

    assert await provider.read_object_text("documents/x/y") == "hello, doxly"


async def test_delete_object_calls_the_client():
    provider = _r2_provider()
    provider._client = MagicMock()

    await provider.delete_object("documents/x/y")

    provider._client.delete_object.assert_called_once_with(
        Bucket="doxly-test", Key="documents/x/y"
    )
