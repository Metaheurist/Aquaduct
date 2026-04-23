from __future__ import annotations

from src.content.crawler import NewsItem
from src.content.topic_discovery import discover_topics_from_items


def test_discover_topics_fallback_uses_title_when_parsing_empty():
    """Meme-style or stopword-heavy titles should still yield at least one line."""
    items = [
        NewsItem(title="the a an of", url="u1", source="Firecrawl"),
    ]
    topics = discover_topics_from_items(items, limit=10)
    assert topics == ["the a an of"]


def test_discover_creative_drops_platform_tokens_and_listicles():
    items = [
        NewsItem(title="Top 10 Sketch Comedy Channels on YouTube 2025", url="u1", source="Firecrawl"),
        NewsItem(title="Netflix", url="u2", source="Firecrawl"),
        NewsItem(title="Instagram Photos And Videos From Festival", url="u3", source="Firecrawl"),
        NewsItem(
            title="Absurdist cartoon short about a tired moon — indie animation meme",
            url="u4",
            source="Firecrawl",
        ),
    ]
    topics = discover_topics_from_items(items, limit=20, topic_mode="cartoon")
    lowered = " ".join(topics).lower()
    assert "youtube" not in lowered or "animation" in lowered
    assert "top 10" not in lowered
    assert "netflix" not in lowered
    assert any("animation" in t.lower() or "cartoon" in t.lower() or "meme" in t.lower() for t in topics)


def test_discover_topics_from_items_ranks_reasonably():
    items = [
        NewsItem(title="OpenAI launches new Agents API for developers", url="u1", source="GoogleNews"),
        NewsItem(title="Benchmark: Llama 4 beats older baselines", url="u2", source="GoogleNews"),
        NewsItem(title="Stable Video Diffusion img2vid XT released", url="u3", source="MarkTechPost"),
    ]
    topics = discover_topics_from_items(items, limit=20)
    assert topics
    # Should include at least one obvious entity
    lowered = [t.lower() for t in topics]
    assert any("openai" in t for t in lowered) or any("llama" in t for t in lowered) or any("stable" in t for t in lowered)


def test_content_quality_scoring_prefers_non_clickbait(tmp_path):
    from src.content.content_quality import load_seen_titles, save_seen_titles, score_item

    seen_path = tmp_path / "seen_titles.json"
    # Seed with a different title so we don't penalize the "good" item as a duplicate.
    save_seen_titles(seen_path, ["Some other unrelated AI headline"])
    seen = load_seen_titles(seen_path)

    good = NewsItem(title="OpenAI launches new Agents API for developers", url="u1", source="GoogleNews")
    bad = NewsItem(title="You WON'T believe this new AI tool!!!", url="u2", source="GoogleNews")

    s_good = score_item(good, topic_tags=["OpenAI"], seen_titles=seen, source_weights={"GoogleNews": 0.25})
    s_bad = score_item(bad, topic_tags=["OpenAI"], seen_titles=seen, source_weights={"GoogleNews": 0.25})

    # Clickbait should be penalized in clarity, and duplicates should be penalized.
    assert s_bad.clarity <= s_good.clarity
    assert s_good.total >= s_bad.total

