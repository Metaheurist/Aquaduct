"""Pro-mode scene prompt splitting (Phase 4: title prefix dropped, genre cues + cast injection)."""

from src.content.brain import ScriptSegment, VideoPackage

from main import _split_into_pro_scenes_from_script


def test_pro_scenes_news_no_longer_prefixes_headline() -> None:
    """Phase 4: T2V prompts no longer begin with the article title verbatim.

    CLIP-class T2V encoders treat the title as a literal text-rendering request,
    which collapses every clip into the same shot. The headline now lives in
    branding overlays only.
    """
    pkg = VideoPackage(
        title="Top 10 Widgets — Blog",
        description="",
        hashtags=[],
        hook="Hook line",
        segments=[ScriptSegment(narration="First beat about widgets.", visual_prompt="v", on_screen_text="")],
        cta="Subscribe",
    )
    scenes = _split_into_pro_scenes_from_script(pkg=pkg, prompts=["v"], video_format="news")
    assert scenes
    for s in scenes:
        assert "Top 10 Widgets" not in s
        assert " | " not in s.split(",")[0]


def test_pro_scenes_cartoon_omits_headline_prefix() -> None:
    pkg = VideoPackage(
        title="Top 10 Sketch Comedy Shows - Entertainment Junkie Blog",
        description="",
        hashtags=[],
        hook="This headline showed up uninvited.",
        segments=[ScriptSegment(narration="I'm telling you right now.", visual_prompt="v", on_screen_text="")],
        cta="Follow for more.",
    )
    scenes = _split_into_pro_scenes_from_script(pkg=pkg, prompts=["v"], video_format="cartoon")
    assert scenes
    for s in scenes:
        assert "Top 10 Sketch Comedy" not in s
        assert "Entertainment Junkie" not in s
