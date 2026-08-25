"""
tasks/remediation-plan.md R3 — TXT parser (document-processing.md §3.3):
native UTF-8 decode, then a charset-normalizer fallback pass for common
alternate encodings before failing (decisions.md ADR-014).
"""

from app.document_processing.base import DocumentParser, EncodingError, ParsedText


class TxtParser(DocumentParser):
    mime_type = "text/plain"

    def sniff_matches(self, header_bytes: bytes) -> bool:
        # No reliable magic-byte signature for plain text — a genuinely
        # unparseable file still fails inside parse() via EncodingError.
        return True

    def parse(self, data: bytes) -> ParsedText:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = self._decode_fallback(data)

        return ParsedText(full_text=text, page_breaks=None, page_count=None)

    def _decode_fallback(self, data: bytes) -> str:
        import charset_normalizer

        best_match = charset_normalizer.from_bytes(data).best()
        if best_match is None:
            raise EncodingError()
        return str(best_match)
