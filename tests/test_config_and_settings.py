from __future__ import annotations

from src.core.config import AppSettings, VideoSettings
from src.content.topics import (
    effective_topic_tags,
    news_cache_mode_for_run,
    normalize_video_format,
    video_format_is_creative_topics_mode,
    video_format_skips_seen_url_disk_cache,
    video_format_uses_news_style_sourcing,
)
from src.settings.ui_settings import load_settings, save_settings


def test_ui_settings_roundtrip_defaults(write_ui_settings):
    # Empty file -> defaults
    write_ui_settings({})
    s = load_settings()
    assert isinstance(s, AppSettings)
    assert s.personality_id == "auto"
    assert getattr(s, "active_character_id", "") == ""
    assert isinstance(s.video, VideoSettings)


def test_ui_settings_roundtrip_persist(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)

    s = AppSettings(
        topic_tags_by_mode={"news": ["AI video editor", "agentic workflow"], "cartoon": [], "explainer": []},
        video_format="news",
        personality_id="analytical",
        llm_model_id="x",
        image_model_id="y",
        video_model_id="z",
        voice_model_id="v",
        background_music_path="C:\\music.mp3",
        video=VideoSettings(
            width=720,
            height=1280,
            fps=24,
            images_per_video=5,
            pro_mode=True,
            pro_clip_seconds=5.5,
            cleanup_images_after_run=True,
            platform_preset_id="landscape_720p",
            effects_preset_id="effects_dynamic",
        ),
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
    assert s2.video.pro_mode is True
    assert abs(s2.video.pro_clip_seconds - 5.5) < 1e-6
    assert s2.video.cleanup_images_after_run is True
    assert s2.video.platform_preset_id == "landscape_720p"
    assert s2.video.effects_preset_id == "effects_dynamic"
    # Audio defaults/persistence should not break loading
    assert s2.video.audio_polish in {"off", "basic", "strong"}


def test_ui_settings_tutorial_completed_roundtrip(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)
    s = AppSettings(tutorial_completed=True)
    save_settings(s)
    s2 = load_settings()
    assert s2.tutorial_completed is True


def test_ui_settings_media_mode_roundtrip(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)
    s = AppSettings(media_mode="photo")  # type: ignore[arg-type]
    save_settings(s)
    s2 = load_settings()
    assert s2.media_mode == "photo"


def test_ui_settings_roundtrip_custom_video_fields(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)
    s = AppSettings(
        run_content_mode="custom",
        custom_video_instructions="First line topic\nMore detail for the LLM.",
    )
    save_settings(s)
    s2 = load_settings()
    assert s2.run_content_mode == "custom"
    assert "First line topic" in s2.custom_video_instructions


def test_ui_settings_api_fields_roundtrip(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod
    from src.core.config import AppSettings

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)
    s = AppSettings(
        hf_api_enabled=False,
        hf_token="hf_x",
        firecrawl_enabled=True,
        firecrawl_api_key="fc_y",
        allow_nsfw=True,
    )
    save_settings(s)
    s2 = load_settings()
    assert s2.hf_api_enabled is False
    assert s2.hf_token == "hf_x"
    assert s2.firecrawl_enabled is True
    assert s2.firecrawl_api_key == "fc_y"
    assert s2.allow_nsfw is True


def test_ui_settings_migrates_legacy_topic_tags_to_news(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)
    p = tmp_repo_root / "ui_settings.json"
    p.write_text('{"topic_tags": ["legacy"], "personality_id": "auto"}', encoding="utf-8")
    s = load_settings()
    assert "legacy" in (s.topic_tags_by_mode.get("news") or [])


def test_effective_topic_tags_follows_video_format():
    s = AppSettings(
        topic_tags_by_mode={"news": ["n1"], "cartoon": ["c1", "c2"], "explainer": [], "unhinged": ["u1"]},
        video_format="cartoon",
    )
    assert effective_topic_tags(s) == ["c1", "c2"]


def test_effective_topic_tags_unhinged():
    s = AppSettings(
        topic_tags_by_mode={"news": ["n1"], "cartoon": [], "explainer": [], "unhinged": ["meme", "sketch"]},
        video_format="unhinged",
    )
    assert effective_topic_tags(s) == ["meme", "sketch"]


def test_effective_topic_tags_creepypasta():
    s = AppSettings(
        topic_tags_by_mode={
            "news": ["n1"],
            "cartoon": [],
            "explainer": [],
            "unhinged": [],
            "creepypasta": ["nosleep", "liminal"],
        },
        video_format="creepypasta",
    )
    assert effective_topic_tags(s) == ["nosleep", "liminal"]


def test_video_format_uses_news_style_sourcing_only_news_and_explainer():
    assert video_format_uses_news_style_sourcing("news") is True
    assert video_format_uses_news_style_sourcing("explainer") is True
    assert video_format_uses_news_style_sourcing("cartoon") is False
    assert video_format_uses_news_style_sourcing("unhinged") is False
    assert video_format_uses_news_style_sourcing("creepypasta") is False


def test_news_cache_mode_for_run_matches_video_format():
    assert news_cache_mode_for_run(AppSettings(video_format="cartoon")) == "cartoon"
    assert news_cache_mode_for_run(AppSettings(video_format="NEWS")) == "news"
    assert news_cache_mode_for_run(AppSettings(video_format="explainer")) == "explainer"
    assert news_cache_mode_for_run(AppSettings(video_format="unhinged")) == "unhinged"
    assert news_cache_mode_for_run(AppSettings(video_format="creepypasta")) == "creepypasta"


def test_news_cache_mode_for_run_unknown_defaults_to_news():
    assert news_cache_mode_for_run(AppSettings(video_format="")) == "news"
    # Invalid format string falls back to "news" per normalize_video_format
    assert news_cache_mode_for_run(AppSettings(video_format="not-a-mode")) == "news"


def test_normalize_video_format_unhinged():
    assert normalize_video_format("UNHINGED") == "unhinged"
    assert normalize_video_format("unhinged") == "unhinged"


def test_normalize_video_format_creepypasta():
    assert normalize_video_format("CREEPYPASTA") == "creepypasta"
    assert normalize_video_format("creepypasta") == "creepypasta"


def test_video_format_pipeline_helpers_creepypasta():
    assert video_format_skips_seen_url_disk_cache("creepypasta") is True
    assert video_format_skips_seen_url_disk_cache("unhinged") is True
    assert video_format_skips_seen_url_disk_cache("news") is False
    assert video_format_is_creative_topics_mode("creepypasta") is True


def test_save_settings_calls_mark_hidden(tmp_repo_root, monkeypatch):
    from src.settings import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "application_data_dir", lambda: tmp_repo_root)
    called: list = []
    monkeypatch.setattr(ui_mod, "mark_path_hidden", lambda p: called.append(p))
    save_settings(AppSettings())
    assert len(called) == 1
    assert called[0] == tmp_repo_root / "ui_settings.json"

