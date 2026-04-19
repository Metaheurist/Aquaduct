"""Pro-mode scene prompt splitting (headline anchoring vs cartoon / unhinged)."""

from src.content.brain import ScriptSegment, VideoPackage

from main import _split_into_pro_scenes_from_script


def test_pro_scenes_news_prefixes_headline() -> None:
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
    assert all(s.startswith("Top 10 Widgets — Blog |") for s in scenes)


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
