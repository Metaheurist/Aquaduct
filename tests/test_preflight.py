from __future__ import annotations

from src.config import AppSettings, VideoSettings
from src.preflight import preflight_check


def test_preflight_invalid_fps(monkeypatch):
    # Pretend ffmpeg exists
    import src.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    s = AppSettings(topic_tags=[], video=VideoSettings(fps=999))
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("Invalid FPS" in e for e in r.errors)


def test_preflight_strict_requires_ffmpeg(monkeypatch):
    import src.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: None)  # type: ignore[arg-type]
    # Also don't fail imports in this test
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    r = preflight_check(settings=AppSettings(topic_tags=[]), strict=True)
    assert not r.ok
    assert any("FFmpeg is not installed" in e for e in r.errors)

