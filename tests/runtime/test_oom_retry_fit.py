from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.config import AppSettings
from src.models.hardware import GpuDevice
from src.runtime import oom_retry
from src.runtime.oom_retry import (
    QuantDowngradeExhaustedError,
    higher_vram_gpu_index,
    is_dependency_setup_error,
    is_oom_error,
    next_lower_quant_mode,
    pick_next_gpu_index_after_oom,
    retry_stage,
)


def test_is_dependency_setup_error_tiktoken() -> None:
    err = ValueError("`tiktoken` is required to read a `tiktoken` file. Install it with `pip install tiktoken`.")
    assert is_dependency_setup_error(err)
    assert not is_oom_error(err)


def test_is_dependency_setup_error_sentencepiece_chain() -> None:
    inner = ImportError(
        "SentencePieceExtractor requires the SentencePiece library but it was not found in your environment."
    )
    try:
        raise ValueError("tokenizer convert failed") from inner
    except ValueError as e:
        assert is_dependency_setup_error(e)


def test_retry_stage_dependency_error_skips_quant_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oom_retry, "_persist_quant_settings", lambda _s: None)
    s0 = replace(
        AppSettings(),
        video_quant_mode="bf16",
        auto_quant_downgrade_on_failure=True,
    )
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))

    def _bad(_s: AppSettings, _idx: int | None) -> str:
        raise ValueError("`tiktoken` is required — pip install tiktoken")

    with pytest.raises(ValueError, match="tiktoken"):
        retry_stage(
            stage_name="t2v",
            role="video",
            repo_id="THUDM/CogVideoX-5b",
            settings=s0,
            cuda_device_index=0,
            gpus=[g0],
            clear_cb=lambda: None,
            run_cb=_bad,
            max_quant_downgrades=5,
            preempt_high_vram=False,
        )
    assert str(getattr(s0, "video_quant_mode")) == "bf16"


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


def test_retry_stage_preempt_high_vram_switches_gpu_without_oom(monkeypatch: pytest.MonkeyPatch) -> None:
    s0 = replace(AppSettings(), video_quant_mode="bf16")
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=24 * (1024**3))
    calls: list[int | None] = []

    def _fake_frac(idx: int | None) -> float:
        # After relief move to cuda:1, pretend that card has headroom (real hardware would differ).
        if idx == 1:
            return 0.05
        return 0.995

    monkeypatch.setattr(oom_retry, "gpu_mem_used_fraction", _fake_frac)

    def run_once(settings: AppSettings, idx: int | None) -> str:
        calls.append(idx)
        return "ok"

    out, s1, idx1 = retry_stage(
        stage_name="t2v",
        role="video",
        repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        settings=s0,
        cuda_device_index=0,
        gpus=[g0, g1],
        clear_cb=lambda: None,
        run_cb=run_once,
        max_quant_downgrades=5,
        preempt_high_vram=True,
    )
    assert out == "ok"
    assert idx1 == 1
    assert calls == [1]
    assert str(getattr(s1, "video_quant_mode")) == "bf16"


def test_retry_stage_preempt_disabled_runs_on_busy_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """With preempt off, near-full VRAM does not switch GPU before run_cb."""
    s0 = replace(AppSettings(), video_quant_mode="bf16")
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))
    g1 = GpuDevice(index=1, name="B", total_vram_bytes=24 * (1024**3))

    monkeypatch.setattr(oom_retry, "gpu_mem_used_fraction", lambda _idx: 0.995)

    def run_once(settings: AppSettings, idx: int | None) -> str:
        return "ok"

    _out, _s1, idx1 = retry_stage(
        stage_name="t2v",
        role="video",
        repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        settings=s0,
        cuda_device_index=0,
        gpus=[g0, g1],
        clear_cb=lambda: None,
        run_cb=run_once,
        preempt_high_vram=False,
    )
    assert idx1 == 0


def test_retry_stage_non_oom_downgrades_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oom_retry, "_persist_quant_settings", lambda _s: None)
    s0 = replace(
        AppSettings(),
        video_quant_mode="bf16",
        auto_quant_downgrade_on_failure=True,
    )
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))

    class FailOnce:
        n = 0

        def __call__(self, settings: AppSettings, idx: int | None) -> str:
            self.n += 1
            if self.n == 1:
                raise RuntimeError("bad checkpoint shard")
            return "ok"

    out, s1, idx1 = retry_stage(
        stage_name="t2v",
        role="video",
        repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers",
        settings=s0,
        cuda_device_index=0,
        gpus=[g0],
        clear_cb=lambda: None,
        run_cb=FailOnce(),
        max_quant_downgrades=5,
        preempt_high_vram=False,
    )
    assert out == "ok"
    assert idx1 == 0
    assert str(getattr(s1, "video_quant_mode")) == "fp16"


def test_retry_stage_non_oom_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oom_retry, "_persist_quant_settings", lambda _s: None)
    s0 = replace(
        AppSettings(),
        video_quant_mode="cpu_offload",
        auto_quant_downgrade_on_failure=True,
    )
    g0 = GpuDevice(index=0, name="A", total_vram_bytes=8 * (1024**3))

    def _always_bad(_s: AppSettings, _idx: int | None) -> str:
        raise RuntimeError("load failed")

    with pytest.raises(QuantDowngradeExhaustedError, match="All quantization levels"):
        retry_stage(
            stage_name="t2v",
            role="video",
            repo_id="Wan-AI/Wan2.2-T2V-A14B-Diffusers",
            settings=s0,
            cuda_device_index=0,
            gpus=[g0],
            clear_cb=lambda: None,
            run_cb=_always_bad,
            max_quant_downgrades=5,
            preempt_high_vram=False,
        )


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

