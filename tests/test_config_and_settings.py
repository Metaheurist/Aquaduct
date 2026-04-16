from __future__ import annotations

from src.config import AppSettings, VideoSettings
from src.topics import effective_topic_tags, news_cache_mode_for_run
from src.ui_settings import load_settings, save_settings


def test_ui_settings_roundtrip_defaults(write_ui_settings):
    # Empty file -> defaults
    write_ui_settings({})
    s = load_settings()
    assert isinstance(s, AppSettings)
    assert s.personality_id == "auto"
    assert getattr(s, "active_character_id", "") == ""
    assert isinstance(s.video, VideoSettings)


def test_ui_settings_roundtrip_persist(tmp_repo_root, monkeypatch):
    from src import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "_root", lambda: tmp_repo_root)

    s = AppSettings(
        topic_tags_by_mode={"news": ["AI video editor", "agentic workflow"], "cartoon": [], "explainer": []},
        video_format="news",
        personality_id="analytical",
        llm_model_id="x",
        image_model_id="y",
        video_model_id="z",
        voice_model_id="v",
        background_music_path="C:\\music.mp3",
        video=VideoSettings(width=720, height=1280, fps=24, images_per_video=5, cleanup_images_after_run=True),
        elevenlabs_enabled=True,
        elevenlabs_api_key="el_test_key",
    )
    save_settings(s)
    s2 = load_settings()
    assert s2.personality_id == "analytical"
    assert s2.elevenlabs_enabled is True
    assert s2.elevenlabs_api_key == "el_test_key"
    assert s2.topic_tags_by_mode.get("news") == ["AI video editor", "agentic workflow"]
    assert s2.video_format == "news"
    assert s2.hf_api_enabled is True
    assert s2.firecrawl_enabled is False
    assert s2.firecrawl_api_key == ""
    assert s2.video.width == 720
    assert s2.video.height == 1280
    assert s2.video.fps == 24
    assert s2.video.images_per_video == 5
    assert s2.video.cleanup_images_after_run is True
    # Audio defaults/persistence should not break loading
    assert s2.video.audio_polish in {"off", "basic", "strong"}


def test_ui_settings_api_fields_roundtrip(tmp_repo_root, monkeypatch):
    from src import ui_settings as ui_mod
    from src.config import AppSettings

    monkeypatch.setattr(ui_mod, "_root", lambda: tmp_repo_root)
    s = AppSettings(
        hf_api_enabled=False,
        hf_token="hf_x",
        firecrawl_enabled=True,
        firecrawl_api_key="fc_y",
    )
    save_settings(s)
    s2 = load_settings()
    assert s2.hf_api_enabled is False
    assert s2.hf_token == "hf_x"
    assert s2.firecrawl_enabled is True
    assert s2.firecrawl_api_key == "fc_y"


def test_ui_settings_migrates_legacy_topic_tags_to_news(tmp_repo_root, monkeypatch):
    from src import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "_root", lambda: tmp_repo_root)
    p = tmp_repo_root / "ui_settings.json"
    p.write_text('{"topic_tags": ["legacy"], "personality_id": "auto"}', encoding="utf-8")
    s = load_settings()
    assert "legacy" in (s.topic_tags_by_mode.get("news") or [])


def test_effective_topic_tags_follows_video_format():
    s = AppSettings(
        topic_tags_by_mode={"news": ["n1"], "cartoon": ["c1", "c2"], "explainer": []},
        video_format="cartoon",
    )
    assert effective_topic_tags(s) == ["c1", "c2"]


def test_news_cache_mode_for_run_matches_video_format():
    assert news_cache_mode_for_run(AppSettings(video_format="cartoon")) == "cartoon"
    assert news_cache_mode_for_run(AppSettings(video_format="NEWS")) == "news"
    assert news_cache_mode_for_run(AppSettings(video_format="explainer")) == "explainer"


def test_news_cache_mode_for_run_unknown_defaults_to_news():
    assert news_cache_mode_for_run(AppSettings(video_format="")) == "news"
    # Invalid format string falls back to "news" per normalize_video_format
    assert news_cache_mode_for_run(AppSettings(video_format="not-a-mode")) == "news"

