"""Planner inputs: free CUDA memory + optional host RAM (psutil)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuMemoryEstimate:
    index: int
    free_bytes: int
    total_bytes: int


def list_cuda_memory_estimates(device_count: int) -> tuple[GpuMemoryEstimate, ...]:
    """Best-effort per-device free VRAM via ``torch.cuda.mem_get_info``."""
    dc = max(0, int(device_count))
    if dc <= 0:
        return ()
    try:
        import torch
    except Exception:
        return ()

    out: list[GpuMemoryEstimate] = []
    for idx in range(dc):
        free_b, total_b = -1, -1
        try:
            f, t = torch.cuda.mem_get_info(idx)
            free_b = int(f)
            total_b = int(t)
        except Exception:
            try:
                total_b = int(torch.cuda.get_device_properties(idx).total_memory)
                free_b = max(1, total_b // 8)
            except Exception:
                total_b = 8 * (1024**3)
                free_b = 2 * (1024**3)
        out.append(GpuMemoryEstimate(index=idx, free_bytes=max(0, free_b), total_bytes=max(1, total_b)))
    return tuple(out)


def available_host_ram_gb() -> float | None:
    """Return available system RAM (GiB) when psutil works."""
    try:
        import psutil

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:
        return None


def build_accelerate_max_memory(
    *,
    estimates: tuple[GpuMemoryEstimate, ...],
    reserve_frac: float = 0.12,
    min_cpu_gib: int = 4,
    cpu_frac: float = 0.35,
) -> dict[int | str, str]:
    """``max_memory`` dict suitable for transformers + Accelerate VRAM slicing."""
    out: dict[int | str, str] = {}
    for e in estimates:
        free_gib = int(max(1, round(e.free_bytes / (1024**3))))
        usable = max(1, int(round(float(free_gib) * (1.0 - float(reserve_frac)))))
        out[int(e.index)] = f"{usable}GiB"
    avail_gb = available_host_ram_gb()
    cpu_gib: int
    if avail_gb is not None:
        cpu_gib = max(int(min_cpu_gib), int(round(float(avail_gb) * float(cpu_frac))))
    else:
        cpu_gib = int(min_cpu_gib)
    out["cpu"] = f"{cpu_gib}GiB"
    try:
        dg: int | None = None
        raw = os.environ.get("AQUADUCT_ACCELERATE_DISK_GIB", "").strip()
        if raw.replace(".", "", 1).isdigit():
            dg = max(1, int(float(raw)))
        elif os.environ.get("AQUADUCT_ACCELERATE_DISK_AUTO", "1").strip().lower() not in ("0", "false", "no"):
            from src.core.config import get_paths

            dd = get_paths().cache_dir / "accelerate_disk"
            dd.mkdir(parents=True, exist_ok=True)
            free_b = shutil.disk_usage(str(dd)).free
            frac = float(os.environ.get("AQUADUCT_ACCELERATE_DISK_FREE_FRAC", "0.35"))
            dg = max(24, int((free_b * frac) / (1024**3)))
            dg = min(512, dg)
        if dg is not None and dg >= 24:
            out["disk"] = f"{dg}GiB"
    except Exception:
        pass
    return out
