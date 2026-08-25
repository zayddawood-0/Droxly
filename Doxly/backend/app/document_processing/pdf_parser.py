"""
tasks/remediation-plan.md R3 — PDF parser (document-processing.md §3.1,
decisions.md ADR-014: pypdf for structure/metadata, pdfplumber as the
primary text-extraction path for better layout fidelity).
"""

import io

from app.document_processing.base import (
    CorruptFileError,
    DocumentParser,
    NoTextLayerError,
    ParsedText,
    PasswordProtectedError,
)

# document-processing.md §3.1 — "if a page yields zero extractable
# characters via the text layer across a sampled threshold of pages (e.g.,
# first 3 pages and a random sample)". A fixed, small sample size keeps
# scanned-image detection cheap even for very large PDFs.
_SAMPLE_PAGE_COUNT = 3


class PdfParser(DocumentParser):
    mime_type = "application/pdf"

    def sniff_matches(self, header_bytes: bytes) -> bool:
        return header_bytes.startswith(b"%PDF-")

    def parse(self, data: bytes) -> ParsedText:
        import pypdf
        from pypdf.errors import PyPdfError

        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
        except (PyPdfError, ValueError, OSError) as exc:
            raise CorruptFileError() from exc

        if reader.is_encrypted:
            raise PasswordProtectedError()

        pages_text = self._extract_pages(data)

        if not pages_text:
            raise NoTextLayerError()

        sample_indices = list(range(min(_SAMPLE_PAGE_COUNT, len(pages_text))))
        if len(pages_text) > _SAMPLE_PAGE_COUNT:
            import random

            sample_indices.append(random.randrange(_SAMPLE_PAGE_COUNT, len(pages_text)))

        if not any(pages_text[i].strip() for i in sample_indices):
            raise NoTextLayerError()

        full_text_parts: list[str] = []
        page_breaks: list[int] = []
        cursor = 0
        for i, text in enumerate(pages_text):
            full_text_parts.append(text)
            cursor += len(text)
            if i < len(pages_text) - 1:
                cursor += 1  # the "\n" join separator below
                page_breaks.append(cursor)

        full_text = "\n".join(full_text_parts)
        if not full_text.strip():
            raise NoTextLayerError()

        return ParsedText(
            full_text=full_text, page_breaks=page_breaks, page_count=len(pages_text)
        )

    def _extract_pages(self, data: bytes) -> list[str]:
        import pdfplumber
        from pdfplumber.utils.exceptions import PdfminerException

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return [page.extract_text() or "" for page in pdf.pages]
        except (PdfminerException, ValueError, OSError) as exc:
            raise CorruptFileError() from exc
