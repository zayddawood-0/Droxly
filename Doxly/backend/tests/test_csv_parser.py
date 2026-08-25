"""tasks/remediation-plan.md R3 — CsvParser (document-processing.md §3.4)."""

import pytest

from app.document_processing.base import EncodingError, MalformedCsvError
from app.document_processing.csv_parser import CsvParser


@pytest.fixture
def parser() -> CsvParser:
    return CsvParser()


def test_sniff_always_matches_no_reliable_signature(parser):
    assert parser.sniff_matches(b"anything at all") is True


def test_parse_extracts_header_and_typed_rows(parser):
    """FR-PROC-001 — header/column schema preserved, rows attached to column names."""
    data = b"name,score\nAlice,95\nBob,88\n"
    result = parser.parse(data)

    assert result.header == ["name", "score"]
    assert result.rows == [
        {"name": "Alice", "score": "95"},
        {"name": "Bob", "score": "88"},
    ]


def test_parse_header_only_file_yields_zero_rows(parser):
    result = parser.parse(b"a,b,c\n")
    assert result.header == ["a", "b", "c"]
    assert result.rows == []


def test_parse_inconsistent_column_counts_raises_typed_error(parser):
    """document-processing.md §3.4 — malformed dialect/inconsistent column counts."""
    data = b"a,b,c\n1,2,3\n4,5\n"
    with pytest.raises(MalformedCsvError) as exc_info:
        parser.parse(data)
    assert exc_info.value.retryable is False


def test_parse_empty_file_raises_typed_error(parser):
    with pytest.raises(MalformedCsvError):
        parser.parse(b"")


def test_parse_non_utf8_bytes_raises_encoding_error(parser):
    data = "café,résumé\n1,2\n".encode("latin-1")
    with pytest.raises(EncodingError):
        parser.parse(data)
