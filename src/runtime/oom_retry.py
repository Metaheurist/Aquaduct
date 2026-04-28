from __future__ import annotations

from dataclasses import replace
from typing import Callable, TypeVar

from src.core.config import AppSettings
from src.models.hardware import GpuDevice
from src.models.quantization import (
    QuantMode,
    QuantRole,
    index_of_manual_mode,
    manual_quant_modes_low_to_high,
    resolve_quant_mode,
)

T = TypeVar("T")


def is_oom_error(exc: BaseException) -> bool:
    """
    Best-effort: classify an exception as CUDA/VRAM/allocator OOM.

    This is intentionally string-based because different stacks (torch, diffusers, xformers,
    CUDA runtime) raise different types and messages.
    """
    s = f"{exc}".lower()
    needles = (
        "out of memory",
        "cuda out of memory",
        "cublas",
        "cuda error: out of memory",
        "alloc",
        "allocation failed",
        "cuda error",
        "hip out of memory",
        "mps out of memory",
    )
    return any(n in s for n in needles)


def higher_vram_gpu_index(*, current_index: int | None, gpus: list[GpuDevice]) -> int | None:
    """
    Returns the index of a GPU with strictly higher VRAM than the current device.
    Chooses the highest-VRAM card. Returns None if no better card exists.
    """
    if not gpus:
        return None
    by_idx = {g.index: g for g in gpus}
    cur = by_idx.get(int(current_index)) if current_index is not None else None
    cur_v = float(cur.total_vram_gb) if cur is not None else None
    best = max(gpus, key=lambda g: float(g.total_vram_gb))
    if cur_v is None:
        return best.index
    return best.index if float(best.total_vram_gb) > float(cur_v) else None


def next_lower_quant_mode(*, role: QuantRole, repo_id: str, settings: AppSettings) -> QuantMode | None:
    """
    Step one notch toward lower VRAM for this role, based on the canonical manual ordering.

    Returns None if the mode cannot be lowered further (or the role has no manual modes).
    """
    effective = resolve_quant_mode(role=role, settings=settings)
    modes = manual_quant_modes_low_to_high(role=role, repo_id=repo_id)
    if not modes:
        return None
    ix = index_of_manual_mode(modes, effective)
    if ix <= 0:
        return None
    return modes[ix - 1]


def with_lowered_quant(
    *, role: QuantRole, new_mode: QuantMode, settings: AppSettings
) -> AppSettings:
    """
    Persist a per-role quant choice into settings (per your selection: per-role, not per-repo).
    """
    if role == "script":
        return replace(settings, script_quant_mode=new_mode)
    if role == "image":
        return replace(settings, image_quant_mode=new_mode)
    if role == "video":
        return replace(settings, video_quant_mode=new_mode)
    if role == "voice":
        return replace(settings, voice_quant_mode=new_mode)
    return settings


def retry_stage(
    *,
    stage_name: str,
    role: QuantRole,
    repo_id: str,
    settings: AppSettings,
    cuda_device_index: int | None,
    gpus: list[GpuDevice],
    clear_cb: Callable[[], None],
    run_cb: Callable[[AppSettings, int | None], T],
    max_quant_downgrades: int = 3,
) -> tuple[T, AppSettings, int | None]:
    """
    Generic retry controller:
    - first attempt: run_cb(settings, cuda_device_index)
    - on OOM: try switching to a higher-VRAM GPU (once)
    - then downgrade quant step-by-step (max_quant_downgrades)

    Returns (result, settings_after, cuda_device_index_after).
    """
    switched_gpu = False
    quant_steps = 0
    cur_settings = settings
    cur_idx = cuda_device_index

    while True:
        try:
            out = run_cb(cur_settings, cur_idx)
            return out, cur_settings, cur_idx
        except BaseException as e:
            if not is_oom_error(e):
                raise

            # Retry 1: move to a higher VRAM GPU (only if it exists).
            if not switched_gpu:
                alt = higher_vram_gpu_index(current_index=cur_idx, gpus=gpus)
                if alt is not None and alt != cur_idx:
                    clear_cb()
                    switched_gpu = True
                    cur_idx = int(alt)
                    continue
                switched_gpu = True  # no better GPU exists; proceed to quant downgrade

            # Retry 2+: lower quant mode.
            if quant_steps >= max_quant_downgrades:
                raise
            new_mode = next_lower_quant_mode(role=role, repo_id=repo_id, settings=cur_settings)
            if new_mode is None:
                raise
            clear_cb()
            cur_settings = with_lowered_quant(role=role, new_mode=new_mode, settings=cur_settings)
            quant_steps += 1

