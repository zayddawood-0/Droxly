"""
tasks/remediation-plan.md R3 — CSV parser (document-processing.md §3.4,
decisions.md ADR-014: pandas preferred, stdlib `csv` as a lightweight
fallback for very small/edge-case files pandas itself rejects).
"""

import csv as csv_module
import io

from app.document_processing.base import (
    DocumentParser,
    EncodingError,
    MalformedCsvError,
    ParsedCsv,
)


class CsvParser(DocumentParser):
    mime_type = "text/csv"

    def sniff_matches(self, header_bytes: bytes) -> bool:
        # No reliable magic-byte signature for CSV — an unparseable file
        # still fails inside parse() via MalformedCsvError/EncodingError.
        return True

    def parse(self, data: bytes) -> ParsedCsv:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EncodingError() from exc

        # pandas' C parser silently pads a short row with NaN rather than
        # raising (it only errors on rows with EXTRA fields) — document-
        # processing.md §3.4 requires inconsistent column counts to be
        # rejected, so that check is done explicitly here, upfront, rather
        # than relying on either library's own leniency.
        self._validate_consistent_column_counts(text)

        try:
            return self._parse_with_pandas(text)
        except MalformedCsvError:
            return self._parse_with_stdlib(text)

    def _validate_consistent_column_counts(self, text: str) -> None:
        rows_raw = [
            row for row in csv_module.reader(io.StringIO(text)) if row
        ]  # blank lines are formatting noise, not malformed rows
        if not rows_raw:
            raise MalformedCsvError()
        expected_len = len(rows_raw[0])
        if any(len(row) != expected_len for row in rows_raw[1:]):
            raise MalformedCsvError()

    def _parse_with_pandas(self, text: str) -> ParsedCsv:
        import pandas as pd

        try:
            frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
        except Exception as exc:  # pandas raises several distinct error types
            raise MalformedCsvError() from exc

        if frame.shape[1] == 0:
            raise MalformedCsvError()

        header = [str(c) for c in frame.columns]
        rows = frame.to_dict(orient="records")
        return ParsedCsv(header=header, rows=rows)

    def _parse_with_stdlib(self, text: str) -> ParsedCsv:
        """
        document-processing.md §3.4's lightweight fallback path. Also
        catches the small edge cases pandas' own parser is stricter about
        (e.g. a single header-only row) — still rejects genuinely malformed
        input (inconsistent column counts) rather than best-effort-repairing it.
        """
        reader = csv_module.reader(io.StringIO(text))
        rows_raw = list(reader)
        if not rows_raw:
            raise MalformedCsvError()

        header = rows_raw[0]
        expected_len = len(header)
        rows: list[dict[str, str]] = []
        for raw_row in rows_raw[1:]:
            if len(raw_row) != expected_len:
                raise MalformedCsvError()
            rows.append(dict(zip(header, raw_row, strict=True)))
        return ParsedCsv(header=header, rows=rows)
