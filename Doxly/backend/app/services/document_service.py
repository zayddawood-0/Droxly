"""
tasks/remediation-plan.md R2 — FR-DOC-001..008. skills/backend.md §3:
business rules (quota checks, MIME validation, orchestration) live here,
never in the router or repository.
"""

import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.queue import enqueue_document_processing
from app.core.storage import (
    ObjectMetadata,
    PresignedDownload,
    PresignedUpload,
    StorageProvider,
    generate_storage_key,
)
from app.errors import (
    InvalidStatusError,
    NotFoundError,
    NotReadyError,
    QuotaExceededError,
    TagAlreadyExistsError,
    UnsupportedMimeTypeError,
    UploadMismatchError,
)
from app.models import Document, Tag
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
    DocumentTagRepository,
    TagRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.document import SUPPORTED_MIME_TYPES
from app.schemas.user import (
    DOCUMENT_QUOTA_FREE,
    DOCUMENT_QUOTA_PRO,
    STORAGE_QUOTA_BYTES_FREE,
    STORAGE_QUOTA_BYTES_PRO,
)

# decisions.md OQ-06 — 25 MB per file, MVP-wide (not yet plan-tiered).
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Magic-byte signatures for the confirm-time cross-check (security.md §5 /
# document-processing.md §1) — a fast, cheap "does the upload roughly match
# what was declared" gate. TXT/CSV have no reliable signature, so they're
# checked for size only here; R3's worker (not yet built) does the deeper,
# per-parser validation for every type at actual parse time.
_MAGIC_BYTES: dict[str, bytes] = {
    "application/pdf": b"%PDF-",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
}


class DocumentService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: DocumentChunkRepository,
        tag_repo: TagRepository,
        document_tag_repo: DocumentTagRepository,
        user_repo: UserRepository,
        storage_provider: StorageProvider,
    ) -> None:
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.tag_repo = tag_repo
        self.document_tag_repo = document_tag_repo
        self.user_repo = user_repo
        self.storage_provider = storage_provider

    # --- FR-DOC-001 ---

    async def presign_upload(
        self, user_id: uuid.UUID, *, file_name: str, mime_type: str, size_bytes: int
    ) -> tuple[Document, PresignedUpload]:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedMimeTypeError()

        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise QuotaExceededError("This file exceeds the maximum upload size.")

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError()
        is_pro = user.plan == "pro"

        storage_quota = STORAGE_QUOTA_BYTES_PRO if is_pro else STORAGE_QUOTA_BYTES_FREE
        if user.storage_used_bytes + size_bytes > storage_quota:
            raise QuotaExceededError()

        document_quota = DOCUMENT_QUOTA_PRO if is_pro else DOCUMENT_QUOTA_FREE
        if document_quota is not None:
            current_count = await self.document_repo.count_for_user(user_id)
            if current_count >= document_quota:
                raise QuotaExceededError("You've reached your document limit.")

        storage_key = generate_storage_key(user_id)
        document = await self.document_repo.create(
            user_id,
            file_name=file_name,
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum_sha256="",
            status="queued",
        )
        presigned = await self.storage_provider.generate_presigned_upload(
            storage_key, mime_type=mime_type
        )
        return document, presigned

    async def confirm_upload(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()

        metadata = await self.storage_provider.get_object_metadata(document.storage_key)
        if metadata is None:
            # api.md: "404 if ... the presign window expired without a
            # confirming upload" — no object ever arrived.
            raise NotFoundError()

        self._verify_upload_matches_declaration(document, metadata)

        checksum = await self._compute_checksum(document.storage_key)
        actual_size = metadata.size_bytes

        document.checksum_sha256 = checksum
        document.size_bytes = actual_size
        await self.document_repo.session.flush()

        # security.md §5 — size is server-authoritative; the user's usage
        # counter is incremented from the VERIFIED size, not the declared
        # one from presign.
        user = await self.user_repo.get_by_id(user_id)
        if user is not None:
            await self.user_repo.update(
                user_id, storage_used_bytes=user.storage_used_bytes + actual_size
            )

        # FR-PROC-001's trigger — R3's worker/queue infrastructure now
        # exists; enqueue_document_processing fails open (decisions.md
        # ADR-023) rather than turning a transient Redis outage into a
        # failed upload confirmation.
        enqueue_document_processing(user_id, document.id)
        return document

    def _verify_upload_matches_declaration(
        self, document: Document, metadata: ObjectMetadata
    ) -> None:
        if metadata.size_bytes != document.size_bytes:
            raise UploadMismatchError()
        expected_prefix = _MAGIC_BYTES.get(document.mime_type)
        if expected_prefix is not None and not metadata.header_bytes.startswith(
            expected_prefix
        ):
            raise UploadMismatchError()

    async def _compute_checksum(self, storage_key: str) -> str:
        # A real cloud provider would expose a server-side checksum/ETag
        # instead of requiring a full read; that optimization is deferred to
        # whichever future task adds a real cloud StorageProvider
        # (decisions.md ADR-022), not invented here. read_object_bytes is a
        # real StorageProvider ABC method (R3 — every provider needs it for
        # the parsing pipeline, not just this checksum computation).
        data = await self.storage_provider.read_object_bytes(storage_key)
        return hashlib.sha256(data).hexdigest()

    # --- FR-DOC-002 ---

    async def list_documents(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        status: str | None,
        tag_id: uuid.UUID | None,
        mime_type: str | None,
        sort: str,
    ) -> tuple[list[Document], dict[uuid.UUID, list[Tag]], int]:
        items, total = await self.document_repo.list_paginated(
            user_id,
            limit=limit,
            offset=offset,
            status=status,
            tag_id=tag_id,
            mime_type=mime_type,
            sort=sort,
        )
        tags_by_document = await self.document_tag_repo.list_tags_for_documents(
            [doc.id for doc in items]
        )
        return list(items), tags_by_document, total

    # --- FR-DOC-003 ---

    async def get_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, list[Tag]]:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        tag_ids = await self.document_tag_repo.list_tag_ids_for_document(document.id)
        tags = await self.tag_repo.get_many(user_id, tag_ids) if tag_ids else []
        return document, list(tags)

    async def get_download_url(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> PresignedDownload:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        return await self.storage_provider.generate_presigned_download(
            document.storage_key
        )

    async def get_content(self, user_id: uuid.UUID, document_id: uuid.UUID) -> dict:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        if document.status != "ready":
            raise NotReadyError()

        chunks = await self.chunk_repo.list_for_document(user_id, document_id)

        if document.mime_type == "text/plain":
            return {"text": "\n".join(chunk.content for chunk in chunks)}

        if document.mime_type == "text/csv":
            import csv
            import io

            # R3 (chunking.chunk_csv_rows) repeats the header row inside
            # EVERY chunk's stored content (rag.md §2), so — unlike the
            # other formats — chunks can't just be joined into one blob and
            # parsed once; each chunk is parsed independently and only its
            # data rows (not its repeated header) are accumulated.
            columns: list[str] = []
            rows: list[dict] = []
            for chunk in chunks:
                chunk_rows = list(csv.reader(io.StringIO(chunk.content)))
                if not chunk_rows:
                    continue
                if not columns:
                    columns = chunk_rows[0]
                rows.extend(
                    dict(zip(columns, row, strict=False)) for row in chunk_rows[1:]
                )
            return {"rows": rows, "columns": columns}

        # PDF/DOCX — page-oriented.
        pages: dict[int, list[str]] = {}
        for chunk in chunks:
            page_number = chunk.page_number or 1
            pages.setdefault(page_number, []).append(chunk.content)
        return {
            "pages": [
                {"page_number": page_number, "text": "\n".join(texts)}
                for page_number, texts in sorted(pages.items())
            ]
        }

    # --- FR-DOC-004 / FR-DOC-006 ---

    async def update_document(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        file_name: str | None,
        tag_ids: list[uuid.UUID] | None,
    ) -> tuple[Document, list[Tag]]:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()

        if file_name is not None:
            document.file_name = file_name

        if tag_ids is not None:
            owned_tags = await self.tag_repo.get_many(user_id, tag_ids)
            if len(owned_tags) != len(set(tag_ids)):
                raise NotFoundError()
            await self.document_tag_repo.replace_for_document(document_id, tag_ids)

        await self.document_repo.session.flush()
        return await self.get_document(user_id, document_id)

    # --- FR-DOC-005 ---

    async def delete_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()

        await self.document_repo.soft_delete(user_id, document_id)

        # The document stops counting against the user's visible quota the
        # moment it's deleted (a deliberate UX choice, not explicitly
        # mandated by any spec text) — the physical storage object/rows
        # are cleaned up later by the retention-window purge job (R1
        # §5.1), which does not touch storage_used_bytes again.
        user = await self.user_repo.get_by_id(user_id)
        if user is not None:
            new_total = max(0, user.storage_used_bytes - document.size_bytes)
            await self.user_repo.update(user_id, storage_used_bytes=new_total)

    # --- FR-PROC-005 (reprocess) ---

    # R3 remediation (tasks/R3-document-processing.md, decisions.md
    # ADR-026) — a worker crash mid-job leaves a document in one of these
    # non-terminal stages forever, with no exception ever raised for RQ's
    # own retry to act on. document-processing.md §5's status machine.
    _NON_TERMINAL_STATUSES = frozenset(
        {"queued", "extracting", "chunking", "embedding"}
    )

    def _is_stale_non_terminal(self, document: Document) -> bool:
        """
        api.md's reprocess entry (amended by this remediation): a document
        in a non-terminal stage for longer than
        `settings.document_processing_stale_threshold_seconds` is treated
        as reprocessable, the same as one already `failed` — `updated_at`
        is bumped by every real stage transition (`DocumentRepository.
        set_status`), so a stale `updated_at` reliably means nothing has
        touched this document in that window, not merely that it hasn't
        finished yet (see ADR-026 for the threshold's derivation and the
        residual risk of a very large, still-legitimately-running job).
        """
        if document.status not in self._NON_TERMINAL_STATUSES:
            return False
        threshold = timedelta(
            seconds=settings.document_processing_stale_threshold_seconds
        )
        return datetime.now(UTC) - document.updated_at > threshold

    async def reprocess_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        if document.status != "failed" and not self._is_stale_non_terminal(document):
            raise InvalidStatusError()

        # "prior chunks/embeddings for the document are discarded and
        # replaced, not appended" (api.md).
        await self.chunk_repo.delete_for_document(user_id, document_id)

        updated = await self.document_repo.set_status(
            user_id, document_id, status="queued", processing_error=None
        )
        assert updated is not None
        enqueue_document_processing(user_id, document_id)
        return updated

    # --- FR-DOC-008 ---

    async def get_status(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self.document_repo.get(user_id, document_id)
        if document is None:
            raise NotFoundError()
        return document

    # --- FR-DOC-007 (bulk, P2) ---

    async def bulk_action(
        self,
        user_id: uuid.UUID,
        *,
        document_ids: Sequence[uuid.UUID],
        action: str,
        tag_ids: list[uuid.UUID] | None,
    ) -> tuple[int, int]:
        owned_tag_ids: list[uuid.UUID] = []
        if action == "tag":
            assert tag_ids is not None
            owned_tags = await self.tag_repo.get_many(user_id, tag_ids)
            if len(owned_tags) != len(set(tag_ids)):
                raise NotFoundError()
            owned_tag_ids = tag_ids

        affected = 0
        skipped = 0
        for document_id in document_ids:
            document = await self.document_repo.get(user_id, document_id)
            if document is None:
                # api.md: "silently excluded ... counted in skipped, never
                # surfaced as a partial error (avoids existence leakage)."
                skipped += 1
                continue

            if action == "delete":
                await self.document_repo.soft_delete(user_id, document_id)
            else:
                for tag_id in owned_tag_ids:
                    await self.document_tag_repo.add(document_id, tag_id)
            affected += 1

        return affected, skipped

    # --- Tags (FR-DOC-006) ---

    async def list_tags(self, user_id: uuid.UUID) -> Sequence[Tag]:
        return await self.tag_repo.list(user_id, limit=1000, offset=0)

    async def create_tag(
        self, user_id: uuid.UUID, *, name: str, color: str | None
    ) -> Tag:
        existing = await self.tag_repo.get_by_name(user_id, name)
        if existing is not None:
            raise TagAlreadyExistsError()
        return await self.tag_repo.create(user_id, name=name, color=color)

    async def delete_tag(self, user_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        deleted = await self.tag_repo.delete(user_id, tag_id)
        if not deleted:
            raise NotFoundError()

    # --- R1 §5.1 cascade contract ---

    async def purge_account_data(self, user_id: uuid.UUID) -> int:
        """Callable, tested hard-delete for the document half of
        FR-USER-002's account-deletion cascade — see
        DocumentRepository.purge_for_user's own docstring for the honest
        boundary (not yet invoked by any scheduled job; R3's queue infra
        doesn't exist)."""
        storage_keys = await self.document_repo.purge_for_user(user_id)
        for key in storage_keys:
            await self.storage_provider.delete_object(key)
        return len(storage_keys)
