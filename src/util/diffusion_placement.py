"""
Place diffusers pipelines on CUDA with optional CPU↔GPU weight movement.

This is not OS "swap" to disk; it is **offload**: weights live in system RAM and are moved to the GPU
for the active module/step, reducing peak VRAM at the cost of speed and some host RAM.

Policy is **auto** from GPU VRAM, total/available system RAM, and optional live ``psutil`` readings.
Override with environment variables when needed (see ``resolve_diffusion_offload_mode``).
"""

from __future__ import annotations

import os
from typing import Literal

OffloadMode = Literal["none", "model", "sequential"]


def resolve_diffusion_offload_mode() -> OffloadMode:
    """
    Choose how to stage diffusion weights between CPU RAM and GPU VRAM.

    Environment (highest priority first):

    - ``AQUADUCT_DIFFUSION_CPU_OFFLOAD``:
      - ``auto`` (default) — heuristics from ``get_hardware_info()`` + available RAM
      - ``off`` / ``none`` / ``0`` / ``false`` — full ``.to("cuda")`` when CUDA is available
      - ``model`` — ``enable_model_cpu_offload()`` (balance of VRAM vs speed)
      - ``sequential`` — ``enable_sequential_cpu_offload()`` (lowest peak VRAM, slowest)

    - ``AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD=1`` (legacy): same as ``sequential`` when the
      variable above is unset or ``auto``.
    """
    raw = os.environ.get("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "").strip().lower()
    legacy_seq = os.environ.get("AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    if raw in ("off", "none", "0", "false", "no"):
        return "none"
    if raw == "model":
        return "model"
    if raw == "sequential":
        return "sequential"
    if raw not in ("", "auto"):
        # Unknown token: prefer safe low-VRAM path
        return "sequential"

    # auto (or empty)
    if legacy_seq and raw in ("", "auto"):
        return "sequential"

    return _resolve_auto_offload_mode()


def _avail_ram_gb() -> float | None:
    try:
        import psutil

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:
        return None


def _resolve_auto_offload_mode() -> OffloadMode:
    vram_gb: float | None = None
    try:
        from src.models.hardware import get_hardware_info

        vram_gb = get_hardware_info().vram_gb
    except Exception:
        pass

    avail_gb = _avail_ram_gb()

    if vram_gb is None:
        # No GPU info: sequential offload is the safest default when CUDA still works but VRAM unknown
        return "sequential"

    # Very little free host RAM: avoid aggressive CPU staging (offload copies weights through RAM).
    # Prefer keeping the full pipeline on GPU only when VRAM is comfortably large (8 GB is not enough
    # for full-GPU SVD + typical prior loads — that path OOMs on common cards).
    if avail_gb is not None and avail_gb < 3.0 and vram_gb >= 12.0:
        return "none"

    if vram_gb >= 12.0:
        if avail_gb is None or avail_gb >= 4.0:
            return "none"
        return "model"

    if vram_gb >= 8.0:
        return "model"

    return "sequential"


def place_diffusion_pipeline(pipe) -> None:
    """
    Move a diffusers ``pipe`` to CPU, or CUDA with none/model/sequential offload per
    ``resolve_diffusion_offload_mode()``.
    """
    import torch

    if not torch.cuda.is_available():
        pipe.to("cpu")
        return

    mode = resolve_diffusion_offload_mode()
    if mode == "none":
        pipe.to("cuda")
        return

    if mode == "model":
        try:
            pipe.enable_model_cpu_offload()
            return
        except Exception:
            pass
        try:
            pipe.enable_sequential_cpu_offload()
            return
        except Exception:
            pass
        pipe.to("cuda")
        return

    # sequential
    try:
        pipe.enable_sequential_cpu_offload()
        return
    except Exception:
        pass
    try:
        pipe.enable_model_cpu_offload()
        return
    except Exception:
        pass
    pipe.to("cuda")
