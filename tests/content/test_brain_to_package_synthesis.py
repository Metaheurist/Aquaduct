"""Phase 3: ``_to_package`` synthesizes ``visual_prompt`` instead of dropping segments.

Pre-Phase-3, segments missing either ``narration`` or ``visual_prompt`` were
silently filtered out — the ``Two_Sentenced_Horror_Stories`` artifacts in
``.Aquaduct_data/runs/.../pipeline_script_package.json`` showed exactly that
collapse, leaving a single placeholder beat which the storyboard then looped.

These tests pin the new synthesis behavior so the regression cannot return.
"""

from __future__ import annotations

from src.content.brain import (
    ScriptSegment,
    VideoPackage,
    _to_package,
    video_package_from_llm_output,
)


def test_segment_with_only_narration_gets_synthesized_visual_prompt() -> None:
    pkg = _to_package(
        {
            "title": "The Hum",
            "description": "Short fictional horror.",
            "hashtags": ["#horror"],
            "hook": "Something is wrong with our wallpaper.",
            "segments": [
                {
                    "narration": "I noticed the wallpaper was breathing again at 3:14 a.m.",
                    "on_screen_text": "3:14 A.M.",
                },
                {
                    "narration": "By morning every framed photograph faced the wall.",
                },
            ],
            "cta": "More fiction-only horror tomorrow.",
        },
        video_format="creepypasta",
    )
    assert isinstance(pkg, VideoPackage)
    assert len(pkg.segments) == 2
    for seg in pkg.segments:
        assert seg.narration.strip()
        assert seg.visual_prompt.strip()
        # Format-aware affix lands in the synthesized visual prompt.
        assert "horror" in seg.visual_prompt.lower() or "moody" in seg.visual_prompt.lower()


def test_segment_with_only_visual_prompt_gets_synthesized_narration() -> None:
    pkg = _to_package(
        {
            "title": "Quiet Hallway",
            "segments": [
                {
                    "visual_prompt": "long carpeted hallway, dim sconces, single open door at the far end",
                },
                {"narration": "and the door was always closed yesterday.", "visual_prompt": "doorknob trembling slightly"},
            ],
        },
        video_format="creepypasta",
    )
    assert len(pkg.segments) == 2
    assert pkg.segments[0].narration.strip()


def test_segments_with_both_empty_are_dropped() -> None:
    pkg = _to_package(
        {
            "title": "X",
            "segments": [
                {"narration": "", "visual_prompt": ""},
                {"narration": "She wouldn't enter the kitchen after sunset.", "visual_prompt": "kitchen at dusk"},
            ],
        },
        video_format="creepypasta",
    )
    assert len(pkg.segments) == 1
    assert pkg.segments[0].narration.startswith("She wouldn")


def test_video_package_from_llm_output_threads_video_format() -> None:
    raw = (
        '{"title":"T","description":"D","hashtags":["#x"],"hook":"h",'
        '"segments":[{"narration":"It came back wearing my smile."}],'
        '"cta":"c"}'
    )
    pkg = video_package_from_llm_output(raw, video_format="creepypasta")
    assert len(pkg.segments) == 1
    seg: ScriptSegment = pkg.segments[0]
    assert seg.visual_prompt.strip()
    assert "9:16" in seg.visual_prompt or "vertical" in seg.visual_prompt.lower()


def test_default_video_format_uses_generic_short_framing() -> None:
    pkg = _to_package(
        {
            "title": "T",
            "segments": [{"narration": "This is the story."}],
        }
    )
    assert pkg.segments[0].visual_prompt.strip()
    assert "9:16" in pkg.segments[0].visual_prompt or "vertical" in pkg.segments[0].visual_prompt.lower()


def test_synthesis_truncates_long_narration_into_visual_prompt() -> None:
    very_long = " ".join(["clue"] * 200)
    pkg = _to_package(
        {
            "title": "T",
            "segments": [{"narration": very_long}],
        },
        video_format="creepypasta",
    )
    assert pkg.segments[0].visual_prompt.endswith("…") or len(pkg.segments[0].visual_prompt) < 600
