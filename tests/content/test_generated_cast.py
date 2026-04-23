from __future__ import annotations

from src.content.characters_store import cast_to_ephemeral_character, fallback_cast_for_show


def test_fallback_cast_news_is_single_narrator() -> None:
    cast = fallback_cast_for_show(video_format="news", topic_tags=["economy"], headline_seed="h")
    assert isinstance(cast, list)
    assert len(cast) == 1
    ch = cast_to_ephemeral_character(cast=cast, video_format="news")
    assert ch.name


def test_fallback_cast_cartoon_has_two_characters_minimum() -> None:
    cast = fallback_cast_for_show(video_format="cartoon", topic_tags=["cats"], headline_seed="h")
    assert len(cast) >= 2
    ch = cast_to_ephemeral_character(cast=cast, video_format="cartoon")
    # Identity should mention cast block for dialogue.
    assert "Cast" in ch.identity or "cast" in ch.identity.lower()

