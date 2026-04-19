from __future__ import annotations

import gc
from contextlib import contextmanager


def cleanup_vram() -> None:
    """
    Release references and return GPU memory to the allocator.
    Call between major stages (LLM → TTS → diffusion) to reduce peak VRAM; slightly slower.
    """
    # Multiple GC passes helps release large graphs sooner (CPU RAM + VRAM).
    gc.collect()
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        # Best-effort cleanup; never crash the pipeline on cleanup.
        return


def prepare_for_next_model() -> None:
    """
    Explicit stage boundary between big model loads.
    This prefers lower peak VRAM/RAM over speed.
    """
    cleanup_vram()


@contextmanager
def vram_guard():
    try:
        yield
    finally:
        cleanup_vram()

