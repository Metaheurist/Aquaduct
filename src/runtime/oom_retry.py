from __future__ import annotations

import os
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
from src.runtime.pipeline_control import PipelineCancelled
from src.util.cuda_capabilities import cuda_device_reported_by_torch

T = TypeVar("T")


class QuantDowngradeExhaustedError(RuntimeError):
    """Raised when ``auto_quant_downgrade_on_failure`` cannot lower quant further or step budget is exhausted."""

    def __init__(
        self,
        *,
        role: str,
        repo_id: str,
        last_error: BaseException,
        reason: str = "no_lower_mode",
    ) -> None:
        self.role = role
        self.repo_id = repo_id
        self.last_error = last_error
        self.reason = reason
        if reason == "no_lower_mode":
            msg = (
                f"All quantization levels were exhausted for {role} (model {repo_id!r}). "
                f"The run still failed: {last_error}\n\n"
                "Try a different model or adjust quantization manually on the Model tab. "
                "You can turn off “Auto quant downgrade on failure” if you prefer fixed settings."
            )
        else:
            msg = (
                f"Auto quant downgrade stopped after several attempts for {role} ({repo_id!r}). "
                f"Last error: {last_error}\n\n"
                "Try a different model or lower quality settings on the Model tab."
            )
        super().__init__(msg)


def _persist_quant_settings(settings: AppSettings) -> None:
    try:
        from src.settings.ui_settings import save_settings

        save_settings(settings)
    except Exception:
        pass


def is_dependency_setup_error(exc: BaseException) -> bool:
    """
    True when the failure is missing optional-but-required pip packages or similar setup issues.

    Quant downgrades and VRAM tweaks cannot fix these; retrying only burns steps and confusing messages.
    """
    parts: list[str] = []
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and len(parts) < 8:
        i = id(cur)
        if i in seen:
            break
        seen.add(i)
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or cur.__context__
    blob = "\n".join(parts).lower()
    if "pip install tiktoken" in blob or "`tiktoken` is required" in blob or "no module named 'tiktoken'" in blob:
        return True
    if "sentencepiece" in blob and (
        "not found in your environment" in blob or "requires the sentencepiece" in blob or "pip install sentencepiece" in blob
    ):
        return True
    return False


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


def gpu_mem_used_fraction(device_index: int | None) -> float | None:
    """
    Fraction of total VRAM used on ``device_index`` (0.0–1.0), via ``torch.cuda.mem_get_info``.
    Returns ``None`` when CUDA is unavailable, ``device_index`` is ``None``, or the query fails.
    """
    try:
        import torch

        if not cuda_device_reported_by_torch():
            return None
        if device_index is None:
            return None
        ix = int(device_index)
        if ix < 0 or ix >= int(torch.cuda.device_count()):
            return None
        free_b, total_b = torch.cuda.mem_get_info(ix)
        total_b = float(total_b)
        if total_b <= 0:
            return None
        used_b = total_b - float(free_b)
        return max(0.0, min(1.0, used_b / total_b))
    except Exception:
        return None


def preempt_used_frac_threshold() -> float:
    """Env ``AQUADUCT_VRAM_PREEMPT_USED_FRAC`` (default ``0.99``): preempt when used/total ≥ this."""
    raw = os.environ.get("AQUADUCT_VRAM_PREEMPT_USED_FRAC", "0.99").strip()
    try:
        v = float(raw)
        return max(0.50, min(0.9999, v))
    except ValueError:
        return 0.99


def pick_relief_gpu_index(*, current_index: int | None, gpus: list[GpuDevice]) -> int | None:
    """
    Prefer a larger-VRAM GPU (then equal-VRAM peer), excluding ``current_index``, without tracking OOM failures.

    Same ranking as ``pick_next_gpu_index_after_oom`` but uses a fresh ``failed_indices`` set so preempt moves stay independent of OOM bookkeeping.
    """
    failed: set[int] = set()
    return pick_next_gpu_index_after_oom(
        current_index=current_index,
        failed_indices=failed,
        gpus=gpus,
    )


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
    preempt_high_vram: bool = True,
) -> tuple[T, AppSettings, int | None]:
    """
    Generic retry controller:
    - first attempt: run_cb(settings, cuda_device_index)
    - optional **preempt** (when ``preempt_high_vram``): if device VRAM use ≥ threshold (default 99%, env
      ``AQUADUCT_VRAM_PREEMPT_USED_FRAC``), ``clear_cb()`` then re-check; if still high, switch to a larger /
      equal-VRAM GPU if listed, else lower quant once — **before** running ``run_cb``, to reduce OOM risk.
    - on OOM: try another CUDA device with **more** or **equal** VRAM (never a smaller card), then
    - downgrade quant one step at a time (``max_quant_downgrades``), clearing VRAM between tries.
    - when ``settings.auto_quant_downgrade_on_failure`` is True, a **non-OOM** failure also triggers the same
      one-step quant lowering (per role), persisting settings, until success or
      :class:`QuantDowngradeExhaustedError`.

    Returns (result, settings_after, cuda_device_index_after).
    """
    failed_gpu_indices: set[int] = set()
    quant_steps = 0
    cur_settings = settings
    cur_idx = cuda_device_index

    while True:
        if preempt_high_vram:
            thr = preempt_used_frac_threshold()
            frac = gpu_mem_used_fraction(cur_idx)
            if frac is not None and frac >= thr:
                clear_cb()
                frac = gpu_mem_used_fraction(cur_idx)
            if frac is not None and frac >= thr:
                alt = pick_relief_gpu_index(current_index=cur_idx, gpus=gpus)
                if alt is not None and (cur_idx is None or int(alt) != int(cur_idx)):
                    try:
                        from debug import pipeline_console

                        pipeline_console(
                            f"VRAM nearly full (~{100.0 * frac:.1f}% used on cuda={cur_idx!r}) before "
                            f"{stage_name!r} — moving work to larger/equal VRAM GPU → cuda={alt!r}",
                            stage=stage_name,
                        )
                    except Exception:
                        pass
                    clear_cb()
                    cur_idx = int(alt)
                    continue
                if quant_steps < max_quant_downgrades:
                    new_mode = next_lower_quant_mode(role=role, repo_id=repo_id, settings=cur_settings)
                    if new_mode is not None:
                        try:
                            from debug import pipeline_console

                            pipeline_console(
                                f"VRAM nearly full (~{100.0 * frac:.1f}% used) before {stage_name!r} — "
                                f"preemptively lowering {role} quant → {new_mode!r} "
                                f"(step {quant_steps + 1}/{max_quant_downgrades})",
                                stage=stage_name,
                            )
                        except Exception:
                            pass
                        clear_cb()
                        cur_settings = with_lowered_quant(role=role, new_mode=new_mode, settings=cur_settings)
                        quant_steps += 1
                        _persist_quant_settings(cur_settings)
                        continue

        try:
            out = run_cb(cur_settings, cur_idx)
            return out, cur_settings, cur_idx
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(e, PipelineCancelled):
                raise
            if is_dependency_setup_error(e):
                raise
            if not is_oom_error(e):
                downgrade = bool(getattr(cur_settings, "auto_quant_downgrade_on_failure", False))
                if downgrade and quant_steps < max_quant_downgrades:
                    new_mode = next_lower_quant_mode(role=role, repo_id=repo_id, settings=cur_settings)
                    if new_mode is None:
                        raise QuantDowngradeExhaustedError(
                            role=str(role),
                            repo_id=str(repo_id),
                            last_error=e,
                            reason="no_lower_mode",
                        ) from e
                    try:
                        from debug import pipeline_console

                        pipeline_console(
                            f"Failure in {stage_name!r} ({type(e).__name__}) — lowering {role} quant → {new_mode!r} "
                            f"(auto quant downgrade, step {quant_steps + 1}/{max_quant_downgrades}); retrying…",
                            stage=stage_name,
                        )
                    except Exception:
                        pass
                    clear_cb()
                    cur_settings = with_lowered_quant(role=role, new_mode=new_mode, settings=cur_settings)
                    quant_steps += 1
                    _persist_quant_settings(cur_settings)
                    continue
                if downgrade and quant_steps >= max_quant_downgrades:
                    raise QuantDowngradeExhaustedError(
                        role=str(role),
                        repo_id=str(repo_id),
                        last_error=e,
                        reason="max_steps",
                    ) from e
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
                if bool(getattr(cur_settings, "auto_quant_downgrade_on_failure", False)):
                    raise QuantDowngradeExhaustedError(
                        role=str(role),
                        repo_id=str(repo_id),
                        last_error=e,
                        reason="no_lower_mode",
                    ) from e
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
            _persist_quant_settings(cur_settings)

