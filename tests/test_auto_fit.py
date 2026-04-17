from __future__ import annotations

from src.hardware import AutoFitRanked, HardwareInfo, rank_models_for_auto_fit, voice_fit_marker
from src.model_manager import model_options


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
    assert r.video_combo_values
    assert r.voice_repo_ids
    assert "Auto-fit" in r.log_summary
    assert "Script:" in r.log_summary
    # 8GB VRAM: SDXL Turbo should rank before paired SVD (heavier).
    assert r.video_combo_values[0] == "stabilityai/sdxl-turbo" or "sdxl-turbo" in r.video_combo_values[0]


def test_rank_prefers_lighter_video_on_low_vram() -> None:
    opts = model_options()
    hw = HardwareInfo(os="t", cpu="t", ram_gb=16.0, gpu_name="G", vram_gb=4.0)
    r = rank_models_for_auto_fit(opts, hw)
    # SD 1.5 class should beat SDXL Turbo when VRAM is tight.
    assert r.video_combo_values[0] == "runwayml/stable-diffusion-v1-5"


def test_voice_fit_marker_penalizes_bark_on_small_vram() -> None:
    m, _ = voice_fit_marker("suno/bark", 4.0)
    assert m in ("RISKY", "NO_GPU")


def test_voice_fit_marker_ok_for_kokoro() -> None:
    m, _ = voice_fit_marker("hexgrad/Kokoro-82M", None)
    assert m == "EXCELLENT"
