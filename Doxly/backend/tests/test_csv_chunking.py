"""tasks/remediation-plan.md R3 — chunk_csv_rows (rag.md §2's CSV row-group chunking)."""

from app.document_processing.chunking import (
    TARGET_MAX_TOKENS,
    chunk_csv_rows,
    count_tokens,
)


def test_empty_rows_yields_zero_chunks():
    """rag.md §2's degenerate-input contract, mirrored for the CSV path."""
    assert chunk_csv_rows(["a", "b"], []) == []


def test_small_row_set_fits_in_a_single_chunk_with_header_repeated():
    header = ["name", "score"]
    rows = [{"name": "Alice", "score": "95"}, {"name": "Bob", "score": "88"}]

    chunks = chunk_csv_rows(header, rows)

    assert len(chunks) == 1
    assert chunks[0].content.splitlines()[0] == "name,score"
    assert "Alice,95" in chunks[0].content
    assert "Bob,88" in chunks[0].content
    assert chunks[0].page_number is None
    assert chunks[0].chunk_index == 0


def test_large_row_set_splits_into_multiple_token_budgeted_groups_with_header_in_each():
    header = ["id", "description"]
    rows = [
        {
            "id": str(i),
            "description": f"A fairly long description of row number {i} " * 5,
        }
        for i in range(200)
    ]

    chunks = chunk_csv_rows(header, rows)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.content.splitlines()[0] == "id,description"
        assert chunk.token_count <= TARGET_MAX_TOKENS + count_tokens("id,description")


def test_every_row_appears_exactly_once_across_all_chunks():
    header = ["value"]
    rows = [{"value": f"row-{i}"} for i in range(500)]

    chunks = chunk_csv_rows(header, rows)

    data_lines: list[str] = []
    for chunk in chunks:
        lines = chunk.content.splitlines()
        assert lines[0] == "value"  # header repeated in every chunk
        data_lines.extend(lines[1:])

    assert data_lines == [f"row-{i}" for i in range(500)]


def test_chunk_indices_are_sequential():
    header = ["value"]
    rows = [{"value": str(i)} for i in range(300)]

    chunks = chunk_csv_rows(header, rows)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_char_offsets_are_ascending_and_track_the_canonical_row_text():
    header = ["value"]
    rows = [{"value": str(i)} for i in range(5)]

    chunks = chunk_csv_rows(header, rows)

    assert len(chunks) == 1
    assert chunks[0].char_start == 0
    # canonical text is "0\n1\n2\n3\n4" (no repeated header, no trailing newline)
    assert chunks[0].char_end == len("0\n1\n2\n3\n4")
