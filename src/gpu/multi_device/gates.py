"""Feature gates for intra-model multi-GPU (VRAM-first mode)."""

from __future__ import annotations

from typing import cast

from src.core.config import AppSettings
from src.util.cuda_capabilities import cuda_device_reported_by_torch
from src.util.cuda_device_policy import cuda_env_override_device_index


def vram_first_master_enabled(settings: AppSettings | None) -> bool:
    if settings is None:
        return False
    if str(getattr(settings, "multi_gpu_shard_mode", "off") or "off").strip().lower() != "vram_first_auto":
        return False
    if str(getattr(settings, "gpu_selection_mode", "auto") or "auto").strip().lower() != "auto":
        return False
    if cuda_env_override_device_index() is not None:
        return False
    try:
        import torch

        if cuda_device_reported_by_torch() and torch.cuda.device_count() >= 2:
            return True
    except Exception:
        pass
    return False


def llm_float_quant_ok(effective_quant: str) -> bool:
    return effective_quant.strip().lower() in ("bf16", "fp16")


def diffusion_quant_allows_peer_split(effective_quant: str) -> bool:
    qq = effective_quant.strip().lower()
    if qq in ("nf4_4bit", "int8", "cpu_offload"):
        return False
    return qq in ("bf16", "fp16")


def effective_diffusion_quant(
    *,
    role: str,
    settings: AppSettings | None,
    quant_mode_raw: str,
    repo_id: str,
) -> str:
    """Resolve ``auto`` quantization for diffusion offload / shard gates."""
    qm = quant_mode_raw.strip().lower()
    if qm != "auto" or settings is None:
        return qm
    try:
        from src.models.hardware import effective_vram_gb_for_kind, list_cuda_gpus
        from src.models.quantization import QuantRole, pick_auto_mode

        gpus = list_cuda_gpus()
        rk = role.strip().lower()
        qr: str = rk if rk in ("image", "video") else "image"
        v = effective_vram_gb_for_kind(cast(QuantRole, qr), gpus, settings)
        return str(pick_auto_mode(role=cast(QuantRole, qr), repo_id=str(repo_id or ""), vram_gb=v, cuda_ok=True))
    except Exception:
        return qm