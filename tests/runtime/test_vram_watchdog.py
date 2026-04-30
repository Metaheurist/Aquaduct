"""VRAM watchdog + pipeline notice helpers."""

from __future__ import annotations

import pytest

from src.runtime.pipeline_notice import emit_pipeline_notice, pipeline_notice_scope


def test_pipeline_notice_emits_inside_scope() -> None:
    got: list[tuple[str, str]] = []
    with pipeline_notice_scope(lambda t, m: got.append((t, m))):
        emit_pipeline_notice("VRAM", "Low memory")
    assert got == [("VRAM", "Low memory")]


def test_pipeline_notice_no_cb_outside_scope() -> None:
    emit_pipeline_notice("X", "Y")  # should not raise


def test_vram_watchdog_disabled_skips_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQUADUCT_VRAM_WATCHDOG", "0")
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda ix: "FakeGPU")
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda ix: (1024.0, 8 * 1024**3))

    import src.util.vram_watchdog as vw

    vw.check_cuda_headroom(0, stage="unit")


def test_vram_watchdog_aborts_when_critically_low(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQUADUCT_VRAM_WATCHDOG", raising=False)
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda ix: "FakeGPU")
    monkeypatch.setattr(
        torch.cuda,
        "mem_get_info",
        lambda ix: (16 * 1024 * 1024, 8 * 1024**3),
    )

    import src.util.vram_watchdog as vw

    with pytest.raises(RuntimeError, match="FakeGPU"):
        vw.check_cuda_headroom(0, stage="unit_stage")
