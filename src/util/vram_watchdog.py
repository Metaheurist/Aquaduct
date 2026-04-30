"""CUDA VRAM headroom checks before heavy loads — warnings (UI + log) and optional hard stops."""

from __future__ import annotations

import os
from typing import Any

from debug import pipeline_console
from src.runtime.pipeline_notice import emit_pipeline_notice


def _watchdog_disabled() -> bool:
    v = os.environ.get("AQUADUCT_VRAM_WATCHDOG", "1").strip().lower()
    return v in ("0", "false", "no", "off")


def _bytes_from_mib_env(key: str, default_mib: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return float(default_mib) * 1024.0 * 1024.0
    try:
        return float(raw) * 1024.0 * 1024.0
    except ValueError:
        return float(default_mib) * 1024.0 * 1024.0


def _frac_env(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return float(default)
    try:
        return max(0.001, min(0.95, float(raw)))
    except ValueError:
        return float(default)


def _thresholds(total_b: float) -> tuple[float, float]:
    """Returns (warn_free_bytes_minimum, abort_free_bytes_minimum)."""
    warn_abs = _bytes_from_mib_env("AQUADUCT_VRAM_WARN_FREE_MIB", 768.0)
    abort_abs = _bytes_from_mib_env("AQUADUCT_VRAM_ABORT_FREE_MIB", 96.0)
    warn_frac = _frac_env("AQUADUCT_VRAM_WARN_FREE_FRAC", 0.07)
    abort_frac = _frac_env("AQUADUCT_VRAM_ABORT_FREE_FRAC", 0.025)
    warn_need = max(warn_abs, warn_frac * total_b)
    abort_need = max(abort_abs, abort_frac * total_b)
    if abort_need >= warn_need:
        abort_need = warn_need * 0.45
    return warn_need, abort_need


def _fmt_gb(n: float) -> str:
    return f"{float(n) / (1024 ** 3):.2f}"


def check_cuda_headroom(device_index: int | None, *, stage: str) -> None:
    """
    If VRAM free on ``device_index`` is critically low, raise RuntimeError with guidance.

    If moderately low, log + optional UI notice (:func:`emit_pipeline_notice`).
    Skipped when CUDA unavailable, ``device_index`` is None, or ``AQUADUCT_VRAM_WATCHDOG=0``.
    """
    if _watchdog_disabled():
        return
    if device_index is None:
        return
    try:
        import torch

        if not torch.cuda.is_available():
            return
        ix = int(device_index)
        n = int(torch.cuda.device_count())
        if ix < 0 or ix >= n:
            return
        free_b, total_b = torch.cuda.mem_get_info(ix)
        total_b = float(total_b)
        free_b = float(free_b)
        if total_b <= 0:
            return
        warn_need, abort_need = _thresholds(total_b)
        name = ""
        try:
            name = str(torch.cuda.get_device_name(ix))
        except Exception:
            name = f"cuda:{ix}"

        if free_b < abort_need:
            msg = (
                f"{name}: only {_fmt_gb(free_b)} GiB free of {_fmt_gb(total_b)} GiB before {stage}. "
                "Close other GPU apps, enable CPU offload for heavy models, reduce resolution, or disable "
                "multi-stage script refinement. Set AQUADUCT_VRAM_WATCHDOG=0 to skip this guard."
            )
            pipeline_console(msg, stage="vram_watchdog")
            raise RuntimeError(msg)

        if free_b < warn_need:
            msg = (
                f"{name}: {_fmt_gb(free_b)} GiB free of {_fmt_gb(total_b)} GiB before {stage}. "
                "The run may be slow or hit CUDA OOM."
            )
            pipeline_console(msg, stage="vram_watchdog")
            emit_pipeline_notice("Low GPU memory", msg)
    except RuntimeError:
        raise
    except Exception:
        # Never break inference because mem_get_info failed (driver quirks).
        return


def cuda_mem_snapshot(device_index: int | None) -> dict[str, Any] | None:
    """Best-effort VRAM snapshot for logging (torch ``mem_get_info``)."""
    if device_index is None:
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        ix = int(device_index)
        if ix < 0 or ix >= int(torch.cuda.device_count()):
            return None
        free_b, total_b = torch.cuda.mem_get_info(ix)
        total_b = float(total_b)
        free_b = float(free_b)
        if total_b <= 0:
            return None
        used_b = total_b - free_b
        return {
            "device_index": ix,
            "free_gib": free_b / (1024**3),
            "total_gib": total_b / (1024**3),
            "used_frac": max(0.0, min(1.0, used_b / total_b)),
        }
    except Exception:
        return None
