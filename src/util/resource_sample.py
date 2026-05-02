"""Sample CPU/RAM for this process and optional CUDA memory (for resource graph)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass

from src.util.cuda_capabilities import cuda_device_reported_by_torch

# Wall clock + cumulative CPU seconds (user+system) for this process and all children, for delta-%CPU.
_cpu_tree_prev: tuple[float, float] | None = None

# Short-lived cache so split-view (N GPUs) does not spawn N ``nvidia-smi`` calls per second when Torch fails.
_smi_vram_pct_cache: tuple[float, dict[int, float]] | None = None


def vram_sparkline_y_axis_cap(samples: Sequence[float]) -> float:
    """
    Cap for the resource graph VRAM sparkline vertical scale (percent of VRAM).

    Uses a fixed 0–100% axis, low percentages sit on the visual floor beside CPU/RAM
    charts that use most of the height; widen the scale when utilization is modest.
    """
    if len(samples) < 2:
        return 100.0
    mx = float(max(samples))
    mn = float(min(samples))
    span = mx - mn
    pad = max(6.0, span * 1.5, mx * 0.06)
    cap = mx + pad
    return max(25.0, min(100.0, cap))


def _tree_cpu_rss_and_children(proc) -> tuple[float, int, int]:
    """
    One recursive walk: summed CPU time (user+system), RSS bytes, and descendant count.

    Avoids calling ``children(recursive=True)`` three times per sample tick.
    """
    import psutil

    t0 = proc.cpu_times()
    cpu_s = float(t0.user + t0.system)
    rss = int(proc.memory_info().rss)
    n_children = 0
    try:
        children = proc.children(recursive=True)
        n_children = len(children)
        for c in children:
            try:
                ct = c.cpu_times()
                cpu_s += float(ct.user + ct.system)
                rss += int(c.memory_info().rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return cpu_s, rss, n_children


@dataclass(frozen=True)
class ResourceSample:
    process_cpu_pct: float  # 0–100: CPU time / wall time / logical cores (tree: main + children)
    process_ram_pct: float  # RSS (main + children) as % of machine RAM
    gpu_mem_pct: float | None  # 0–100 of total VRAM, or None if unavailable
    tree_rss_mb: float = 0.0  # summed RSS for process tree (approximate)
    available_ram_mb: float | None = None  # host free RAM per psutil.virtual_memory().available
    system_memory_used_pct: float | None = None  # machine-wide RAM use (psutil virtual_memory().percent)
    host_used_mb: float | None = None  # psutil virtual_memory().used (MB), for app vs “other” split in UI
    tree_child_count: int = 0  # descendant processes (FFmpeg workers, etc.)
    # System-wide utilization per logical CPU (0–100 each), from ``psutil.cpu_percent(percpu=True)``.
    host_cpu_per_core_pct: tuple[float, ...] = ()


def sample_aquaduct_resources() -> ResourceSample:
    """
    CPU uses **process tree** (Python + FFmpeg subprocesses, etc.): ``psutil`` only reported the
    main process before, which stays near 0% while FFmpeg does the encode.

    RAM is **RSS sum** of main + children (still an underestimate vs peak; shared pages may be double-counted).

    ``host_cpu_per_core_pct`` lists **system-wide** CPU % per logical processor (``psutil.cpu_percent(percpu=True)``),
    for per-core sparklines in the resource graph; unrelated to the headline process-tree average.

    GPU VRAM: fraction of total used on the current CUDA device (drops after each GPU stage finishes).
    """
    global _cpu_tree_prev
    cpu_pct = 0.0
    ram_pct = 0.0
    rss_mb = 0.0
    avail_mb: float | None = None
    sys_used_pct: float | None = None
    host_used_mb: float | None = None
    n_children = 0
    host_per_core: tuple[float, ...] = ()
    try:
        import psutil

        p = psutil.Process(os.getpid())
        n = max(1, psutil.cpu_count(logical=True) or 1)
        now = time.perf_counter()
        cum, rss_b, n_children = _tree_cpu_rss_and_children(p)
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
        rss = float(rss_b)
        ram_pct = 100.0 * rss / float(vm.total) if vm.total else 0.0
        ram_pct = max(0.0, min(100.0, ram_pct))
        rss_mb = rss / (1024.0 * 1024.0)
        avail_mb = float(vm.available) / (1024.0 * 1024.0) if vm.total else None
        if vm.total:
            try:
                host_used_mb = float(vm.used) / (1024.0 * 1024.0)
            except Exception:
                host_used_mb = None
        try:
            sys_used_pct = max(0.0, min(100.0, float(vm.percent)))
        except Exception:
            sys_used_pct = None
        try:
            raw_per = psutil.cpu_percent(percpu=True, interval=None)
            if raw_per:
                host_per_core = tuple(max(0.0, min(100.0, float(x))) for x in raw_per)
        except Exception:
            host_per_core = ()
    except Exception:
        cpu_pct, ram_pct = 0.0, 0.0
        rss_mb = 0.0
        avail_mb = None
        sys_used_pct = None
        host_used_mb = None
        n_children = 0
        host_per_core = ()

    gpu_pct: float | None = None
    try:
        import torch

        if cuda_device_reported_by_torch():
            gpu_pct = sample_gpu_mem_pct(int(torch.cuda.current_device()))
    except Exception:
        gpu_pct = None

    return ResourceSample(
        process_cpu_pct=cpu_pct,
        process_ram_pct=ram_pct,
        gpu_mem_pct=gpu_pct,
        tree_rss_mb=rss_mb,
        available_ram_mb=avail_mb,
        system_memory_used_pct=sys_used_pct,
        host_used_mb=host_used_mb,
        tree_child_count=n_children,
        host_cpu_per_core_pct=host_per_core,
    )


def _torch_gpu_mem_pct(device_index: int) -> float | None:
    try:
        import torch

        if not cuda_device_reported_by_torch():
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


def _parse_nvidia_smi_gpu_mem_pct(stdout: str) -> dict[int, float]:
    """Parse ``--query-gpu=index,memory.used,memory.total`` CSV lines → index → used % (0–100)."""
    out: dict[int, float] = {}
    for raw in (stdout or "").strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [x.strip() for x in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            ix = int(parts[0])
            used_m = float(parts[1])
            total_m = float(parts[2])
        except ValueError:
            continue
        if total_m <= 0.0:
            continue
        out[ix] = max(0.0, min(100.0, 100.0 * used_m / total_m))
    return out


def _nvidia_smi_gpu_used_pct_by_index() -> dict[int, float]:
    """
    VRAM used % per GPU index via ``nvidia-smi`` (matches :func:`list_cuda_gpus` when PyTorch is absent).

    Cached briefly so split-view ticks do not run one subprocess per GPU per second.
    """
    global _smi_vram_pct_cache
    now = time.perf_counter()
    if _smi_vram_pct_cache is not None and now - _smi_vram_pct_cache[0] < 0.85:
        return _smi_vram_pct_cache[1]

    smi = shutil.which("nvidia-smi")
    if not smi:
        _smi_vram_pct_cache = (now, {})
        return {}

    cmd = [
        smi,
        "--query-gpu=index,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    kw: dict = dict(args=cmd, capture_output=True, text=True, timeout=5.0)
    if os.name == "nt":
        try:
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        p = subprocess.run(**kw)
    except Exception:
        _smi_vram_pct_cache = (now, {})
        return {}

    if p.returncode != 0:
        _smi_vram_pct_cache = (now, {})
        return {}

    table = _parse_nvidia_smi_gpu_mem_pct(p.stdout or "")
    _smi_vram_pct_cache = (now, table)
    return table


def sample_gpu_mem_pct(device_index: int) -> float | None:
    """VRAM used on ``device_index`` as 0–100% of that GPU's total.

    Uses ``torch.cuda.mem_get_info`` when available; falls back to ``nvidia-smi`` so split-view
    charts still update when Torch cannot query VRAM (driver/build quirks, CPU-only Torch with
    NVIDIA drivers present, etc.).
    """
    t = _torch_gpu_mem_pct(device_index)
    if t is not None:
        return t
    return _nvidia_smi_gpu_used_pct_by_index().get(device_index)
