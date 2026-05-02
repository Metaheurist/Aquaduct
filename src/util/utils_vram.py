from __future__ import annotations

import gc
from contextlib import contextmanager

from src.util.cuda_capabilities import cuda_device_reported_by_torch


def cleanup_vram() -> None:
    """
    Release references and return GPU memory to the allocator.
    Call between major stages (LLM → TTS → diffusion) to reduce peak VRAM; slightly slower.

    On multi-GPU machines, empties the CUDA cache on **each** device — a single
    ``empty_cache()`` only targeted the current device in some configurations, which could
    leave several GB reserved before the next large load (e.g. Wan T2V after LLM/TTS on another card).
    """
    # Multiple GC passes helps release large graphs sooner (CPU RAM + VRAM).
    gc.collect()
    gc.collect()
    try:
        import torch

        if cuda_device_reported_by_torch():
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            try:
                n = int(torch.cuda.device_count())
                for di in range(n):
                    try:
                        with torch.cuda.device(di):
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
            except Exception:
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
    except Exception:
        # Best-effort cleanup; never crash the pipeline on cleanup.
        return


def purge_process_memory_aggressive() -> None:
    """
    Manual / UI purge: extra ``gc`` passes and CUDA cache flush on **every** device.

    Frees **unreachable** Python objects and returns memory held in PyTorch's CUDA caching
    allocator to the driver. Does **not** unload models that are still referenced (e.g. a
    running pipeline worker holding a pipeline in memory).
    """
    for _ in range(4):
        try:
            gc.collect()
        except Exception:
            break
    try:
        import torch
    except Exception:
        return

    try:
        if cuda_device_reported_by_torch():
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            try:
                n = int(torch.cuda.device_count())
                for di in range(n):
                    try:
                        with torch.cuda.device(di):
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
            except Exception:
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            try:
                torch.mps.empty_cache()
            except Exception:
                pass
    except Exception:
        pass


def prepare_for_next_model(cuda_device_index: int | None = None) -> None:
    """
    Explicit stage boundary between big model loads.
    This prefers lower peak VRAM/RAM over speed.

    When ``cuda_device_index`` is set and ``AQUADUCT_VRAM_WATCHDOG`` is enabled, checks free VRAM on
    that device after cleanup (warn UI / abort if critically low).
    """
    cleanup_vram()
    try:
        from src.util.vram_watchdog import check_cuda_headroom

        if cuda_device_index is not None:
            check_cuda_headroom(int(cuda_device_index), stage="between pipeline stages (before next GPU load)")
            return
        # When the active CUDA index is unknown (e.g. generic OOM cleanup), still check every device.
        try:
            import torch

            if cuda_device_reported_by_torch():
                n = int(torch.cuda.device_count())
                for di in range(n):
                    check_cuda_headroom(di, stage="between pipeline stages (VRAM cleanup, all devices)")
        except RuntimeError:
            raise
        except Exception:
            pass
    except RuntimeError:
        raise
    except Exception:
        pass


@contextmanager
def vram_guard():
    try:
        yield
    finally:
        cleanup_vram()

