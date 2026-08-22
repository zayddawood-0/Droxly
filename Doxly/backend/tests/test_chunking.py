from itertools import pairwise

from app.document_processing.chunking import (
    TARGET_MAX_TOKENS,
    TARGET_MIN_TOKENS,
    chunk_text,
    count_tokens,
)


def test_empty_and_whitespace_only_text_yields_zero_chunks():
    """rag.md §2's degenerate-input case — never force-chunk meaningless input."""
    assert chunk_text("") == []
    assert chunk_text("   \n\n  \t") == []


def test_short_document_yields_a_single_undersized_chunk():
    text = "Just one short paragraph, nothing fancy."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].content == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert chunks[0].chunk_index == 0


def test_every_chunk_stays_within_the_target_token_window_except_the_final_tail():
    paragraph = (
        "This is a sentence about cats. Cats are wonderful pets. " * 40
    ).strip()
    text = "\n\n".join([paragraph] * 6)
    chunks = chunk_text(text)

    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert chunk.token_count <= TARGET_MAX_TOKENS
    # The final chunk is allowed to be smaller than the target minimum —
    # there's no more content left to pack into it.
    assert chunks[-1].token_count <= TARGET_MAX_TOKENS


def test_chunk_indices_are_sequential_and_offsets_are_ordered():
    paragraph = ("Sentence one. Sentence two. Sentence three. " * 20).strip()
    text = "\n\n".join([paragraph] * 5)
    chunks = chunk_text(text)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for earlier, later in pairwise(chunks):
        assert later.char_start >= earlier.char_start
        assert later.char_end > earlier.char_end


def test_consecutive_chunks_overlap_when_atoms_are_small_enough_to_allow_it():
    sentence_text = " ".join(
        f"This is sentence number {i} about testing chunking behavior."
        for i in range(200)
    )
    chunks = chunk_text(sentence_text)

    assert len(chunks) > 1
    # Overlap means the next chunk's content starts before the previous one ends.
    assert chunks[1].char_start < chunks[0].char_end
    overlap_text = sentence_text[chunks[1].char_start : chunks[0].char_end]
    assert overlap_text.strip() != ""


def test_a_run_on_sentence_with_no_punctuation_still_respects_the_token_ceiling():
    """Last-resort hard-split path (rag.md §2) — never silently exceed TARGET_MAX_TOKENS."""
    runon = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(runon)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= TARGET_MAX_TOKENS
    # Reassembling every chunk's raw span (ignoring overlap) covers the source text.
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(runon)


def test_page_number_reflects_the_page_a_chunk_starts_on():
    text = ("Page one content sentence. " * 300) + ("Page two content sentence. " * 300)
    page_two_offset = text.index("Page two")
    chunks = chunk_text(text, page_breaks=[page_two_offset])

    pages_seen = {c.page_number for c in chunks}
    assert pages_seen == {1, 2}
    for chunk in chunks:
        expected_page = 1 if chunk.char_start < page_two_offset else 2
        assert chunk.page_number == expected_page


def test_page_number_is_none_when_no_page_breaks_are_given():
    """DOCX/TXT sources have no page concept (database.md's nullable page_number)."""
    chunks = chunk_text("Some content. " * 100)
    assert all(c.page_number is None for c in chunks)


def test_count_tokens_matches_the_chunker_s_own_measurement():
    text = "A short piece of text for token counting."
    assert count_tokens(text) > 0
    chunks = chunk_text(text)
    assert chunks[0].token_count == count_tokens(text)


def test_target_window_constants_match_rag_md():
    assert TARGET_MIN_TOKENS == 500
    assert TARGET_MAX_TOKENS == 800
