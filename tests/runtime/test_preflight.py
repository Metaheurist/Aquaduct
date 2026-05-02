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


@pytest.fixture(autouse=True)
def _stub_no_cpu_torch_gpu_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI/dev machines may have NVIDIA drivers + CPU-only torch; unrelated tests stub that mismatch off."""
    monkeypatch.setattr(
        "src.models.torch_install.pytorch_cpu_wheel_with_nvidia_gpu_present",
        lambda: False,
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


def test_preflight_strict_blocks_cpu_torch_when_nvidia_and_cpu_wheel(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr("src.models.torch_install.pytorch_cpu_wheel_with_nvidia_gpu_present", lambda: True)
    monkeypatch.setattr(
        "src.models.torch_install.cuda_torch_required_message_for_nvidia_host",
        lambda: "TEST_BLOCK_NEED_CUDA_TORCH",
    )
    r = preflight_check(settings=AppSettings(), strict=True)
    assert not r.ok
    assert any("TEST_BLOCK_NEED_CUDA_TORCH" in e for e in r.errors)


def test_preflight_cpu_torch_block_skipped_with_env_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.runtime.preflight as pf

    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr("src.models.torch_install.pytorch_cpu_wheel_with_nvidia_gpu_present", lambda: True)
    monkeypatch.setenv("AQUADUCT_ALLOW_CPU_TORCH_WITH_NVIDIA", "1")
    r = preflight_check(
        settings=AppSettings(model_execution_mode="local", video_model_id="dummy/video-repo-for-test"),
        strict=True,
    )
    assert r.ok
    assert not any("CPU-only PyTorch" in e for e in r.errors)


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


def test_preflight_host_ram_warning_when_flag_and_low_free(monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    import src.runtime.preflight as pf

    monkeypatch.setenv("AQUADUCT_HOST_RAM_PREFLIGHT", "1")
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])

    class _VM:
        total = 16 << 30
        available = 1 << 30  # 1 GiB free → below 4 GiB threshold

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _VM())

    r = preflight_check(
        settings=AppSettings(model_execution_mode="local", video_model_id="dummy/video-repo-for-test"),
        strict=True,
    )
    assert r.ok
    assert any("Low host RAM headroom" in w for w in r.warnings)


def test_preflight_host_ram_skipped_for_api(monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    import src.runtime.preflight as pf
    from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig

    monkeypatch.setenv("AQUADUCT_HOST_RAM_PREFLIGHT", "1")
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr(pf, "api_preflight_errors", lambda s: [])

    class _VM:
        total = 16 << 30
        available = 1 << 30

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _VM())

    s = AppSettings(
        model_execution_mode="api",
        api_openai_key="test-key-openai",
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
            image=ApiRoleConfig(provider="openai", model="dall-e-3"),
            video=ApiRoleConfig(),
            voice=ApiRoleConfig(provider="openai", model="tts-1"),
        ),
    )
    r = preflight_check(settings=s, strict=True)
    assert not any("Low host RAM headroom" in w for w in r.warnings)


def test_preflight_heavy_repo_ram_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    import src.runtime.preflight as pf

    monkeypatch.setenv("AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM", "1")
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr(
        "src.models.model_manager.load_hf_size_cache",
        lambda _path: {"black-forest-labs/flux.1-dev": 7 * (1024**3)},
    )

    class _VM:
        total = 32 << 30
        available = 2 << 30

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _VM())

    s = AppSettings(
        model_execution_mode="local",
        image_model_id="black-forest-labs/flux.1-dev",
        video_model_id="cerspense/zeroscope_v2_576w",
    )
    r = preflight_check(settings=s, strict=True)
    assert r.ok
    assert any("frontier-class" in w or "large" in w for w in r.warnings)


def test_preflight_heavy_repo_ram_skipped_when_ram_high(monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    import src.runtime.preflight as pf

    monkeypatch.setenv("AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM", "1")
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])
    monkeypatch.setattr(
        "src.models.model_manager.load_hf_size_cache",
        lambda _path: {"black-forest-labs/flux.1-dev": 7 * (1024**3)},
    )

    class _VM:
        total = 64 << 30
        available = 20 << 30

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _VM())

    s = AppSettings(
        model_execution_mode="local",
        image_model_id="black-forest-labs/flux.1-dev",
        video_model_id="cerspense/zeroscope_v2_576w",
    )
    r = preflight_check(settings=s, strict=True)
    assert r.ok
    assert not any("frontier-class" in w for w in r.warnings)


def test_preflight_cpu_busy_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    import src.runtime.preflight as pf

    monkeypatch.setenv("AQUADUCT_CPU_PREFLIGHT", "1")
    monkeypatch.setattr(pf, "find_ffmpeg", lambda p: p)  # type: ignore[arg-type]
    monkeypatch.setattr(pf, "_check_imports", lambda mods: [])

    def _cpu(interval=None):  # noqa: ANN001
        return 0.0 if interval is None else 95.0

    monkeypatch.setattr(psutil, "cpu_percent", _cpu)

    r = preflight_check(
        settings=AppSettings(
            model_execution_mode="local",
            video_model_id="cerspense/zeroscope_v2_576w",
        ),
        strict=True,
    )
    assert r.ok
    assert any("CPU load is high" in w for w in r.warnings)

