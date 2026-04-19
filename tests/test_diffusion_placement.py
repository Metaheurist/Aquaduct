"""Tests for diffusion CPU offload policy (VRAM/RAM heuristics + env overrides)."""

from __future__ import annotations

import pytest

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
    assert dp.resolve_diffusion_offload_mode() == "model"


def test_tight_host_ram_and_decent_vram_prefers_none(monkeypatch: pytest.MonkeyPatch, clear_offload_env: None) -> None:
    """Avoid offload staging when host RAM is nearly full but GPU can hold the full pipe."""
    monkeypatch.setenv("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "auto")
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=64.0, gpu_name="g", vram_gb=12.0),
    )
    monkeypatch.setattr(dp, "_avail_ram_gb", lambda: 2.0)
    assert dp.resolve_diffusion_offload_mode() == "none"


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
