from __future__ import annotations

from src.core.config import video_format_supports_facts_card


def test_facts_card_only_news_and_explainer() -> None:
    assert video_format_supports_facts_card("news") is True
    assert video_format_supports_facts_card("explainer") is True
    assert video_format_supports_facts_card("cartoon") is False
    assert video_format_supports_facts_card("unhinged") is False
    assert video_format_supports_facts_card("creepypasta") is False
    assert video_format_supports_facts_card(None) is True  # default pipeline treats as news
    assert video_format_supports_facts_card("NEWS") is True
