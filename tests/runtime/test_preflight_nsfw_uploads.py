from __future__ import annotations

import pytest

from src.core.config import AppSettings, VideoSettings
from src.runtime.preflight import preflight_check


@pytest.fixture(autouse=True)
def _local_hf_snapshots_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.runtime.preflight.model_has_local_snapshot",
        lambda rid, models_dir=None, min_bytes=None: True,
    )


@pytest.fixture(autouse=True)
def _stub_no_cpu_torch_gpu_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.models.torch_install.pytorch_cpu_wheel_with_nvidia_gpu_present",
        lambda: False,
    )


def test_preflight_nsfw_rejects_tiktok_auto_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "is_api_mode", lambda _s: False)
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr(pf, "local_hf_model_snapshot_errors", lambda _settings: [])
    s = AppSettings(
        video_format="nsfw",
        tiktok_auto_upload_after_render=True,
        youtube_auto_upload_after_render=False,
    )
    r = preflight_check(settings=s, strict=True)
    assert not r.ok
    assert any("NSFW preset" in e for e in r.errors)


def test_preflight_nsfw_skips_upload_and_safety_warnings_when_session_guardrail_bypass_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "is_api_mode", lambda _s: False)
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr(pf, "local_hf_model_snapshot_errors", lambda _settings: [])
    monkeypatch.setenv("AQUADUCT_DEV_DISABLE_CONTENT_GUARDRAILS", "1")
    s = AppSettings(
        video_format="nsfw",
        tiktok_auto_upload_after_render=True,
        youtube_auto_upload_after_render=True,
        video=VideoSettings(),
    )
    r = preflight_check(settings=s, strict=True)
    assert r.ok
    assert not any("NSFW preset" in e for e in r.errors)
    assert not any("safety checker" in w for w in r.warnings)


def test_preflight_nsfw_warns_on_allow_nsfw_effective(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "is_api_mode", lambda _s: False)
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr(pf, "local_hf_model_snapshot_errors", lambda _settings: [])
    s = AppSettings(video_format="nsfw", video=VideoSettings())
    r = preflight_check(settings=s, strict=True)
    assert r.ok
    assert any("NSFW video format" in w and "safety checker" in w for w in r.warnings)
