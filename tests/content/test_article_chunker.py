"""Phase 10: sentence-aware article chunker."""

from __future__ import annotations

from src.content.article_chunker import ArticleChunk, chunk_article_text


def test_returns_empty_list_for_empty_input() -> None:
    assert chunk_article_text("") == []
    assert chunk_article_text("   ") == []


def test_short_text_collapses_to_one_chunk() -> None:
    text = "This is a short story. It fits inside one chunk."
    chunks = chunk_article_text(text, target_chars=2000, max_chunks=8)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_splits_long_text_at_sentence_boundaries() -> None:
    text = (
        "Para one start. Para one continues with details. " * 30
        + "\n\n"
        + "Para two start. Para two continues. " * 30
    )
    chunks = chunk_article_text(text, target_chars=400, max_chunks=8)
    assert 2 <= len(chunks) <= 8
    for c in chunks:
        assert c.length <= 1500  # target plus one sentence overrun is allowed


def test_caps_chunk_count() -> None:
    text = ("Sentence A. Sentence B. " * 200)
    chunks = chunk_article_text(text, target_chars=200, max_chunks=4)
    assert len(chunks) == 4


def test_chunk_indexing_is_sequential() -> None:
    text = ("Foo bar. " * 200)
    chunks = chunk_article_text(text, target_chars=300, max_chunks=6)
    for i, c in enumerate(chunks):
        assert isinstance(c, ArticleChunk)
        assert c.index == i


def test_min_chars_merges_tiny_first_chunk() -> None:
    text = "Tiny start. " + ("Then a long body sentence with many words. " * 60)
    chunks = chunk_article_text(text, target_chars=400, max_chunks=4, min_chars=50)
    assert chunks[0].length >= 50 or len(chunks) == 1
