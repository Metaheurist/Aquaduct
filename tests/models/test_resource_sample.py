from __future__ import annotations

import pytest

from src.util import resource_sample as rs
from src.util.resource_sample import ResourceSample, sample_aquaduct_resources, sample_gpu_mem_pct


def test_resource_sample_returns_dataclass() -> None:
    s = sample_aquaduct_resources()
    assert isinstance(s, ResourceSample)
    assert 0.0 <= s.process_cpu_pct <= 100.0
    assert 0.0 <= s.process_ram_pct <= 100.0
    assert s.gpu_mem_pct is None or 0.0 <= s.gpu_mem_pct <= 100.0
    assert s.tree_rss_mb >= 0.0
    assert s.tree_child_count >= 0
    assert s.available_ram_mb is None or s.available_ram_mb >= 0.0
    assert s.system_memory_used_pct is None or 0.0 <= s.system_memory_used_pct <= 100.0
    assert s.host_used_mb is None or s.host_used_mb >= 0.0


def test_sample_gpu_mem_pct_invalid_index_returns_none() -> None:
    assert sample_gpu_mem_pct(-1) is None
    assert sample_gpu_mem_pct(10_000_000) is None
    try:
        import torch
    except Exception:
        return
    if not torch.cuda.is_available():
        return
    n = int(torch.cuda.device_count())
    assert sample_gpu_mem_pct(n) is None


def test_parse_nvidia_smi_gpu_mem_pct() -> None:
    s = "0, 1024, 8192\n1, 4096, 8192\n"
    got = rs._parse_nvidia_smi_gpu_mem_pct(s)
    assert got[0] == pytest.approx(12.5)
    assert got[1] == pytest.approx(50.0)


def test_sample_gpu_mem_pct_smi_fallback_when_torch_raises(monkeypatch) -> None:
    try:
        import torch
    except Exception:
        return

    monkeypatch.setattr(rs, "_torch_gpu_mem_pct", lambda _idx: None)
    monkeypatch.setattr(rs, "_nvidia_smi_gpu_used_pct_by_index", lambda: {0: 11.0, 1: 22.0})
    assert sample_gpu_mem_pct(0) == pytest.approx(11.0)
    assert sample_gpu_mem_pct(1) == pytest.approx(22.0)
