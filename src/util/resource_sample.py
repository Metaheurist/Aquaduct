"""Sample CPU/RAM for this process and optional CUDA memory (for resource graph)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

# Wall clock + cumulative CPU seconds (user+system) for this process and all children, for delta-%CPU.
_cpu_tree_prev: tuple[float, float] | None = None


def _tree_cpu_times_seconds(proc) -> float:
    """Sum user+system CPU time for ``proc`` and all descendants (FFmpeg, etc.)."""
    import psutil

    t = proc.cpu_times()
    s = float(t.user + t.system)
    try:
        for c in proc.children(recursive=True):
            try:
                ct = c.cpu_times()
                s += float(ct.user + ct.system)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return s


def _tree_rss_bytes(proc) -> int:
    """RSS for main process plus children (encode/mux helpers often run as separate processes)."""
    import psutil

    r = int(proc.memory_info().rss)
    try:
        for c in proc.children(recursive=True):
            try:
                r += int(c.memory_info().rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return r


def _tree_child_count(proc) -> int:
    import psutil

    try:
        return len(proc.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


@dataclass(frozen=True)
class ResourceSample:
    process_cpu_pct: float  # 0–100: CPU time / wall time / logical cores (tree: main + children)
    process_ram_pct: float  # RSS (main + children) as % of machine RAM
    gpu_mem_pct: float | None  # 0–100 of total VRAM, or None if unavailable
    tree_rss_mb: float = 0.0  # summed RSS for process tree (approximate)
    available_ram_mb: float | None = None  # host free RAM per psutil.virtual_memory().available
    tree_child_count: int = 0  # descendant processes (FFmpeg workers, etc.)


def sample_aquaduct_resources() -> ResourceSample:
    """
    CPU uses **process tree** (Python + FFmpeg subprocesses, etc.): ``psutil`` only reported the
    main process before, which stays near 0% while FFmpeg does the encode.

    RAM is **RSS sum** of main + children (still an underestimate vs peak; shared pages may be double-counted).

    GPU VRAM: fraction of total used on the current CUDA device (drops after each GPU stage finishes).
    """
    global _cpu_tree_prev
    cpu_pct = 0.0
    ram_pct = 0.0
    rss_mb = 0.0
    avail_mb: float | None = None
    n_children = 0
    try:
        import psutil

        p = psutil.Process(os.getpid())
        n = max(1, psutil.cpu_count(logical=True) or 1)
        now = time.perf_counter()
        cum = _tree_cpu_times_seconds(p)
        prev = _cpu_tree_prev
        _cpu_tree_prev = (now, cum)
        if prev is not None:
            prev_wall, prev_cum = prev
            dt = now - prev_wall
            d_cpu = cum - prev_cum
            if d_cpu < 0.0:
                d_cpu = 0.0  # child process exited; cumulative tree time can step down
            if dt > 1e-6:
                # Fraction of all logical CPUs used: d_cpu/dt can be up to n → 100% at full machine load.
                cpu_pct = max(0.0, min(100.0, 100.0 * (d_cpu / dt) / float(n)))

        vm = psutil.virtual_memory()
        rss = float(_tree_rss_bytes(p))
        ram_pct = 100.0 * rss / float(vm.total) if vm.total else 0.0
        ram_pct = max(0.0, min(100.0, ram_pct))
        rss_mb = rss / (1024.0 * 1024.0)
        avail_mb = float(vm.available) / (1024.0 * 1024.0) if vm.total else None
        n_children = _tree_child_count(p)
    except Exception:
        cpu_pct, ram_pct = 0.0, 0.0
        rss_mb = 0.0
        avail_mb = None
        n_children = 0

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

    return ResourceSample(
        process_cpu_pct=cpu_pct,
        process_ram_pct=ram_pct,
        gpu_mem_pct=gpu_pct,
        tree_rss_mb=rss_mb,
        available_ram_mb=avail_mb,
        tree_child_count=n_children,
    )


def sample_gpu_mem_pct(device_index: int) -> float | None:
    """VRAM used on ``device_index`` as 0–100% of that GPU's total (no ``set_device`` required)."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        n = int(torch.cuda.device_count())
        if device_index < 0 or device_index >= n:
            return None
        free_b, total_b = torch.cuda.mem_get_info(device_index)
        total_b = float(total_b)
        if total_b <= 0:
            return None
        used_b = total_b - float(free_b)
        return max(0.0, min(100.0, 100.0 * used_b / total_b))
    except Exception:
        return None
