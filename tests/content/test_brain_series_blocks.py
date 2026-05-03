from __future__ import annotations

import src.content.brain as brain_mod


def test_series_continuity_empty_omitted_from_prompt(monkeypatch):
    captured: dict[str, str] = {}

    def fake_infer(model_id: str, prompt: str, **kwargs):
        captured["prompt"] = prompt
        return (
            '{"title":"T","description":"D","hashtags":["#A"],"hook":"H",'
            '"segments":[{"narration":"N","visual_prompt":"V","on_screen_text":"O"}],"cta":"C"}'
        )

    monkeypatch.setattr(brain_mod, "_infer_text_with_optional_holder", fake_infer)
    brain_mod.generate_script(
        model_id="x",
        items=[{"title": "Headline", "url": "u", "source": "s"}],
        video_format="news",
        previous_episode_summary="",
        series_bible="",
    )
    assert "Previous episode recap" not in captured["prompt"]
    assert "Series bible" not in captured["prompt"]


def test_series_continuity_inserts_recap_and_bible(monkeypatch):
    captured: dict[str, str] = {}

    def fake_infer(model_id: str, prompt: str, **kwargs):
        captured["prompt"] = prompt
        return (
            '{"title":"T","description":"D","hashtags":["#A"],"hook":"H",'
            '"segments":[{"narration":"N","visual_prompt":"V","on_screen_text":"O"}],"cta":"C"}'
        )

    monkeypatch.setattr(brain_mod, "_infer_text_with_optional_holder", fake_infer)
    brain_mod.generate_script(
        model_id="x",
        items=[{"title": "Headline", "url": "u", "source": "s"}],
        video_format="news",
        previous_episode_summary="Previously the hero escaped.",
        series_bible="### Episode 1\n\nOld recap.",
    )
    assert "Previous episode recap" in captured["prompt"]
    assert "Previously the hero escaped" in captured["prompt"]
    assert "Series bible" in captured["prompt"]
    assert "### Episode 1" in captured["prompt"]


def test_series_continuity_block_helper():
    from src.content.brain import _previous_episode_block, _series_bible_block, _series_continuity_block

    assert _previous_episode_block("") == ""
    assert "Previous episode recap" in _previous_episode_block("abc")
    assert _series_bible_block("") == ""
    assert "Series bible" in _series_bible_block("xyz")

    assert _series_continuity_block(previous_episode_summary="", series_bible="") == ""
    assert "Previous episode recap" in _series_continuity_block(
        previous_episode_summary="abc", series_bible=""
    )
    assert "Series bible" in _series_continuity_block(previous_episode_summary="", series_bible="xyz")
