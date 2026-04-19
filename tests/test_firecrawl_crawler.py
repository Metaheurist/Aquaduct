from __future__ import annotations

import pytest


def test_fetch_latest_prefers_firecrawl_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.content.crawler import fetch_latest_items

    def fake_fc(q: str, *, limit: int, api_key: str, timeout_s: int = 60):
        assert api_key == "k"
        return [
            {
                "title": "FC headline",
                "url": "https://fc.example/a",
                "source": "Firecrawl",
                "published_at": None,
            }
        ]

    def boom_rss(**_kw):
        raise AssertionError("RSS should not run when Firecrawl fills the quota")

    monkeypatch.setattr("src.content.firecrawl_news.firecrawl_search_news", fake_fc)
    monkeypatch.setattr("src.content.crawler._google_news_rss", boom_rss)
    out = fetch_latest_items(limit=1, firecrawl_enabled=True, firecrawl_api_key="k")
    assert len(out) == 1
    assert out[0].source == "Firecrawl"
    assert "fc.example" in out[0].url


def test_fetch_latest_falls_back_to_rss_when_firecrawl_returns_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.content.crawler import NewsItem, fetch_latest_items

    def fake_fc(*_a, **_k):
        return []

    def rss(**kw):
        return [
            NewsItem(title="RSS", url="https://news.example/x", source="GoogleNews", published_at=None),
        ]

    monkeypatch.setattr("src.content.firecrawl_news.firecrawl_search_news", fake_fc)
    monkeypatch.setattr("src.content.crawler._google_news_rss", rss)
    monkeypatch.setattr("src.content.crawler._marktechpost_latest", lambda **_k: [])
    out = fetch_latest_items(limit=2, firecrawl_enabled=True, firecrawl_api_key="k")
    assert len(out) >= 1
    assert out[0].source == "GoogleNews"


def test_fetch_article_text_falls_back_when_firecrawl_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.content.crawler import fetch_article_text

    monkeypatch.setattr("src.content.firecrawl_news.resolve_firecrawl_api_key", lambda _s: "key")
    monkeypatch.setattr("src.content.firecrawl_news.firecrawl_scrape_markdown", lambda *_a, **_k: "")

    class Resp:
        text = "<html><body><article>Hello from html</article></body></html>"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("src.content.crawler.requests.get", lambda *_a, **_k: Resp())
    txt = fetch_article_text("https://example.com/x", firecrawl_enabled=True, firecrawl_api_key="k")
    assert "Hello from html" in txt


def test_resolve_firecrawl_api_key_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.content.firecrawl_news import resolve_firecrawl_api_key

    monkeypatch.setenv("FIRECRAWL_API_KEY", "from-env")
    assert resolve_firecrawl_api_key("from-ui") == "from-env"
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    assert resolve_firecrawl_api_key("from-ui") == "from-ui"

