"""Phase 3: deterministic article-excerpt sanitizer.

Pre-Phase-3, the script LLM saw the *entire* longest text candidate from
:func:`src.content.crawler.fetch_article_text`, which on Fandom and other
wiki-like sources still included the trailing rails (Fan Feed, Trending
pages, Categories…), citation markers, and cookie / share / promo lines.

These tests guard the deterministic regex cleaner that runs *before* the
chunked LLM relevance pass added in Phase 10.
"""

from __future__ import annotations

from src.content.article_clean import (
    clean_article_excerpt,
    clean_many,
)


def test_drops_citation_markers() -> None:
    raw = (
        "The narrator wakes up confused [12]. The whispers continue [citation needed]. "
        "Eventually the lights die [3]."
    )
    out = clean_article_excerpt(raw, url="https://example.com/news")
    assert "[12]" not in out
    assert "[citation needed]" not in out
    assert "[3]" not in out


def test_truncates_at_fandom_rail_header() -> None:
    raw = (
        "She found the diary in the attic, the pages cold and waxy. "
        "By dawn the diary was on her pillow. "
        "Trending pages 1 The Smiling Man 2 The Russian Sleep Experiment 3 Slender"
    )
    out = clean_article_excerpt(raw, url="https://creepypasta.fandom.com/wiki/SCP_Foundation")
    assert "diary" in out
    assert "Trending pages" not in out
    assert "Smiling Man" not in out


def test_keeps_paragraphs_that_mention_rail_words_in_prose() -> None:
    """The cleaner must not nuke prose just because it mentions 'fan feed' inline."""
    raw = (
        "He dreamt of a fan feed of comments crawling across the wall, every line accusing him by name."
    )
    out = clean_article_excerpt(raw, url="https://example.com/blog/post")
    # On a non-wiki URL with no other rail markers, the cleaner does NOT cut here.
    assert "fan feed of comments" in out


def test_aggressive_mode_can_cut_rails_on_non_wiki_urls() -> None:
    raw = "Story content here. Fan Feed Trending pages 1 X 2 Y 3 Z 4 W"
    out = clean_article_excerpt(raw, url="https://example.com/", aggressive=True)
    assert "Trending pages" not in out
    assert "Story content here." in out


def test_collapses_long_numbered_lists() -> None:
    raw = (
        "Story body. "
        "1 The First Tale 2 The Second Tale 3 The Third Tale 4 The Fourth Tale 5 The Fifth Tale"
    )
    out = clean_article_excerpt(raw, url="https://example.com/blog/post")
    assert "related pages" in out.lower() or "Story body" in out


def test_strips_promo_and_share_lines() -> None:
    raw = (
        "She heard the doorknob turn.\n"
        "Subscribe to our newsletter for more stories!\n"
        "Cookie consent: accept all cookies.\n"
        "She heard it turn again."
    )
    out = clean_article_excerpt(raw, url="https://example.com/news/article")
    assert "Subscribe to our newsletter" not in out
    assert "Cookie consent" not in out
    assert "doorknob" in out


def test_caps_to_max_chars() -> None:
    raw = "word " * 5000
    out = clean_article_excerpt(raw, url="https://example.com/", max_chars=200)
    assert len(out) <= 220  # 200 + ellipsis tolerance
    assert out.endswith("…")


def test_clean_many_returns_per_item_excerpts() -> None:
    items = [
        ("https://example.com/news/a", "Story A. Categories: news"),
        ("https://creepypasta.fandom.com/wiki/X", "Body. Trending pages 1 A 2 B 3 C 4 D"),
    ]
    out = clean_many(items, max_chars=2000)
    assert len(out) == 2
    assert "Story A" in out[0]
    assert "Trending" not in out[1]


def test_handles_empty_input() -> None:
    assert clean_article_excerpt("") == ""
    assert clean_article_excerpt(None) == ""  # type: ignore[arg-type]
