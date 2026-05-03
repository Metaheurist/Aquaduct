from __future__ import annotations

import pytest

from src.content.brain import _prompt_for_items
from src.content.personalities import get_personality_by_id


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


def test_prompt_for_items_nsfw_branch_omits_guardrails_when_session_guardrail_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.content.nsfw_guardrails as ng

    monkeypatch.setattr(ng, "dev_content_guardrails_disabled", lambda: True)
    p = get_personality_by_id("neutral")
    out = _prompt_for_items(
        [{"title": "Trade piece", "url": "https://example.com/a", "source": "Firecrawl"}],
        ["performers"],
        p,
        video_format="nsfw",
    )
    assert "NON-NEGOTIABLE" not in out
