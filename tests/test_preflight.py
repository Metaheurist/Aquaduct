from __future__ import annotations

from src.core.config import AppSettings, VideoSettings
from src.runtime.preflight import preflight_check


def test_preflight_invalid_fps(monkeypatch):
    # Pretend ffmpeg exists
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    s = AppSettings(video=VideoSettings(fps=999))
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("Invalid FPS" in e for e in r.errors)


def test_preflight_strict_requires_ffmpeg(monkeypatch):
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: None)  # type: ignore[arg-type]
    # Also don't fail imports in this test
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    r = preflight_check(settings=AppSettings(), strict=True)
    assert not r.ok
    assert any("FFmpeg is not under" in e for e in r.errors)


def test_preflight_watermark_requires_existing_file(monkeypatch, tmp_path):
    import src.runtime.preflight as pf
    from src.core.config import BrandingSettings

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])

    branding = BrandingSettings(watermark_enabled=True, watermark_path=str(tmp_path / "nope.png"))
    s = AppSettings(branding=branding)
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("Watermark logo file not found" in e for e in r.errors)

