from __future__ import annotations

from src.content.brain import ScriptSegment, VideoPackage
from src.content.story_pipeline import (
    SCRIPT_MIN_SEGMENTS,
    SCRIPT_MIN_TOTAL_WORDS,
    all_video_formats_have_refinement_stages,
    narration_word_count,
    package_to_json_text,
    refinement_stage_ids_for_format,
)
from src.core.config import VIDEO_FORMATS


def test_all_video_formats_have_non_empty_refinement_stages() -> None:
    assert all_video_formats_have_refinement_stages()
    for vf in VIDEO_FORMATS:
        ids = refinement_stage_ids_for_format(vf)
        assert "elaboration" in ids
        assert len(ids) >= 3


def test_narration_word_count_counts_hook_segments_cta() -> None:
    pkg = VideoPackage(
        title="t",
        description="d",
        hashtags=["#a"],
        hook="one two",
        segments=[ScriptSegment(narration="three four five", visual_prompt="v", on_screen_text=None)],
        cta="six",
    )
    assert narration_word_count(pkg) == 6


def test_package_to_json_text_roundtrip_shape() -> None:
    pkg = VideoPackage(
        title="T",
        description="D",
        hashtags=["#x"],
        hook="h",
        segments=[ScriptSegment(narration="n", visual_prompt="vp", on_screen_text="os")],
        cta="c",
    )
    s = package_to_json_text(pkg)
    assert "hook" in s and "segments" in s and "vp" in s


def test_script_min_thresholds_sane() -> None:
    assert SCRIPT_MIN_TOTAL_WORDS >= 120
    assert SCRIPT_MIN_SEGMENTS >= 6
