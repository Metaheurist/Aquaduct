from __future__ import annotations

from src.models.hardware import (
    AutoFitRanked,
    HardwareInfo,
    fit_marker_display,
    rank_models_for_auto_fit,
    voice_fit_marker,
)
from src.models.model_manager import model_options


def test_rank_models_for_auto_fit_returns_ordered_lists() -> None:
    opts = model_options()
    hw = HardwareInfo(
        os="test",
        cpu="test",
        ram_gb=32.0,
        gpu_name="Test GPU",
        vram_gb=8.0,
    )
    r = rank_models_for_auto_fit(opts, hw)
    assert isinstance(r, AutoFitRanked)
    assert r.script_repo_ids
    assert r.image_repo_ids
    assert r.video_repo_ids
    assert r.voice_repo_ids
    assert "Auto-fit" in r.log_summary
    assert "Script:" in r.log_summary
    # 8GB VRAM: SDXL Turbo should rank first among image models.
    assert r.image_repo_ids[0] == "stabilityai/sdxl-turbo" or "sdxl-turbo" in r.image_repo_ids[0]
    # Motion: at 8GB VRAM, lighter ZeroScope (448×256) can outrank 576w on fit marker before preference tie-break.
    assert r.video_repo_ids[0].startswith("cerspense/zeroscope_v2_")


def test_rank_prefers_lighter_video_on_low_vram() -> None:
    opts = model_options()
    hw = HardwareInfo(os="t", cpu="t", ram_gb=16.0, gpu_name="G", vram_gb=4.0)
    r = rank_models_for_auto_fit(opts, hw)
    # SD 1.5 class should beat SDXL Turbo when VRAM is tight.
    assert r.image_repo_ids[0] == "runwayml/stable-diffusion-v1-5"


def test_voice_fit_marker_penalizes_bark_on_small_vram() -> None:
    m, _ = voice_fit_marker("suno/bark", 4.0)
    assert m in ("RISKY", "NO_GPU")


def test_voice_fit_marker_ok_for_kokoro() -> None:
    m, _ = voice_fit_marker("hexgrad/Kokoro-82M", None)
    assert m == "EXCELLENT"


def test_fit_marker_display_maps_no_gpu_to_vram_limit() -> None:
    assert fit_marker_display("NO_GPU") == "VRAM Limit"
    assert fit_marker_display("OK") == "OK"
