from __future__ import annotations

from pathlib import Path

import pytest

from src.content.story_context import (
    _meme_supplement_searches,
    _search_query,
    build_script_context,
)


def test_search_query_cartoon_biases_memes():
    q = _search_query(["slapstick"], ["Some headline"], video_format="cartoon")
    assert "meme" in q.lower() or "viral" in q.lower()
    assert "slapstick" in q


def test_search_query_unhinged_biases_memes():
    q = _search_query([], [], video_format="unhinged")
    assert "meme" in q.lower() or "viral" in q.lower()


def test_search_query_news_default():
    q = _search_query(["AI"], [], video_format="news")
    assert "AI" in q


def test_meme_supplement_only_cartoon_unhinged():
    assert len(_meme_supplement_searches(video_format="news", topic_tags=[], source_titles=[])) == 0
    a = _meme_supplement_searches(video_format="cartoon", topic_tags=["x"], source_titles=[])
    assert len(a) == 2
    assert any("meme" in x.lower() or "knowyourmeme" in x.lower() for x in a)


def test_build_script_context_cartoon_calls_extra_searches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[str] = []

    def fake_search(q: str, *, limit: int, api_key: str):
        calls.append(q)
        return [{"title": "T", "url": f"https://ex.com/{len(calls)}", "source": "x"}]

    def fake_scrape(url: str, *, api_key: str, timeout_s: int = 60):
        return f"![x](https://picsum.photos/seed/{hash(url) % 1000}/40/40)\n"

    monkeypatch.setattr("src.content.story_context.firecrawl_search_news", fake_search)
    monkeypatch.setattr("src.content.story_context.firecrawl_scrape_markdown", fake_scrape)

    digest, paths, primary, notes = build_script_context(
        topic_tags=["toon"],
        source_titles=["seed"],
        stored_firecrawl_key="k",
        firecrawl_enabled=True,
        want_web=True,
        want_refs=False,
        out_dir=tmp_path,
        video_format="cartoon",
    )
    assert "Meme / viral supplement" in digest
    # primary query + 2 supplement searches = 3 Firecrawl search calls
    assert len(calls) >= 3
    assert "meme" in calls[0].lower() or "viral" in calls[0].lower()


def test_build_script_context_news_one_search(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[str] = []

    def fake_search(q: str, *, limit: int, api_key: str):
        calls.append(q)
        return [{"title": "N", "url": "https://news.example/a", "source": "x"}]

    def fake_scrape(url: str, *, api_key: str, timeout_s: int = 60):
        return "body"

    monkeypatch.setattr("src.content.story_context.firecrawl_search_news", fake_search)
    monkeypatch.setattr("src.content.story_context.firecrawl_scrape_markdown", fake_scrape)

    build_script_context(
        topic_tags=["AI"],
        source_titles=["h"],
        stored_firecrawl_key="k",
        firecrawl_enabled=True,
        want_web=True,
        want_refs=False,
        out_dir=tmp_path,
        video_format="news",
    )
    assert len(calls) == 1
