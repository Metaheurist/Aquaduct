"""
Shared CUDA eligibility for Aquaduct.

Prefer using the GPU whenever PyTorch reports a CUDA device, even when a conservative
kernel smoke test fails (some wheels/driver combos report CUDA but omit specific ops).
"""


def torch_cuda_kernels_work() -> bool:
    """
    True only if basic CUDA tensor ops run on device 0.

    PyTorch wheels omit SASS for some GPUs; ``cuda.is_available()`` can still be True
    while kernels fail with "no kernel image is available".
    """
    import torch

    try:
        from src.util.cpu_parallelism import apply_torch_cpu_settings

        apply_torch_cpu_settings(torch)
    except Exception:
        pass

    if not torch.cuda.is_available():
        return False
    try:
        x = torch.tensor([0, 1], device="cuda", dtype=torch.long)
        torch.isin(x, x)
        return True
    except RuntimeError:
        return False


def cuda_device_reported_by_torch() -> bool:
    """True when PyTorch exposes at least one CUDA device."""
    try:
        import torch

        return bool(torch.cuda.is_available() and torch.cuda.device_count() > 0)
    except Exception:
        return False


def cuda_ok_for_torch_workloads() -> bool:
    """Use CUDA for heavy torch workloads when probes pass or a CUDA device is visible."""
    return torch_cuda_kernels_work() or cuda_device_reported_by_torch()


# Alias for script/LLM loader call sites that predate the shared helper name.
cuda_ok_for_llm_load = cuda_ok_for_torch_workloads
