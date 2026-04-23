from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.config import AppSettings
from src.models.hardware import GpuDevice, rate_model_fit_for_repo, vram_hungry_device_index
from src.util.cuda_device_policy import (
    DevicePlan,
    effective_vram_gb_for_kind,
    resolve_device_plan,
)


def _gpu(a: int, b: int, name_a: str = "A", name_b: str = "B") -> list[GpuDevice]:
    return [
        GpuDevice(index=0, name=name_a, total_vram_bytes=a * 1024**3, multiprocessor_count=20, major=8, minor=6, clock_rate_khz=1800000),
        GpuDevice(index=1, name=name_b, total_vram_bytes=b * 1024**3, multiprocessor_count=36, major=8, minor=9, clock_rate_khz=2000000),
    ]


def test_resolve_single_mode_pins_one_gpu() -> None:
    gpus = _gpu(8, 12)
    s = replace(AppSettings(), gpu_selection_mode="single", gpu_device_index=1)
    plan = resolve_device_plan(gpus, s)
    assert plan == DevicePlan(llm_device_index=1, diffusion_device_index=1, voice_device_index=1)


def test_resolve_auto_splits_llm_and_diffusion() -> None:
    gpus = _gpu(8, 12)
    s = replace(AppSettings(), gpu_selection_mode="auto")
    plan = resolve_device_plan(gpus, s)
    assert plan.diffusion_device_index == 1  # 12GB
    # Max-VRAM and compute both prefer the 12GB card — LLM should move to the other GPU.
    assert plan.llm_device_index == 0
    assert plan.voice_device_index == 0


def test_resolve_auto_when_vram_and_compute_same_gpu_splits_llm_to_other() -> None:
    """Equal VRAM tie → index 0 wins both heuristics; LLM must use GPU 1 so both GPUs participate."""
    gpus = [
        GpuDevice(index=0, name="A", total_vram_bytes=12 * 1024**3, multiprocessor_count=40, major=8, minor=6, clock_rate_khz=1800000),
        GpuDevice(index=1, name="B", total_vram_bytes=12 * 1024**3, multiprocessor_count=40, major=8, minor=6, clock_rate_khz=1800000),
    ]
    s = replace(AppSettings(), gpu_selection_mode="auto")
    plan = resolve_device_plan(gpus, s)
    assert plan.diffusion_device_index == 0
    assert plan.llm_device_index == 1
    assert plan.voice_device_index == 1


def test_effective_vram_per_kind() -> None:
    gpus = _gpu(8, 12)
    s = replace(AppSettings(), gpu_selection_mode="auto")
    assert effective_vram_gb_for_kind("image", gpus, s) == 12.0
    assert effective_vram_gb_for_kind("script", gpus, s) is not None


def test_vram_hungry_tie_prefers_lower_index() -> None:
    gpus = [
        GpuDevice(index=0, name="A", total_vram_bytes=12 * 1024**3, multiprocessor_count=40, major=8, minor=6, clock_rate_khz=1800000),
        GpuDevice(index=1, name="B", total_vram_bytes=12 * 1024**3, multiprocessor_count=40, major=8, minor=6, clock_rate_khz=1800000),
    ]
    assert vram_hungry_device_index(gpus) == 0


def test_effective_vram_image_vs_script_changes_fit_marker() -> None:
    """Auto: LLM on compute GPU vs diffusion on max VRAM — image fit must not use script VRAM."""
    gpus = [
        GpuDevice(
            index=0,
            name="Compute",
            total_vram_bytes=8 * 1024**3,
            multiprocessor_count=90,
            major=9,
            minor=0,
            clock_rate_khz=2800000,
        ),
        GpuDevice(
            index=1,
            name="VRAM",
            total_vram_bytes=24 * 1024**3,
            multiprocessor_count=28,
            major=8,
            minor=6,
            clock_rate_khz=1700000,
        ),
    ]
    s = replace(AppSettings(), gpu_selection_mode="auto")
    plan = resolve_device_plan(gpus, s)
    assert plan.diffusion_device_index == 1
    assert plan.llm_device_index == 0
    assert effective_vram_gb_for_kind("script", gpus, s) == 8.0
    assert effective_vram_gb_for_kind("image", gpus, s) == 24.0
    m_hi, _ = rate_model_fit_for_repo(
        kind="image",
        speed="fastest",
        repo_id="stabilityai/sdxl-turbo",
        pair_image_repo_id="",
        vram_gb=24.0,
        ram_gb=32.0,
    )
    m_lo, _ = rate_model_fit_for_repo(
        kind="image",
        speed="fastest",
        repo_id="stabilityai/sdxl-turbo",
        pair_image_repo_id="",
        vram_gb=8.0,
        ram_gb=32.0,
    )
    assert m_hi != m_lo


def test_env_aquaduct_cuda_device_overrides_auto_split(monkeypatch: pytest.MonkeyPatch) -> None:
    """AQUADUCT_CUDA_DEVICE pins every stage to one index."""
    monkeypatch.setenv("AQUADUCT_CUDA_DEVICE", "0")
    gpus = _gpu(8, 12)
    s = replace(AppSettings(), gpu_selection_mode="auto")
    plan = resolve_device_plan(gpus, s)
    assert plan == DevicePlan(llm_device_index=0, diffusion_device_index=0, voice_device_index=0)
    assert effective_vram_gb_for_kind("image", gpus, s) == 8.0
