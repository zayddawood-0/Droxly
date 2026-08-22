import uuid


class DoxlyError(Exception):
    """
    Base for all domain-level errors (skills/backend.md §10) — services (and,
    once routers exist, a single global exception handler mapping each
    subclass to the api.md §0.5 envelope) raise/catch these, never a raw
    HTTPException constructed inline. Introduced in Phase 6 — the first
    phase with a service-layer business-rule failure to signal — and
    extended by later phases rather than each inventing its own error base.
    """


class EmptyDocumentError(DoxlyError):
    """
    Raised when chunking a document's extracted text yields zero chunks
    (rag.md §2's degenerate-input case, e.g. a mostly-image PDF with no text
    layer). Recording documents.status='failed' with a user-safe reason is
    FR-PROC-004's concern, owned by whichever caller performed extraction
    (the Phase 5 backend worker) — this error only signals that embedding
    cannot proceed, it does not itself touch document status.
    """

    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(
            f"Document {document_id} produced no chunks from its extracted text."
        )
        self.document_id = document_id
