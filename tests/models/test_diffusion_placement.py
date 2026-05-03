"""Tests for diffusion CPU offload policy (VRAM/RAM heuristics + env overrides)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.config import AppSettings
from src.models.hardware import HardwareInfo
from src.util import diffusion_placement as dp


@pytest.fixture
def clear_offload_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", raising=False)
    monkeypatch.delenv("AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD", raising=False)


def test_env_off_forces_none(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "off")
    assert dp.resolve_diffusion_offload_mode() == "none"


def test_env_sequential(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "sequential")
    assert dp.resolve_diffusion_offload_mode() == "sequential"


def test_legacy_env_forces_sequential(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD", "1")
    assert dp.resolve_diffusion_offload_mode() == "sequential"


def test_auto_high_vram_prefers_none(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=16.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 16.0)
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 1)
    assert dp.resolve_diffusion_offload_mode() == "none"


def test_auto_low_vram_prefers_sequential(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=16.0, gpu_name="g", vram_gb=6.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 8.0)
    assert dp.resolve_diffusion_offload_mode() == "sequential"


def test_auto_mid_vram_uses_model(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=10.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 8.0)
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 1)
    assert dp.resolve_diffusion_offload_mode() == "model"


def test_tight_host_ram_12gb_vram_prefers_model(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    """12 GB VRAM is not enough for full-GPU diffusion after LLM / image stages; use model offload."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=64.0, gpu_name="g", vram_gb=12.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 2.0)
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 1)
    assert dp.resolve_diffusion_offload_mode() == "model"


def test_tight_host_ram_16gb_vram_can_prefers_none(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    """Avoid offload staging when host RAM is nearly full but the GPU can hold the full pipe."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=64.0, gpu_name="g", vram_gb=16.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 2.0)
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 1)
    assert dp.resolve_diffusion_offload_mode() == "none"


def test_tight_host_ram_8gb_vram_prefers_model_not_full_gpu(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    """~8 GB VRAM cannot safely run full-GPU SVD after other loads; do not pick ``none`` here."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=64.0, gpu_name="g", vram_gb=8.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 2.0)
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 1)
    assert dp.resolve_diffusion_offload_mode() == "model"


def test_auto_multi_gpu_prefers_sequential(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    """Two+ CUDA devices: auto defaults to sequential so diffusion stays low-peak on its GPU."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=24.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 16.0)
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 2)
    assert dp.resolve_diffusion_offload_mode() == "sequential"


def test_auto_multi_gpu_vram_first_image_prefers_model(
    monkeypatch: pytest.MonkeyPatch, clear_offload_env: None
) -> None:
    """VRAM-first + ≥2 GPUs: image role must not opt into full GPU (video-only optimization)."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    settings = replace(
        AppSettings(),
        multi_gpu_shard_mode="vram_first_auto",
        gpu_selection_mode="auto",
    )
    monkeypatch.setattr(
        "src.gpu.multi_device.gates.vram_first_master_enabled",
        lambda s: isinstance(s, AppSettings),
    )
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 2)
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=24.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 16.0)
    assert dp.resolve_diffusion_offload_mode(settings, placement_role="image") == "model"


def test_auto_multi_gpu_vram_first_image_tight_ram_prefers_sequential(
    monkeypatch: pytest.MonkeyPatch, clear_offload_env: None
) -> None:
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    settings = replace(
        AppSettings(),
        multi_gpu_shard_mode="vram_first_auto",
        gpu_selection_mode="auto",
    )
    monkeypatch.setattr(
        "src.gpu.multi_device.gates.vram_first_master_enabled",
        lambda s: isinstance(s, AppSettings),
    )
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 2)
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=24.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 2.0)
    assert dp.resolve_diffusion_offload_mode(settings, placement_role="image") == "sequential"


def test_auto_multi_gpu_vram_first_video_prefers_none(
    monkeypatch: pytest.MonkeyPatch, clear_offload_env: None
) -> None:
    """VRAM-first + ample host RAM: video path keeps full GPU for peer sharding."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    settings = replace(
        AppSettings(),
        multi_gpu_shard_mode="vram_first_auto",
        gpu_selection_mode="auto",
    )
    monkeypatch.setattr(
        "src.gpu.multi_device.gates.vram_first_master_enabled",
        lambda s: isinstance(s, AppSettings),
    )
    monkeypatch.setattr(dp, "_cuda_device_count", lambda: 2)
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=24.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 16.0)
    assert dp.resolve_diffusion_offload_mode(settings, placement_role="video") == "none"


def test_place_pipeline_cpu_when_no_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    class P:
        def __init__(self) -> None:
            self.device = "cpu"

        def to(self, d: str) -> P:
            self.device = d
            return self

    p = P()
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    dp.place_diffusion_pipeline(p)
    assert p.device == "cpu"


def test_place_sequential_passes_gpu_id(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    """``enable_sequential_cpu_offload`` must receive ``gpu_id`` for multi-GPU diffusion routing."""
    import torch

    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "sequential")

    class P:
        def __init__(self) -> None:
            self.gpu_id: int | None = None

        def enable_sequential_cpu_offload(self, gpu_id: int | None = None, device=None) -> None:
            self.gpu_id = gpu_id

    p = P()
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    dp.place_diffusion_pipeline(p, cuda_device_index=1)
    assert p.gpu_id == 1


def test_dispose_diffusion_pipeline_calls_maybe_free_hooks() -> None:
    calls: list[str] = []

    class DummyPipe:
        def maybe_free_model_hooks(self) -> None:
            calls.append("ok")

    dp.dispose_diffusion_pipeline(DummyPipe())
    assert calls == ["ok"]


def test_dispose_diffusion_pipeline_ok_without_hooks() -> None:
    dp.dispose_diffusion_pipeline(object())
