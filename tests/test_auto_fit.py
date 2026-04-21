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
    # 8GB VRAM: lightest “OK”/best-fit 3.5-turbo is preferred first via fit + preference.
    assert r.image_repo_ids[0] == "stabilityai/stable-diffusion-3.5-large-turbo"
    # 8GB VRAM: CogVideoX 5B is the lightest curated T2V fit target.
    assert r.video_repo_ids[0].lower() == "thudm/cogvideox-5b"


def test_rank_prefers_lighter_video_on_low_vram() -> None:
    opts = model_options()
    hw = HardwareInfo(os="t", cpu="t", ram_gb=16.0, gpu_name="G", vram_gb=4.0)
    r = rank_models_for_auto_fit(opts, hw)
    # 4GB VRAM: all curated image stacks are tight; first follows tie-break preference (3.5 Large Turbo first).
    assert r.image_repo_ids[0] == "stabilityai/stable-diffusion-3.5-large-turbo"
    assert r.video_repo_ids[0].lower() == "thudm/cogvideox-5b"


def test_voice_fit_marker_moss_tight_on_small_vram() -> None:
    m, _ = voice_fit_marker("OpenMOSS-Team/MOSS-VoiceGenerator", 4.0)
    assert m == "RISKY"


def test_voice_fit_marker_ok_for_kokoro() -> None:
    m, _ = voice_fit_marker("hexgrad/Kokoro-82M", None)
    assert m == "EXCELLENT"


def test_fit_marker_display_maps_no_gpu_to_vram_limit() -> None:
    assert fit_marker_display("NO_GPU") == "VRAM Limit"
    assert fit_marker_display("OK") == "OK"
