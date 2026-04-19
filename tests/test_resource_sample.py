from __future__ import annotations

from src.util.resource_sample import ResourceSample, sample_aquaduct_resources


def test_resource_sample_returns_dataclass() -> None:
    s = sample_aquaduct_resources()
    assert isinstance(s, ResourceSample)
    assert 0.0 <= s.process_cpu_pct <= 100.0
    assert 0.0 <= s.process_ram_pct <= 100.0
    assert s.gpu_mem_pct is None or 0.0 <= s.gpu_mem_pct <= 100.0
