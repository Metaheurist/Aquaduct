from __future__ import annotations

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


def test_sample_gpu_mem_pct_invalid_index_returns_none() -> None:
    try:
        import torch
    except Exception:
        assert sample_gpu_mem_pct(0) is None
        return
    if not torch.cuda.is_available():
        assert sample_gpu_mem_pct(0) is None
        return
    n = int(torch.cuda.device_count())
    assert sample_gpu_mem_pct(-1) is None
    assert sample_gpu_mem_pct(n) is None
