"""
tasks/remediation-plan.md R3 — the `DocumentParser` interface
document-processing.md §8 describes: a registry maps MIME type -> parser
implementation; each parser (1) validates sniffed content against the
claimed type, (2) produces extracted text/rows in one of the two common
intermediate shapes below, and (3) raises a small, fixed set of typed parse
errors that the orchestration layer (services/document_processing_service.py)
maps to sanitized `processing_error` messages (NFR-SEC-009) — it never
contains per-file-type branching logic itself.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedText:
    """
    Result shape for paragraph/sentence-chunked formats (PDF/DOCX/TXT) —
    handed to `chunking.chunk_text()` unmodified.

    `page_breaks` is an ascending list of character offsets where each new
    page begins (PDF only; `chunking.py`'s existing `_page_number_at`
    contract) — `None` for DOCX/TXT, which have no page concept
    (document-processing.md §3.2/§3.3).
    """

    full_text: str
    page_breaks: list[int] | None
    page_count: int | None


@dataclass(frozen=True)
class ParsedCsv:
    """
    Result shape for CSV's row-group chunking variant (rag.md §2) — handed
    to `chunking.chunk_csv_rows()`, not `chunk_text()`, since CSV content is
    fundamentally row-structured rather than prose.
    """

    header: list[str]
    rows: list[dict[str, str]]


ParsedDocument = ParsedText | ParsedCsv


class DocumentParseError(Exception):
    """
    Base for every typed parse failure (document-processing.md §6). Carries
    the exact sanitized, user-safe message the spec assigns to this failure
    mode (NFR-SEC-009 — library exceptions/stack traces are never surfaced;
    only this fixed message is). `retryable=False` is the default: every
    subclass below is a permanent, content-inherent failure (NFR-AVAIL-002 —
    "retrying cannot change the outcome"), so retrying is actively wrong,
    not merely unnecessary. `TransientParseError` is the one exception,
    reserved for a genuinely transient condition detected before/during
    parsing (e.g. a storage read hiccup) rather than a property of the file
    itself.
    """

    user_message: str = "This document could not be processed."
    retryable: bool = False


class UnsupportedContentError(DocumentParseError):
    """Sniffed content doesn't match the document's declared/stored MIME type."""

    user_message = "File content does not match its declared type."


class CorruptFileError(DocumentParseError):
    """The file's container/structure is unreadable by the format's own parser."""

    user_message = "This file appears to be corrupted and cannot be processed."


class PasswordProtectedError(DocumentParseError):
    """PDF-specific: encrypted at open time (document-processing.md §3.1)."""

    user_message = "This document is password-protected and cannot be processed."


class NoTextLayerError(DocumentParseError):
    """PDF-specific: sampled pages yield zero extractable characters (scanned/image-only, OCR out of scope — decisions.md OQ-05)."""

    user_message = (
        "This document appears to be a scanned image without extractable "
        "text. OCR is not yet supported."
    )


class EncodingError(DocumentParseError):
    """TXT/CSV: no attempted encoding (UTF-8, then charset-normalizer's best guess) could decode the file."""

    user_message = "Unable to read this file's text encoding."


class MalformedCsvError(DocumentParseError):
    """CSV: unparseable dialect or inconsistent column counts beyond tolerance."""

    user_message = "This file could not be parsed as valid CSV."


class TransientParseError(DocumentParseError):
    """
    A non-content-inherent failure (e.g. a storage read error) — the one
    `DocumentParseError` subclass that IS retryable. Distinguishes "this
    file can never be parsed" from "this attempt happened to fail."
    """

    user_message = "A temporary error occurred while processing this document."
    retryable = True


class DocumentParser(ABC):
    """
    One implementation per supported MIME type, registered in
    `parser_registry.py`. Parsing itself is synchronous (the underlying
    libraries — pypdf/pdfplumber/python-docx/pandas — are not async-native,
    decisions.md ADR-014) — callers run `parse()` via `run_in_executor`
    (skills/backend.md §13), never directly on the event loop.
    """

    mime_type: str

    @abstractmethod
    def sniff_matches(self, header_bytes: bytes) -> bool:
        """
        document-processing.md §1 — "the worker sniffs actual file content
        ... before invoking a parser." Formats with no reliable magic-byte
        signature (TXT/CSV) return True unconditionally here; an actually
        unparseable file still fails inside `parse()` with a typed error.
        """

    @abstractmethod
    def parse(self, data: bytes) -> ParsedDocument:
        """Raises a `DocumentParseError` subclass on any failure; never raises a raw library exception."""
