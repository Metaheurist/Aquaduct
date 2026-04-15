from __future__ import annotations

from src.crawler import NewsItem
from src.topic_discovery import discover_topics_from_items


def test_discover_topics_from_items_ranks_reasonably():
    items = [
        NewsItem(title="OpenAI launches new Agents API for developers", url="u1", source="GoogleNews"),
        NewsItem(title="Benchmark: Llama 3.2 beats older baselines", url="u2", source="GoogleNews"),
        NewsItem(title="Stable Video Diffusion img2vid XT released", url="u3", source="MarkTechPost"),
    ]
    topics = discover_topics_from_items(items, limit=20)
    assert topics
    # Should include at least one obvious entity
    lowered = [t.lower() for t in topics]
    assert any("openai" in t for t in lowered) or any("llama" in t for t in lowered) or any("stable" in t for t in lowered)

