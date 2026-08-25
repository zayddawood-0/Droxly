"""
tasks/remediation-plan.md R3 — MIME type -> DocumentParser lookup
(document-processing.md §8: "a registry maps MIME type -> parser
implementation"). Adding a new file type means registering one new parser
here — no other pipeline code changes (§8's extensibility contract).
"""

from app.document_processing.base import DocumentParser, UnsupportedContentError
from app.document_processing.csv_parser import CsvParser
from app.document_processing.docx_parser import DocxParser
from app.document_processing.pdf_parser import PdfParser
from app.document_processing.txt_parser import TxtParser

_REGISTRY: dict[str, DocumentParser] = {
    PdfParser.mime_type: PdfParser(),
    DocxParser.mime_type: DocxParser(),
    TxtParser.mime_type: TxtParser(),
    CsvParser.mime_type: CsvParser(),
}


def get_parser(mime_type: str) -> DocumentParser:
    parser = _REGISTRY.get(mime_type)
    if parser is None:
        raise UnsupportedContentError()
    return parser
