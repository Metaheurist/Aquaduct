"""Sample CPU/RAM for this process and optional CUDA memory (for resource graph)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSample:
    process_cpu_pct: float  # 0–100 (scaled by CPU count)
    process_ram_pct: float  # RSS as % of machine RAM
    gpu_mem_pct: float | None  # 0–100 of total VRAM, or None if unavailable


def sample_aquaduct_resources() -> ResourceSample:
    """
    Process CPU (avg since last call), process RAM vs system total, and GPU VRAM
    used / total when ``torch.cuda`` is available.
    """
    try:
        import psutil

        p = psutil.Process(os.getpid())
        n = max(1, psutil.cpu_count(logical=True) or 1)
        raw_cpu = float(p.cpu_percent(interval=None))
        cpu_pct = max(0.0, min(100.0, raw_cpu / float(n)))

        vm = psutil.virtual_memory()
        rss = float(p.memory_info().rss)
        ram_pct = 100.0 * rss / float(vm.total) if vm.total else 0.0
        ram_pct = max(0.0, min(100.0, ram_pct))
    except Exception:
        cpu_pct, ram_pct = 0.0, 0.0

    gpu_pct: float | None = None
    try:
        import torch

        if torch.cuda.is_available():
            dev = torch.cuda.current_device()
            free_b, total_b = torch.cuda.mem_get_info(dev)
            total_b = float(total_b)
            if total_b > 0:
                used_b = total_b - float(free_b)
                gpu_pct = max(0.0, min(100.0, 100.0 * used_b / total_b))
    except Exception:
        gpu_pct = None

    return ResourceSample(process_cpu_pct=cpu_pct, process_ram_pct=ram_pct, gpu_mem_pct=gpu_pct)
