"""
Resolve which CUDA device index to use for LLM vs diffusion (and fit heuristics) from AppSettings.

Auto: highest VRAM for diffusion/image/video; heuristic "compute" score for script (LLM).
If both heuristics pick the **same** GPU (common when one card wins on speed and VRAM ties go to
that index), route the LLM to the **best remaining** compute GPU so the second card is used.
Single: one pinned GPU for all local stages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.core.config import AppSettings
from src.models.hardware import (
    GpuDevice,
    compute_preferred_device_index,
    list_cuda_gpus,
    vram_hungry_device_index,
)


@dataclass(frozen=True)
class DevicePlan:
    llm_device_index: int
    diffusion_device_index: int
    voice_device_index: int
    #: Reserved for future Accelerate multi-GPU LLM sharding; currently always False (4-bit stays single-GPU).
    use_model_parallel_llm: bool = False


def _env_override_device_index() -> int | None:
    raw = (os.environ.get("AQUADUCT_CUDA_DEVICE") or "").strip()
    if raw.isdigit():
        return int(raw)
    if raw.lower().startswith("cuda:") and raw.split(":", 1)[1].strip().isdigit():
        return int(raw.split(":", 1)[1].strip())
    return None


def resolve_device_plan(gpus: list[GpuDevice], settings: AppSettings) -> DevicePlan:
    """Map GPU policy to concrete device indices (best-effort if list empty)."""
    env_idx = _env_override_device_index()
    if not gpus:
        return DevicePlan(0, 0, 0)
    valid = {g.index for g in gpus}

    def _clamp(i: int) -> int:
        if i in valid:
            return i
        return gpus[0].index

    if env_idx is not None:
        idx = _clamp(env_idx)
        return DevicePlan(idx, idx, idx)

    mode = str(getattr(settings, "gpu_selection_mode", "auto") or "auto").strip().lower()
    if mode == "single":
        want = int(getattr(settings, "gpu_device_index", 0) or 0)
        idx = _clamp(want)
        return DevicePlan(idx, idx, idx)

    vram_i = vram_hungry_device_index(gpus)
    comp_i = compute_preferred_device_index(gpus)
    if len(gpus) >= 2 and vram_i == comp_i:
        others = [g for g in gpus if g.index != vram_i]
        if others:
            llm_i = compute_preferred_device_index(others)
            return DevicePlan(llm_device_index=llm_i, diffusion_device_index=vram_i, voice_device_index=llm_i)
    return DevicePlan(llm_device_index=comp_i, diffusion_device_index=vram_i, voice_device_index=comp_i)


def _vram_gb_at(gpus: list[GpuDevice], device_index: int) -> float | None:
    for g in gpus:
        if g.index == device_index:
            return g.total_vram_gb
    return None


def effective_vram_gb_for_kind(kind: str, gpus: list[GpuDevice], settings: AppSettings) -> float | None:
    """
    VRAM (GB) used for fit heuristics for ``kind``: script | image | video | voice.
    """
    if not gpus:
        return None
    plan = resolve_device_plan(gpus, settings)
    k = (kind or "").strip().lower()
    if k == "script":
        return _vram_gb_at(gpus, plan.llm_device_index)
    if k in ("image", "video"):
        return _vram_gb_at(gpus, plan.diffusion_device_index)
    if k == "voice":
        return _vram_gb_at(gpus, plan.voice_device_index)
    return None


def resolve_llm_cuda_device_index(settings: AppSettings) -> int | None:
    """CUDA device index for local LLM load, or None if no CUDA GPUs listed."""
    gpus = list_cuda_gpus()
    if not gpus:
        return None
    return resolve_device_plan(gpus, settings).llm_device_index


def resolve_diffusion_cuda_device_index(settings: AppSettings) -> int | None:
    """CUDA device index for diffusers image/video pipelines, or None if no CUDA."""
    gpus = list_cuda_gpus()
    if not gpus:
        return None
    return resolve_device_plan(gpus, settings).diffusion_device_index
