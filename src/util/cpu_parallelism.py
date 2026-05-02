"""
Tune **host CPU** parallelism for NumPy, BLAS, and PyTorch CPU thread pools.

This is about **logical CPU cores** used by OpenMP/BLAS and PyTorch **CPU** ops — not CUDA
“multithreading” or extra GPU streams. GPU inference stays whatever PyTorch/your driver do per kernel;
we only cap **CPU-side** thread pools so libraries do not oversubscribe the host (e.g. 32× OpenMP).

Call :func:`configure_cpu_parallelism` **before** importing NumPy or PyTorch so OpenMP-backed
libraries respect thread limits (avoids 32× oversubscription on large CPUs).

Environment:

- ``AQUADUCT_CPU_THREADS`` — target thread count for BLAS/OpenMP and ``torch.set_num_threads``
  (default: ``min(32, max(1, os.cpu_count()))``). Ignored for a variable that is **already** set
  in the process environment (e.g. ``OMP_NUM_THREADS``).

- ``AQUADUCT_TORCH_INTEROP_THREADS`` — optional override for ``torch.set_num_interop_threads`` (1–32).
  When unset, the app uses a **higher** inter-op cap on **CPU-only** machines (no CUDA/MPS) so
  independent CPU ops can overlap across more cores; with an accelerator it stays **modest** to
  reduce CPU contention while work is mostly GPU-bound.

- Existing ``OMP_NUM_THREADS``, ``MKL_NUM_THREADS``, ``OPENBLAS_NUM_THREADS``, ``NUMEXPR_NUM_THREADS``,
  ``VECLIB_MAXIMUM_THREADS`` — never overwritten if already set.
"""

from __future__ import annotations

import os

_CONFIGURED = False
_TORCH_CPU_CONFIGURED = False

_ENV_KEYS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def effective_cpu_thread_count() -> int:
    """Logical cap for math libraries and PyTorch CPU ops."""
    raw = os.environ.get("AQUADUCT_CPU_THREADS", "").strip()
    if raw:
        try:
            n = int(raw)
            return max(1, min(256, n))
        except ValueError:
            pass
    cpu = os.cpu_count() or 4
    return max(1, min(32, int(cpu)))


def configure_cpu_parallelism() -> None:
    """
    Set BLAS/OpenMP thread environment variables before NumPy loads MKL/OpenBLAS.

    Safe to call multiple times (no-op after first successful run).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    n = effective_cpu_thread_count()
    for key in _ENV_KEYS:
        if key not in os.environ or not str(os.environ.get(key, "")).strip():
            os.environ[key] = str(n)
    _CONFIGURED = True


def _accelerator_available(torch) -> bool:
    """True when CUDA or Apple MPS is available (work is mostly off the host CPU)."""
    try:
        from src.util.cuda_capabilities import cuda_device_reported_by_torch

        if cuda_device_reported_by_torch():
            return True
    except Exception:
        pass
    try:
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return True
    except Exception:
        pass
    return False


def torch_interop_thread_count(cpu_thread_budget: int, *, accelerator_available: bool) -> int:
    """
    Target for ``torch.set_num_interop_threads``: parallel independent CPU ops in PyTorch.

    CPU-only runs can use a larger value so more cores participate in overlapping CPU work.
    When ``accelerator_available`` is True, keep the value modest to limit host CPU contention
    while the GPU (or MPS) runs the heavy kernels.
    """
    raw = os.environ.get("AQUADUCT_TORCH_INTEROP_THREADS", "").strip()
    if raw:
        try:
            return max(1, min(32, int(raw)))
        except ValueError:
            pass
    n = max(1, cpu_thread_budget)
    if accelerator_available:
        return max(1, min(8, max(1, n // 4)))
    return max(2, min(16, max(2, n // 2)))


def apply_torch_cpu_settings(torch) -> None:
    """
    After ``import torch``, align PyTorch CPU thread pools with :func:`effective_cpu_thread_count`.

    Intra-op threads (``set_num_threads``) follow ``AQUADUCT_CPU_THREADS``. Inter-op threads follow
    :func:`torch_interop_thread_count` so CPU-only machines use more overlapping CPU work; accelerated
    machines keep inter-op modest.
    """
    global _TORCH_CPU_CONFIGURED
    if _TORCH_CPU_CONFIGURED:
        return
    n = effective_cpu_thread_count()
    inter = torch_interop_thread_count(n, accelerator_available=_accelerator_available(torch))
    try:
        torch.set_num_interop_threads(inter)
    except Exception:
        pass
    try:
        torch.set_num_threads(n)
    except Exception:
        pass
    _TORCH_CPU_CONFIGURED = True


def io_bound_pool_workers(*, cap: int = 24) -> int:
    """Worker count for network-bound tasks (e.g. Hugging Face Hub probes)."""
    cpu = os.cpu_count() or 4
    return max(4, min(cap, cpu * 3))


def disk_bound_verify_workers(*, cap: int = 4) -> int:
    """Parallel verify jobs across different repos; keep low to avoid disk thrash."""
    cpu = os.cpu_count() or 4
    return max(1, min(cap, max(1, cpu // 2)))

