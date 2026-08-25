import re
from dataclasses import dataclass

import tiktoken

# rag.md §2 — target 500-800 tokens per chunk, ~15% (75-120 token) overlap.
TARGET_MIN_TOKENS = 500
TARGET_MAX_TOKENS = 800
OVERLAP_TOKENS = 100

# cl100k_base matches text-embedding-3-small (decisions.md ADR-012 default),
# so token_count reflects what the configured embedding model actually sees.
_ENCODING = tiktoken.get_encoding("cl100k_base")

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_Span = tuple[
    str, int, int
]  # (text, char_start, char_end) — offsets into the original full_text


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    token_count: int
    page_number: int | None


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def chunk_text(
    full_text: str, *, page_breaks: list[int] | None = None
) -> list[TextChunk]:
    """
    rag.md §2 — recursive, structure-aware splitting: paragraph boundaries
    first, then sentence boundaries, then a hard token-count cut only as a
    last resort, so a chunk is never split mid-sentence when a cleaner
    boundary exists. Consecutive chunks overlap by ~OVERLAP_TOKENS so a fact
    near a boundary isn't orphaned from its surrounding context.

    `page_breaks` is an ascending list of character offsets where each new
    PDF page begins; omit for DOCX/TXT, which have no page concept
    (`page_number` stays `None` for every chunk, matching the nullable
    column in database.md §3.4). CSV's row-group chunking variant (rag.md
    §2) is not implemented here — it needs structured row input a plain-text
    extractor doesn't produce, and no CSV parser exists yet (Phase 5
    backend, not yet built); this function covers the PDF/DOCX/TXT case.

    A document producing no non-whitespace text yields an empty list — the
    caller's job (FR-PROC-004) to route that as a failure, not force a
    meaningless fragment (rag.md §2's degenerate-input case).
    """
    if not full_text or not full_text.strip():
        return []

    atoms = _flatten_to_atoms(full_text)
    return _pack_atoms(full_text, atoms, page_breaks)


def _flatten_to_atoms(full_text: str) -> list[_Span]:
    """Paragraph → sentence → hard-cut cascade, producing pieces no larger than TARGET_MAX_TOKENS each."""
    atoms: list[_Span] = []
    for paragraph, p_start, p_end in _split_with_offsets(
        full_text, _PARAGRAPH_SPLIT, 0
    ):
        if count_tokens(paragraph) <= TARGET_MAX_TOKENS:
            atoms.append((paragraph, p_start, p_end))
            continue
        for sentence, s_start, s_end in _split_with_offsets(
            paragraph, _SENTENCE_SPLIT, p_start
        ):
            if count_tokens(sentence) <= TARGET_MAX_TOKENS:
                atoms.append((sentence, s_start, s_end))
            else:
                atoms.extend(_hard_split(sentence, s_start))
    return atoms


def _pack_atoms(
    full_text: str, atoms: list[_Span], page_breaks: list[int] | None
) -> list[TextChunk]:
    """Greedily packs atoms into TARGET_MIN..TARGET_MAX-token windows, carrying a trailing overlap forward."""
    chunks: list[TextChunk] = []
    current: list[_Span] = []
    current_tokens = 0

    def flush() -> None:
        if not current:
            return
        content = full_text[current[0][1] : current[-1][2]]
        chunks.append(
            TextChunk(
                chunk_index=len(chunks),
                content=content,
                char_start=current[0][1],
                char_end=current[-1][2],
                token_count=count_tokens(content),
                page_number=_page_number_at(current[0][1], page_breaks),
            )
        )

    for atom in atoms:
        atom_text, _, _ = atom
        atom_tokens = count_tokens(atom_text)

        if current and current_tokens + atom_tokens > TARGET_MAX_TOKENS:
            flush()
            current, current_tokens = _trailing_overlap(current)

        current.append(atom)
        current_tokens += atom_tokens

    flush()
    return chunks


def _trailing_overlap(previous: list[_Span]) -> tuple[list[_Span], int]:
    """
    Walks backward from the end of the just-flushed chunk, including whole
    atoms while they still fit the overlap budget. Deliberately does NOT
    force at least one atom in — an atom larger than OVERLAP_TOKENS on its
    own (e.g. a single big paragraph) is left out entirely rather than
    blown past the budget, since splitting it to fit would violate "never
    split mid-sentence/paragraph when a cleaner boundary exists" (rag.md §2).
    """
    overlap: list[_Span] = []
    overlap_tokens = 0
    for atom in reversed(previous):
        atom_tokens = count_tokens(atom[0])
        if overlap_tokens + atom_tokens > OVERLAP_TOKENS:
            break
        overlap.insert(0, atom)
        overlap_tokens += atom_tokens
    return overlap, overlap_tokens


def _page_number_at(offset: int, page_breaks: list[int] | None) -> int | None:
    """
    The page a chunk *starts* on (rag.md §2) — 1-indexed. `page_breaks is
    None` means no page concept applies at all (DOCX/TXT). `page_breaks ==
    []` is different — a single-page PDF (R3's PdfParser) legitimately
    records zero *breaks* while every chunk is still on page 1; treating an
    empty list the same as None here would silently drop page 1 attribution
    for every single-page PDF.
    """
    if page_breaks is None:
        return None
    page = 1
    for break_offset in page_breaks:
        if offset < break_offset:
            break
        page += 1
    return page


def _split_with_offsets(
    text: str, pattern: re.Pattern[str], base_offset: int
) -> list[_Span]:
    """Splits on `pattern`, returning non-empty pieces with offsets relative to the original full document."""
    pieces: list[_Span] = []
    cursor = 0
    for match in pattern.finditer(text):
        piece = text[cursor : match.start()]
        if piece.strip():
            pieces.append((piece, base_offset + cursor, base_offset + match.start()))
        cursor = match.end()
    tail = text[cursor:]
    if tail.strip():
        pieces.append((tail, base_offset + cursor, base_offset + len(text)))
    return pieces


def chunk_csv_rows(header: list[str], rows: list[dict[str, str]]) -> list[TextChunk]:
    """
    rag.md §2 — "CSV documents are chunked by logical row groups (not raw
    character windows) — a chunk contains a coherent set of rows (with the
    header repeated per chunk for context) rather than an arbitrary
    character slice that could bisect a row." Packs whole rows into groups
    up to TARGET_MAX_TOKENS (reusing the same budget the prose path targets,
    rather than an arbitrary fixed row count) — a row is never split.

    `char_start`/`char_end` track offsets into the canonical, non-repeated
    row-serialized text (header appears once, conceptually, at the start of
    that canonical text) rather than into each chunk's own repeated-header
    `content` string, so the offsets stay meaningful positions within the
    source data even though `content` itself repeats the header for
    per-chunk readability. No overlap between row groups (unlike prose
    chunking) — rows aren't narratively continuous, and the repeated header
    already supplies context; duplicating rows across chunks would only
    risk duplicate retrieval hits.

    An empty `rows` list yields zero chunks — the same degenerate-input
    contract `chunk_text` follows (rag.md §2), routed by the caller to
    FR-PROC-004's failure handling.
    """
    if not rows:
        return []

    header_line = ",".join(header)
    header_tokens = count_tokens(header_line)

    def row_line(row: dict[str, str]) -> str:
        return ",".join(str(row.get(col, "")) for col in header)

    row_lines = [row_line(row) for row in rows]
    row_tokens = [count_tokens(line) for line in row_lines]

    row_offsets: list[tuple[int, int]] = []
    cursor = 0
    for line in row_lines:
        start = cursor
        cursor += len(line)
        row_offsets.append((start, cursor))
        cursor += 1  # newline separator between rows in the canonical text

    chunks: list[TextChunk] = []
    group_start = 0
    group_tokens = header_tokens
    for i in range(len(row_lines)):
        if i > group_start and group_tokens + row_tokens[i] > TARGET_MAX_TOKENS:
            _flush_csv_group(
                chunks, header_line, row_lines, row_offsets, group_start, i
            )
            group_start = i
            group_tokens = header_tokens
        group_tokens += row_tokens[i]
    _flush_csv_group(
        chunks, header_line, row_lines, row_offsets, group_start, len(row_lines)
    )
    return chunks


def _flush_csv_group(
    chunks: list[TextChunk],
    header_line: str,
    row_lines: list[str],
    row_offsets: list[tuple[int, int]],
    start: int,
    end: int,
) -> None:
    content = "\n".join([header_line, *row_lines[start:end]])
    chunks.append(
        TextChunk(
            chunk_index=len(chunks),
            content=content,
            char_start=row_offsets[start][0],
            char_end=row_offsets[end - 1][1],
            token_count=count_tokens(content),
            page_number=None,
        )
    )


def _hard_split(text: str, base_offset: int) -> list[_Span]:
    """
    Last resort for a single sentence still over TARGET_MAX_TOKENS (e.g. a
    run-on sentence with no punctuation) — cuts by character span, shrinking
    until each piece measures within budget, rather than by re-decoding
    token slices (which doesn't round-trip cleanly to exact char offsets).
    """
    pieces: list[_Span] = []
    start = 0
    n = len(text)
    approx_chars_per_token = 4
    while start < n:
        end = min(start + TARGET_MAX_TOKENS * approx_chars_per_token, n)
        while end > start + 1 and count_tokens(text[start:end]) > TARGET_MAX_TOKENS:
            end -= max(1, (end - start) // 10)
        pieces.append((text[start:end], base_offset + start, base_offset + end))
        start = end
    return pieces
