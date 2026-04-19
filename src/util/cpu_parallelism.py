"""
Tune host CPU parallelism for NumPy, BLAS, and PyTorch.

Call :func:`configure_cpu_parallelism` **before** importing NumPy or PyTorch so OpenMP-backed
libraries respect thread limits (avoids 32× oversubscription on large CPUs).

Environment:

- ``AQUADUCT_CPU_THREADS`` — target thread count for BLAS/OpenMP and ``torch.set_num_threads``
  (default: ``min(32, max(1, os.cpu_count()))``). Ignored for a variable that is **already** set
  in the process environment (e.g. ``OMP_NUM_THREADS``).

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


def apply_torch_cpu_settings(torch) -> None:
    """
    After ``import torch``, align PyTorch CPU thread pools with :func:`effective_cpu_thread_count`.

    Inter-op parallelism stays small to avoid oversubscription during GPU-bound workloads.
    """
    global _TORCH_CPU_CONFIGURED
    if _TORCH_CPU_CONFIGURED:
        return
    n = effective_cpu_thread_count()
    # Inter-op parallelism: keep modest to reduce CPU contention when GPU-bound.
    inter = max(1, min(8, max(1, n // 4)))
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

