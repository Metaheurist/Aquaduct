"""NSFW guardrails, topic filter / discovery, prompt branches, and library import hygiene."""

from __future__ import annotations

import pytest

from src.content.brain import _prompt_for_items
from src.content.crawler import _extra_creative_firecrawl_queries
from src.content.nsfw_guardrails import nsfw_text_matches_denylist
from src.content.personalities import get_personality_by_id
from src.content.topic_discovery import _should_discard_creative_candidate


def test_nsfw_denylist_matches_minor_related_terms():
    assert nsfw_text_matches_denylist("weekly teen style roundup")
    assert nsfw_text_matches_denylist("documentary about child actors")
    assert not nsfw_text_matches_denylist("adult industry trade publication")


def test_nsfw_denylist_skipped_when_session_guardrail_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.content.nsfw.guardrails.dev_content_guardrails_disabled",
        lambda: True,
    )
    assert not nsfw_text_matches_denylist("weekly teen style roundup")


def test_nsfw_extra_firecrawl_queries_returns_expected_count():
    qs = _extra_creative_firecrawl_queries("nsfw", ["studio", "awards"])
    assert len(qs) >= 3
    blob = " ".join(qs).lower()
    assert "adult" in blob or "industry" in blob


def test_nsfw_topic_discovery_discards_flagged_candidates():
    assert _should_discard_creative_candidate("weekly teen influencer roundup", "nsfw")
    assert not _should_discard_creative_candidate("industry trade interview with performer studio", "nsfw")


def test_prompt_for_items_nsfw_branch_includes_guardrails():
    p = get_personality_by_id("neutral")
    out = _prompt_for_items(
        [{"title": "Trade piece", "url": "https://example.com/a", "source": "Firecrawl"}],
        ["performers"],
        p,
        video_format="nsfw",
    )
    assert "NON-NEGOTIABLE" in out
    assert "adults-only" in out.lower() or "consent-positive" in out.lower()


def test_prompt_for_items_nsfw_branch_omits_guardrails_when_session_guardrail_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.content.nsfw.guardrails.dev_content_guardrails_disabled",
        lambda: True,
    )
    p = get_personality_by_id("neutral")
    out = _prompt_for_items(
        [{"title": "Trade piece", "url": "https://example.com/a", "source": "Firecrawl"}],
        ["performers"],
        p,
        video_format="nsfw",
    )
    assert "NON-NEGOTIABLE" not in out


def test_nsfw_llm_guardrails_block_is_non_empty():
    """Brain prompts can include the shared adults-only guardrail copy."""
    from src.content.nsfw_guardrails import nsfw_llm_guardrails_block

    blk = nsfw_llm_guardrails_block()
    assert isinstance(blk, str)
    assert len(blk) > 40
