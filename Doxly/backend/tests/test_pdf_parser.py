"""
tasks/remediation-plan.md R3 — PdfParser (document-processing.md §3.1).
No DB needed — pure parser unit tests against real, in-memory PDF bytes
(tests/_pdf_fixtures.py), matching testing.md §3.1's "business logic,
fast, focused" shape.
"""

import pytest

from app.document_processing.base import (
    CorruptFileError,
    NoTextLayerError,
    PasswordProtectedError,
)
from app.document_processing.pdf_parser import PdfParser
from tests._pdf_fixtures import build_blank_pdf, build_encrypted_pdf, build_text_pdf


@pytest.fixture
def parser() -> PdfParser:
    return PdfParser()


def test_sniff_matches_real_pdf_header(parser):
    assert parser.sniff_matches(b"%PDF-1.4\n%...") is True


def test_sniff_rejects_non_pdf_header(parser):
    assert parser.sniff_matches(b"PK\x03\x04 not a pdf") is False


def test_parse_extracts_text_and_page_metadata(parser):
    """FR-PROC-001 — page count and per-page text preserved."""
    data = build_text_pdf(["First page content", "Second page content"])

    result = parser.parse(data)

    assert result.page_count == 2
    assert "First page content" in result.full_text
    assert "Second page content" in result.full_text
    # One page break recorded for a 2-page document (rag.md §2 / chunking.py's
    # _page_number_at contract: an ascending offset per subsequent page).
    assert result.page_breaks is not None
    assert len(result.page_breaks) == 1


def test_parse_single_page_has_no_page_breaks(parser):
    data = build_text_pdf(["Only page"])
    result = parser.parse(data)
    assert result.page_count == 1
    assert result.page_breaks == []


def test_parse_password_protected_pdf_raises_typed_error(parser):
    """document-processing.md §3.1 — detected at open time, no retry."""
    data = build_encrypted_pdf()

    with pytest.raises(PasswordProtectedError) as exc_info:
        parser.parse(data)

    assert exc_info.value.retryable is False
    assert "password-protected" in exc_info.value.user_message


def test_parse_scanned_pdf_with_no_text_layer_raises_typed_error(parser):
    """document-processing.md §3.1 — sampled pages yield zero extractable characters."""
    data = build_blank_pdf(page_count=3)

    with pytest.raises(NoTextLayerError) as exc_info:
        parser.parse(data)

    assert exc_info.value.retryable is False
    assert "OCR" in exc_info.value.user_message


def test_parse_corrupt_file_raises_typed_error(parser):
    garbage = b"%PDF-1.4\nthis is not a real pdf structure at all" + b"X" * 200

    with pytest.raises(CorruptFileError) as exc_info:
        parser.parse(garbage)

    assert exc_info.value.retryable is False
