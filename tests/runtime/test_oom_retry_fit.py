from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.config import AppSettings
from src.models.hardware import GpuDevice
from src.runtime.oom_retry import (
    higher_vram_gpu_index,
    is_oom_error,
    next_lower_quant_mode,
    pick_next_gpu_index_after_oom,
    retry_stage,
)


def test_is_oom_error_stringy() -> None:
    assert is_oom_error(RuntimeError("CUDA out of memory"))
    assert is_oom_error(RuntimeError("allocation failed on device"))
    assert is_oom_error(RuntimeError("Failed to allocate 20.00 GiB"))
    assert not is_oom_error(RuntimeError("some other error"))
    assert not is_oom_error(RuntimeError("CUDA error: device-side assert triggered"))


def test_pick_next_gpu_equal_vram_switches_peer() -> None:
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=12 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=12 * (1024**3))
    failed: set[int] = set()
    nxt = pick_next_gpu_index_after_oom(current_index=0, failed_indices=failed, gpus=[g0, g1])
    assert nxt == 1
    assert 0 in failed


def test_pick_next_gpu_skips_smaller_vram_card() -> None:
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=12 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=8 * (1024**3))
    failed: set[int] = set()
    nxt = pick_next_gpu_index_after_oom(current_index=0, failed_indices=failed, gpus=[g0, g1])
    assert nxt is None
    assert 0 in failed


def test_higher_vram_gpu_index_picks_strictly_higher() -> None:
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=12 * (1024**3))
    assert higher_vram_gpu_index(current_index=0, gpus=[g0, g1]) == 1
    assert higher_vram_gpu_index(current_index=1, gpus=[g0, g1]) is None


def test_next_lower_quant_mode_video_steps_down() -> None:
    s = AppSettings()
    s = replace(s, video_quant_mode="bf16")
    assert next_lower_quant_mode(role="video", repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers", settings=s) == "fp16"
    s2 = replace(s, video_quant_mode="fp16")
    assert next_lower_quant_mode(role="video", repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers", settings=s2) == "int8"


def test_retry_stage_switches_gpu_then_downgrades_quant() -> None:
    s0 = replace(AppSettings(), video_quant_mode="bf16")
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=12 * (1024**3))

    calls: list[tuple[str, int | None]] = []

    class OomOnce:
        n = 0

        def __call__(self, settings: AppSettings, idx: int | None) -> str:
            calls.append((str(getattr(settings, "video_quant_mode", "")), idx))
            # fail first two attempts: first triggers GPU switch, second triggers quant downgrade
            if self.n == 0:
                self.n += 1
                raise RuntimeError("CUDA out of memory while loading weights")
            if self.n == 1:
                self.n += 1
                raise RuntimeError("CUDA out of memory during allocate")
            return "ok"

    out, s1, idx1 = retry_stage(
        stage_name="t2v",
        role="video",
        repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        settings=s0,
        cuda_device_index=0,
        gpus=[g0, g1],
        clear_cb=lambda: None,
        run_cb=OomOnce(),
        max_quant_downgrades=5,
    )
    assert out == "ok"
    assert idx1 == 1  # switched to higher-VRAM GPU
    assert str(getattr(s1, "video_quant_mode")) in ("fp16", "int8", "cpu_offload")
    # first call: bf16 on 0; second call: bf16 on 1; then at least one downgrade
    assert calls[0] == ("bf16", 0)
    assert calls[1] == ("bf16", 1)


def test_retry_stage_equal_vram_tries_peer_gpu_before_quant() -> None:
    s0 = replace(AppSettings(), video_quant_mode="bf16")
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=12 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=12 * (1024**3))
    calls: list[int | None] = []

    class BoomThenOk:
        n = 0

        def __call__(self, settings: AppSettings, idx: int | None) -> str:
            calls.append(idx)
            if self.n == 0:
                self.n += 1
                raise RuntimeError("CUDA out of memory")
            return "ok"

    out, s1, idx1 = retry_stage(
        stage_name="t2v",
        role="video",
        repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        settings=s0,
        cuda_device_index=0,
        gpus=[g0, g1],
        clear_cb=lambda: None,
        run_cb=BoomThenOk(),
        max_quant_downgrades=5,
    )
    assert out == "ok"
    assert calls == [0, 1]
    assert idx1 == 1
    assert str(getattr(s1, "video_quant_mode")) == "bf16"


def test_retry_stage_stops_when_no_more_downgrades() -> None:
    s0 = replace(AppSettings(), video_quant_mode="cpu_offload")
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))

    def _always_oom(_s: AppSettings, _idx: int | None) -> None:
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(RuntimeError, match="out of memory"):
        retry_stage(
            stage_name="t2v",
            role="video",
            repo_id="anything",
            settings=s0,
            cuda_device_index=0,
            gpus=[g0],
            clear_cb=lambda: None,
            run_cb=_always_oom,
            max_quant_downgrades=1,
        )

