from __future__ import annotations

from src.content.brain import ScriptSegment, VideoPackage
from src.content.characters_store import Character
from src.content.storyboard import build_storyboard


def test_build_storyboard_prepends_subject_tokens_before_visual_style():
    pkg = VideoPackage(
        title="T",
        description="",
        hashtags=[],
        hook="",
        segments=[
            ScriptSegment(narration="hello world beat one", visual_prompt="desk"),
            ScriptSegment(narration="two", visual_prompt="city"),
        ],
        cta="",
    )
    ch = Character(
        id="c" * 16,
        name="Host",
        visual_style="neon cartoon",
        gender="woman",
        ethnicity="East Asian",
        age_range="late 20s",
    )
    sb = build_storyboard(pkg, seed_base=10, character=ch, video_format="news")
    base = sb.scenes[0].prompt.split("\n")[0]
    assert "woman" in base
    assert "East Asian" in base
    assert "late 20s" in base or "age late 20s" in base
    assert "neon cartoon" in base


def test_build_storyboard_prepends_tokens_when_visual_style_empty():
    """Identity tokens still anchor prompts when the user hasn't filled Visual style yet."""
    pkg = VideoPackage(
        title="T3",
        description="",
        hashtags=[],
        hook="",
        segments=[ScriptSegment(narration="n", visual_prompt="outdoor")],
        cta="",
    )
    ch = Character(
        id="e" * 16,
        name="Solo",
        visual_style="",
        gender="non-binary presenter",
        ethnicity="",
        age_range="30s",
    )
    sb = build_storyboard(pkg, seed_base=3, character=ch, video_format="news")
    base = sb.scenes[0].prompt.split("\n")[0]
    assert "non-binary" in base
    assert "30s" in base or "age 30s" in base
    assert "outdoor" in base


def test_build_storyboard_skips_extra_token_prefix_for_merged_cast_name():
    pkg = VideoPackage(
        title="T2",
        description="",
        hashtags=[],
        hook="",
        segments=[ScriptSegment(narration="n", visual_prompt="v")],
        cta="",
    )
    ch = Character(
        id="d" * 16,
        name="Cast: Lead +1",
        visual_style="tok1, style1 | tok2, style2",
        gender="woman",
    )
    sb = build_storyboard(pkg, seed_base=1, character=ch, video_format="news")
    p0 = sb.scenes[0].prompt.split("\n")[0]
    assert p0.startswith("tok1") or "tok1" in p0
