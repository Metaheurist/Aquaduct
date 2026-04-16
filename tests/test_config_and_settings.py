from __future__ import annotations

from src.config import AppSettings, VideoSettings
from src.ui_settings import load_settings, save_settings


def test_ui_settings_roundtrip_defaults(write_ui_settings):
    # Empty file -> defaults
    write_ui_settings({})
    s = load_settings()
    assert isinstance(s, AppSettings)
    assert s.personality_id == "auto"
    assert isinstance(s.video, VideoSettings)


def test_ui_settings_roundtrip_persist(tmp_repo_root, monkeypatch):
    from src import ui_settings as ui_mod

    monkeypatch.setattr(ui_mod, "_root", lambda: tmp_repo_root)

    s = AppSettings(
        topic_tags=["AI video editor", "agentic workflow"],
        personality_id="analytical",
        llm_model_id="x",
        image_model_id="y",
        video_model_id="z",
        voice_model_id="v",
        background_music_path="C:\\music.mp3",
        video=VideoSettings(width=720, height=1280, fps=24, images_per_video=5, cleanup_images_after_run=True),
    )
    save_settings(s)
    s2 = load_settings()
    assert s2.personality_id == "analytical"
    assert s2.video.width == 720
    assert s2.video.height == 1280
    assert s2.video.fps == 24
    assert s2.video.images_per_video == 5
    assert s2.video.cleanup_images_after_run is True
    # Audio defaults/persistence should not break loading
    assert s2.video.audio_polish in {"off", "basic", "strong"}

