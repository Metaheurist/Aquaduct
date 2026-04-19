from __future__ import annotations

import json

import pytest


def test_news_seen_paths_matches_video_format_keys(tmp_path) -> None:
    from src.crawler import news_seen_paths

    d = tmp_path / "news_cache"
    seen, titles = news_seen_paths(d, "cartoon")
    assert seen.name == "seen_cartoon.json"
    assert titles.name == "seen_titles_cartoon.json"
    assert seen.parent == d


def test_default_cache_mode_reads_legacy_seen_for_news(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Omitted `cache_mode` defaults to news and migrates from flat `seen.json`."""
    from src.crawler import NewsItem, get_latest_items

    news_cache = tmp_path / "news_cache"
    news_cache.mkdir(parents=True)
    u = "https://example.com/legacy"
    (news_cache / "seen.json").write_text(json.dumps([u]), encoding="utf-8")

    monkeypatch.setattr(
        "src.crawler._fetch_headlines",
        lambda **_kw: [
            NewsItem(title="T", url=u, source="GoogleNews"),
            NewsItem(title="T2", url="https://example.com/n2", source="GoogleNews"),
        ],
    )

    out = get_latest_items(news_cache, limit=3)
    assert len(out) == 1
    assert out[0].url == "https://example.com/n2"


def test_explainer_mode_never_reads_legacy_seen(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from src.crawler import NewsItem, get_latest_items

    news_cache = tmp_path / "news_cache"
    news_cache.mkdir(parents=True)
    u = "https://example.com/in-legacy-only"
    (news_cache / "seen.json").write_text(json.dumps([u]), encoding="utf-8")

    monkeypatch.setattr(
        "src.crawler._fetch_headlines",
        lambda **_kw: [NewsItem(title="T", url=u, source="GoogleNews")],
    )

    out = get_latest_items(news_cache, limit=2, cache_mode="explainer")
    assert len(out) == 1
    assert out[0].url == u
    assert (news_cache / "seen_explainer.json").exists()


def test_per_mode_seen_isolates_from_legacy_news(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from src.crawler import NewsItem, get_latest_items

    news_cache = tmp_path / "news_cache"
    news_cache.mkdir(parents=True)
    legacy_url = "https://example.com/already-seen"
    (news_cache / "seen.json").write_text(json.dumps([legacy_url]), encoding="utf-8")

    def fake_fetch(**_kw):
        return [
            NewsItem(title="Old", url=legacy_url, source="GoogleNews"),
            NewsItem(title="New", url="https://example.com/fresh", source="GoogleNews"),
        ]

    monkeypatch.setattr("src.crawler._fetch_headlines", fake_fetch)

    cartoon = get_latest_items(news_cache, limit=3, cache_mode="cartoon")
    assert len(cartoon) == 2

    news = get_latest_items(news_cache, limit=3, cache_mode="news")
    assert len(news) == 1
    assert news[0].url == "https://example.com/fresh"
    assert (news_cache / "seen_news.json").exists()


def test_legacy_seen_titles_migrates_for_news_scored(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from src.crawler import NewsItem, get_scored_items

    news_cache = tmp_path / "news_cache"
    news_cache.mkdir(parents=True)
    (news_cache / "seen_titles.json").write_text(json.dumps(["Previous headline about X"]), encoding="utf-8")

    raw = [
        NewsItem(title="Previous headline about X", url="https://a.example/u1", source="GoogleNews"),
        NewsItem(title="Totally different story", url="https://b.example/u2", source="GoogleNews"),
    ]

    monkeypatch.setattr("src.crawler.fetch_latest_items", lambda **_kw: raw)
    monkeypatch.setattr("src.content_quality.diversify", lambda ranked, **_kw: ranked)

    get_scored_items(news_cache, limit=1, fetch_n=2, cache_mode="news")
    # Titles persisted to per-mode file
    st = news_cache / "seen_titles_news.json"
    assert st.exists()
    data = json.loads(st.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 1


def test_cartoon_scored_uses_separate_seen_titles(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Non-news modes do not load legacy `seen_titles.json`."""
    from src.crawler import NewsItem, get_scored_items

    news_cache = tmp_path / "news_cache"
    news_cache.mkdir(parents=True)
    (news_cache / "seen_titles.json").write_text(json.dumps(["Legacy title noise"]), encoding="utf-8")

    raw = [NewsItem(title="Legacy title noise", url="https://x.example/a", source="GoogleNews")]

    monkeypatch.setattr("src.crawler.fetch_latest_items", lambda **_kw: raw)
    monkeypatch.setattr("src.content_quality.diversify", lambda ranked, **_kw: ranked)

    get_scored_items(news_cache, limit=1, fetch_n=1, cache_mode="cartoon")
    path = news_cache / "seen_titles_cartoon.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "Legacy title noise" in saved


def test_unhinged_scored_persist_cache_false_skips_disk(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from src.crawler import NewsItem, get_scored_items

    news_cache = tmp_path / "news_cache"
    news_cache.mkdir(parents=True)

    raw = [
        NewsItem(title="Headline A", url="https://a.example/u1", source="GoogleNews"),
        NewsItem(title="Headline B", url="https://b.example/u2", source="GoogleNews"),
    ]

    monkeypatch.setattr("src.crawler.fetch_latest_items", lambda **_kw: raw)
    monkeypatch.setattr("src.content_quality.diversify", lambda ranked, **_kw: ranked)

    get_scored_items(news_cache, limit=1, fetch_n=2, cache_mode="unhinged", persist_cache=False)
    assert not any(news_cache.glob("seen*.json"))
    assert not any(news_cache.glob("seen_titles*.json"))


def test_clear_news_seen_cache_files_removes_legacy_and_per_mode(tmp_path) -> None:
    from src.crawler import clear_news_seen_cache_files

    d = tmp_path / "news_cache"
    d.mkdir(parents=True)
    (d / "seen.json").write_text("[]", encoding="utf-8")
    (d / "seen_titles.json").write_text("[]", encoding="utf-8")
    (d / "seen_news.json").write_text("[]", encoding="utf-8")
    (d / "seen_titles_cartoon.json").write_text("[]", encoding="utf-8")
    (d / "other_cache.json").write_text("{}", encoding="utf-8")

    n = clear_news_seen_cache_files(d)
    assert n == 4
    assert not (d / "seen.json").exists()
    assert (d / "other_cache.json").exists()


def test_effective_query_mode_tailors_search_bias() -> None:
    from src.crawler import _default_headline_query, _effective_query

    n = _effective_query(query="", topic_tags=["Acme"], topic_mode="news")
    assert "Acme" in n and ("AI" in n or "ai" in n)

    c = _effective_query(query="", topic_tags=["slapstick"], topic_mode="cartoon")
    assert "slapstick" in c
    assert "AI tool" not in c
    assert "animation" in c.lower() or "cartoon" in c.lower()

    e = _effective_query(query="", topic_tags=["physics"], topic_mode="explainer")
    assert "physics" in e
    assert "AI" in e or "ai" in e
    assert "tutorial" not in e.lower()

    u = _effective_query(query="", topic_tags=["sketch"], topic_mode="unhinged")
    assert "sketch" in u
    assert "viral" in u.lower() or "meme" in u.lower() or "trending" in u.lower()

    assert "AI tool" in _default_headline_query("news") or "AI" in _default_headline_query("news")
    assert _default_headline_query("explainer") == _default_headline_query("news")
    cdef = _default_headline_query("cartoon").lower()
    assert "premiere" in cdef or "trailer" in cdef or "animation" in cdef
    assert "tutorial" not in cdef
    uh_def = _default_headline_query("unhinged").lower()
    assert "viral" in uh_def or "meme" in uh_def or "internet culture" in uh_def


def test_clear_news_seen_cache_files_empty_dir(tmp_path) -> None:
    from src.crawler import clear_news_seen_cache_files

    d = tmp_path / "news_cache"
    d.mkdir(parents=True)
    assert clear_news_seen_cache_files(d) == 0
