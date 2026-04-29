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
    CUDA runtime) raise different types and messages. Avoid treating every ``cuda error`` as OOM.
    """
    tname = type(exc).__name__.lower()
    if "outofmemory" in tname or tname == "memoryerror":
        return True
    if isinstance(exc, MemoryError):
        return True
    s = f"{type(exc).__name__}: {exc}".lower()
    needles = (
        "out of memory",
        "cuda out of memory",
        "torch.cuda.outofmemory",
        "cublasalloc",
        "cublas error",
        "cuda error: out of memory",
        "allocation failed",
        "failed to allocate",
        "could not allocate",
        "not enough gpu memory",
        "insufficient gpu memory",
        "insufficient memory",
        "bad allocation",
        "std::bad_alloc",
        "resource exhausted",  # some TF/XLA-style wrappers
        "cudnn_status_alloc_failed",
        "hip out of memory",
        "mps out of memory",
        "killed process",  # Linux OOM killer text occasionally surfaces in wrappers
    )
    if any(n in s for n in needles):
        return True
    # Narrow CUDA memory pattern without flagging unrelated driver bugs.
    if "cuda" in s and ("oom" in s or "memory" in s or "allocate" in s):
        return True
    return False


def pick_next_gpu_index_after_oom(
    *,
    current_index: int | None,
    failed_indices: set[int],
    gpus: list[GpuDevice],
) -> int | None:
    """
    After an OOM on ``current_index``, pick another GPU to try **before** lowering quant.

    Preference:
    1. A GPU not yet in ``failed_indices`` with **strictly more** VRAM than the device that OOM'd.
    2. Else a remaining GPU with **equal** VRAM (common identical dual-GPU setups).
    3. Never switch to a **smaller** VRAM card as an OOM recovery step.

    If ``current_index`` is ``None``, returns the highest-VRAM GPU not in ``failed_indices``.
    """
    if not gpus:
        return None
    by_idx = {int(g.index): g for g in gpus}
    if current_index is not None:
        failed_indices.add(int(current_index))
    eligible = [g for g in gpus if int(g.index) not in failed_indices]
    if not eligible:
        return None
    if current_index is None:
        return int(max(eligible, key=lambda g: (float(g.total_vram_gb), -int(g.index))).index)
    cur = by_idx.get(int(current_index))
    cur_v = float(cur.total_vram_gb) if cur is not None else None
    if cur_v is None:
        return int(max(eligible, key=lambda g: (float(g.total_vram_gb), -int(g.index))).index)
    strictly_better = [g for g in eligible if float(g.total_vram_gb) > cur_v + 1e-6]
    if strictly_better:
        return int(max(strictly_better, key=lambda g: (float(g.total_vram_gb), -int(g.index))).index)
    equal_tier = [
        g
        for g in eligible
        if abs(float(g.total_vram_gb) - cur_v) < 1e-6 and int(g.index) != int(current_index)
    ]
    if equal_tier:
        return int(min(equal_tier, key=lambda g: int(g.index)).index)
    return None


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
    max_quant_downgrades: int = 5,
) -> tuple[T, AppSettings, int | None]:
    """
    Generic retry controller:
    - first attempt: run_cb(settings, cuda_device_index)
    - on OOM: try another CUDA device with **more** or **equal** VRAM (never a smaller card), then
    - downgrade quant one step at a time (``max_quant_downgrades``), clearing VRAM between tries.

    Returns (result, settings_after, cuda_device_index_after).
    """
    failed_gpu_indices: set[int] = set()
    quant_steps = 0
    cur_settings = settings
    cur_idx = cuda_device_index

    while True:
        try:
            out = run_cb(cur_settings, cur_idx)
            return out, cur_settings, cur_idx
        except BaseException as e:
            if not is_oom_error(e):
                try:
                    from debug import pipeline_console

                    pipeline_console(
                        f"Stage {stage_name!r} raised {type(e).__name__}: {e} "
                        f"(role={role!r} repo={repo_id!r} cuda={cur_idx!r}) — see stderr traceback from run_once",
                        stage=stage_name,
                    )
                except Exception:
                    pass
                raise

            try:
                from debug import pipeline_console

                pipeline_console(
                    f"CUDA/VRAM OOM in {stage_name!r} ({role}, {repo_id!r}, cuda={cur_idx!r}) — "
                    "trying larger/equal VRAM GPU if available, else lowering quant…",
                    stage=stage_name,
                )
            except Exception:
                pass

            alt = pick_next_gpu_index_after_oom(
                current_index=cur_idx,
                failed_indices=failed_gpu_indices,
                gpus=gpus,
            )
            if alt is not None and (cur_idx is None or int(alt) != int(cur_idx)):
                clear_cb()
                cur_idx = int(alt)
                continue

            # Retry: lower quant mode (VRAM saver path).
            if quant_steps >= max_quant_downgrades:
                raise
            new_mode = next_lower_quant_mode(role=role, repo_id=repo_id, settings=cur_settings)
            if new_mode is None:
                raise
            try:
                from debug import pipeline_console

                pipeline_console(
                    f"OOM retry {stage_name!r}: lowering {role} quant → {new_mode!r} (step {quant_steps + 1}/{max_quant_downgrades})",
                    stage=stage_name,
                )
            except Exception:
                pass
            clear_cb()
            cur_settings = with_lowered_quant(role=role, new_mode=new_mode, settings=cur_settings)
            quant_steps += 1

