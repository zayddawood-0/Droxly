"""tasks/remediation-plan.md R3 — TxtParser (document-processing.md §3.3)."""

import pytest

from app.document_processing.base import EncodingError
from app.document_processing.txt_parser import TxtParser


@pytest.fixture
def parser() -> TxtParser:
    return TxtParser()


def test_sniff_always_matches_no_reliable_signature(parser):
    assert parser.sniff_matches(b"anything at all") is True


def test_parse_decodes_valid_utf8(parser):
    text = "Plain UTF-8 text with a paragraph.\n\nSecond paragraph."
    result = parser.parse(text.encode("utf-8"))
    assert result.full_text == text
    assert result.page_breaks is None
    assert result.page_count is None


def test_parse_falls_back_to_charset_normalizer_for_non_utf8_bytes(parser):
    """document-processing.md §3.3 — a fallback detection pass attempts
    common alternate encodings before failing."""
    text = "Café naïve résumé"  # café naïve résumé
    data = text.encode("latin-1")
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")  # sanity: this really isn't valid UTF-8

    result = parser.parse(data)
    assert result.full_text  # some non-empty decoded text recovered


def test_parse_raises_encoding_error_when_no_encoding_can_decode(parser):
    """document-processing.md §3.3's terminal failure mode."""
    undecodable = bytes(range(256)) * 4

    with pytest.raises(EncodingError) as exc_info:
        parser.parse(undecodable)

    assert exc_info.value.retryable is False
