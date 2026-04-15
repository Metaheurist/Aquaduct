from __future__ import annotations

import gc
from contextlib import contextmanager


def cleanup_vram() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        # Best-effort cleanup; never crash the pipeline on cleanup.
        return


@contextmanager
def vram_guard():
    try:
        yield
    finally:
        cleanup_vram()

