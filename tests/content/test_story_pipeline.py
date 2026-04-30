from __future__ import annotations

from src.content.brain import ScriptSegment, VideoPackage, video_package_from_llm_output
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


def test_video_package_from_llm_output_skips_prologue_before_json() -> None:
    raw = (
        'Sure — here is the rewrite:\n{"title": "T", "description": "D", "hashtags": ["#x"], '
        '"hook": "h", "segments": [{"narration": "n", "visual_prompt": "v", "on_screen_text": null}], '
        '"cta": "c"}\nLet me know if you need tweaks.'
    )
    pkg = video_package_from_llm_output(raw)
    assert pkg.title == "T"
    assert pkg.hook == "h"


def test_video_package_from_llm_output_balanced_braces_in_strings() -> None:
    raw = (
        '{"title": "T", "description": "D", "hashtags": ["#x"], '
        '"hook": "brace literal { ok }", '
        '"segments": [{"narration": "n", "visual_prompt": "v", "on_screen_text": null}], '
        '"cta": "c"}'
    )
    pkg = video_package_from_llm_output(raw)
    assert "{ ok }" in pkg.hook
