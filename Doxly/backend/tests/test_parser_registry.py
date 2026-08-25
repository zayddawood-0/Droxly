"""
tasks/remediation-plan.md R3 — parser_registry.py (document-processing.md
§8: "a registry maps MIME type -> parser implementation").
"""

import pytest

from app.document_processing.base import UnsupportedContentError
from app.document_processing.csv_parser import CsvParser
from app.document_processing.docx_parser import DocxParser
from app.document_processing.parser_registry import get_parser
from app.document_processing.pdf_parser import PdfParser
from app.document_processing.txt_parser import TxtParser


@pytest.mark.parametrize(
    ("mime_type", "expected_type"),
    [
        ("application/pdf", PdfParser),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            DocxParser,
        ),
        ("text/plain", TxtParser),
        ("text/csv", CsvParser),
    ],
)
def test_get_parser_returns_the_registered_implementation(mime_type, expected_type):
    assert isinstance(get_parser(mime_type), expected_type)


def test_get_parser_raises_for_an_unregistered_mime_type():
    """document-processing.md §8 — no per-file-type branching elsewhere;
    an unsupported type fails via this one typed error."""
    with pytest.raises(UnsupportedContentError):
        get_parser("application/zip")
