"""
Stage boundaries between heavy pipeline phases.

Delegates exclusively to :func:`cleanup_vram` and :func:`prepare_for_next_model` — no duplicate
CUDA cache or watchdog logic.
"""

from __future__ import annotations

from typing import Literal

from debug import dprint
from src.util.utils_vram import cleanup_vram, prepare_for_next_model

ReleaseVariant = Literal["cheap", "prepare_diffusion"]


def release_between_stages(
    stage: str,
    *,
    cuda_device_index: int | None = None,
    variant: ReleaseVariant = "cheap",
) -> None:
    """
    Release host/Python refs and CUDA allocator slack between major stages.

    - ``cheap``: :func:`cleanup_vram` only (gc + ``empty_cache`` / ipc_collect).
    - ``prepare_diffusion``: :func:`prepare_for_next_model` with ``cuda_device_index`` so optional
      VRAM watchdog runs when configured.

    Raises ``RuntimeError`` from :func:`~src.util.vram_watchdog.check_cuda_headroom` when watchdog
    aborts (same as calling ``prepare_for_next_model`` directly).
    """
    dprint("memory_budget", stage, variant, f"cuda={cuda_device_index!r}")
    if variant == "prepare_diffusion":
        prepare_for_next_model(cuda_device_index)
        return
    cleanup_vram()
