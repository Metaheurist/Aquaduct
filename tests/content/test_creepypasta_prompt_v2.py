"""Phase 3/7 tests for the tightened ``_prompt_for_creepypasta_items`` prompt.

After the ``Two_Sentenced_Horror_Stories`` run produced empty visual prompts,
the creepypasta prompt was tightened to:

- explicitly mark topic tags as a HARD constraint (Phase 6 alignment),
- require BOTH ``narration`` AND ``visual_prompt`` per segment with an explicit
  warning that an empty ``visual_prompt`` makes the segment unusable, and
- demand a campfire / first-person narrator voice instead of a "peppy news
  host" so personality/branding fusion can't accidentally pivot the tone.

These tests pin the prompt's structural commitments without locking the exact
wording. They run in isolation -- no LLM, no torch.
"""
from __future__ import annotations

from src.content import brain
from src.content.personalities import get_personality_presets


def default_personality():
    return get_personality_presets()[0]


def _build_prompt(tags: list[str] | None = None, *, character_context: str | None = None) -> str:
    headlines = [
        {"title": "The hallway lights flicker once a night", "url": "https://example.com/a"},
        {"title": "We never noticed the third bedroom door", "url": "https://example.com/b"},
    ]
    return brain._prompt_for_creepypasta_items(
        headlines,
        tags or [],
        default_personality(),
        None,
        character_context=character_context,
        article_excerpt="A two-sentence horror about a hallway.",
        video_format="creepypasta",
    )


def test_creepypasta_prompt_marks_topic_tags_as_hard_constraint() -> None:
    out = _build_prompt(["urban_legend", "haunted_house"])
    assert "HARD constraint" in out
    assert "urban_legend" in out
    assert "haunted_house" in out


def test_creepypasta_prompt_includes_visual_prompt_required_warning() -> None:
    out = _build_prompt(["forest"])
    lower = out.lower()
    assert "visual_prompt" in lower
    assert "unusable" in lower or "do not skip it" in lower


def test_creepypasta_prompt_locks_first_person_campfire_voice() -> None:
    out = _build_prompt([])
    lower = out.lower()
    assert "first-person past-tense" in lower
    assert "campfire" in lower
    assert "peppy news host" in lower


def test_creepypasta_prompt_strict_json_envelope() -> None:
    out = _build_prompt([])
    assert "Output STRICT JSON" in out
    assert "narration" in out
    assert "visual_prompt" in out


def test_creepypasta_prompt_includes_arc_skeleton() -> None:
    out = _build_prompt([])
    lower = out.lower()
    for beat in ("hook", "rising dread", "twist / reveal", "aftershock"):
        assert beat in lower, f"missing arc beat: {beat}"


def test_creepypasta_prompt_omits_topic_block_when_no_tags() -> None:
    out = _build_prompt([])
    assert "topic tags (HARD constraint" not in out.lower()
