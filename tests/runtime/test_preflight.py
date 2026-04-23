from __future__ import annotations

import pytest

from src.core.config import AppSettings, VideoSettings
from src.runtime.preflight import local_hf_model_snapshot_errors, preflight_check


@pytest.fixture(autouse=True)
def _local_hf_snapshots_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default local tests assume Hub snapshots exist (avoid disk-dependent failures)."""
    monkeypatch.setattr(
        "src.runtime.preflight.model_has_local_snapshot",
        lambda rid, models_dir=None, min_bytes=None: True,
    )


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


def test_preflight_pro_requires_video_model(monkeypatch):
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    v = VideoSettings(use_image_slideshow=False, pro_mode=True, pro_clip_seconds=4.0)
    s = AppSettings(video=v, video_model_id="")
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("Pro mode requires a Video" in e for e in r.errors)


def test_preflight_pro_allows_svd_img2vid(monkeypatch):
    """Pro + SVD is valid: keyframes come from the image model, then img2vid in the pipeline."""
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    v = VideoSettings(use_image_slideshow=False, pro_mode=True, pro_clip_seconds=4.0)
    s = AppSettings(video=v, video_model_id="stabilityai/stable-video-diffusion-img2vid-xt")
    r = preflight_check(settings=s, strict=True)
    assert r.ok
    assert not any("stable video diffusion" in e.lower() for e in r.errors)


def test_preflight_pro_disables_slideshow(monkeypatch):
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    v = VideoSettings(use_image_slideshow=True, pro_mode=True, pro_clip_seconds=4.0)
    s = AppSettings(video=v, video_model_id="cerspense/zeroscope_v2_576w")
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("disables slideshow" in e.lower() for e in r.errors)


def test_preflight_local_explicit_matches_default(monkeypatch):
    """Regression: explicit ``model_execution_mode='local'`` should not add API-only checks."""
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: None)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    r0 = preflight_check(settings=AppSettings(), strict=True)
    r1 = preflight_check(settings=AppSettings(model_execution_mode="local"), strict=True)
    assert r0.ok is r1.ok
    assert r0.errors == r1.errors


def test_preflight_api_mode_requires_keys(monkeypatch):
    import src.runtime.preflight as pf
    from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    s = AppSettings(
        model_execution_mode="api",
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
            image=ApiRoleConfig(provider="openai", model="dall-e-3"),
            video=ApiRoleConfig(),
            voice=ApiRoleConfig(provider="openai", model="tts-1"),
        ),
    )
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("api key" in e.lower() or "configure" in e.lower() for e in r.errors)


def test_preflight_api_mode_pro_requires_replicate(monkeypatch):
    import src.runtime.preflight as pf
    from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings, VideoSettings

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    v = VideoSettings(use_image_slideshow=False, pro_mode=True, pro_clip_seconds=4.0)
    s = AppSettings(
        model_execution_mode="api",
        video=v,
        api_openai_key="x",
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="openai", model="m"),
            image=ApiRoleConfig(provider="openai", model="m"),
            video=ApiRoleConfig(provider="openai", model="m"),
            voice=ApiRoleConfig(provider="openai", model="m"),
        ),
    )
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("replicate" in e.lower() for e in r.errors)


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


def test_preflight_local_missing_hf_snapshot(monkeypatch):
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr("src.runtime.preflight.model_has_local_snapshot", lambda *a, **k: False)
    r = preflight_check(settings=AppSettings(), strict=True)
    assert not r.ok
    assert any("not downloaded" in e.lower() for e in r.errors)


def test_local_hf_snapshot_errors_skipped_in_api_mode():
    s = AppSettings(model_execution_mode="api")
    assert local_hf_model_snapshot_errors(s) == []


def test_local_hf_snapshot_errors_photo_mode_ignores_video_voice(monkeypatch):
    monkeypatch.setattr("src.runtime.preflight.model_has_local_snapshot", lambda *a, **k: True)
    s = AppSettings(media_mode="photo", video_model_id="", voice_model_id="")
    assert local_hf_model_snapshot_errors(s) == []

