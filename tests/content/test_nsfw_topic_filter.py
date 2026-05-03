from __future__ import annotations

import pytest

from src.content.crawler import _extra_creative_firecrawl_queries
from src.content.nsfw_guardrails import nsfw_text_matches_denylist
from src.content.topic_discovery import _should_discard_creative_candidate


def test_nsfw_denylist_matches_minor_related_terms():
    assert nsfw_text_matches_denylist("weekly teen style roundup")
    assert nsfw_text_matches_denylist("documentary about child actors")
    assert not nsfw_text_matches_denylist("adult industry trade publication")


def test_nsfw_denylist_skipped_when_session_guardrail_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.content.nsfw_guardrails as ng

    monkeypatch.setattr(ng, "dev_content_guardrails_disabled", lambda: True)
    assert not nsfw_text_matches_denylist("weekly teen style roundup")


def test_nsfw_extra_firecrawl_queries_returns_expected_count():
    qs = _extra_creative_firecrawl_queries("nsfw", ["studio", "awards"])
    assert len(qs) >= 3
    blob = " ".join(qs).lower()
    assert "adult" in blob or "industry" in blob


def test_nsfw_topic_discovery_discards_flagged_candidates():
    assert _should_discard_creative_candidate("weekly teen influencer roundup", "nsfw")
    assert not _should_discard_creative_candidate("industry trade interview with performer studio", "nsfw")
