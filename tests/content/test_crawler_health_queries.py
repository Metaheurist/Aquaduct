from __future__ import annotations

from src.content.crawler import _effective_query, _extra_creative_firecrawl_queries


def test_effective_query_health_advice_no_tags():
    q = _effective_query(query="", topic_tags=None, topic_mode="health_advice")
    ql = q.lower()
    assert "wellness" in ql or "nutrition" in ql or "sleep" in ql


def test_effective_query_health_advice_with_tags():
    q = _effective_query(query="", topic_tags=["diabetes", "walking"], topic_mode="health_advice")
    ql = q.lower()
    assert "diabetes" in ql or "walking" in ql
    assert "wellness" in ql or "health" in ql


def test_extra_creative_firecrawl_queries_health():
    qs = _extra_creative_firecrawl_queries("health_advice", ["sleep"])
    assert len(qs) == 4
    joined = " ".join(qs).lower()
    assert "sleep" in joined
    assert "wellness" in joined or "nutrition" in joined or "stress" in joined or "heart" in joined
