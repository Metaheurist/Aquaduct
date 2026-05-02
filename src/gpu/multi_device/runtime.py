"""Runtime orchestration hooks (LLM Accelerate slicing + diffusion peer submodule moves)."""

from __future__ import annotations

from typing import Any

from src.core.config import AppSettings
from src.gpu.multi_device.gates import diffusion_quant_allows_peer_split, llm_float_quant_ok, vram_first_master_enabled
from src.gpu.multi_device.hardware_budget import build_accelerate_max_memory, list_cuda_memory_estimates
from src.gpu.multi_device.registry import lookup_shard_row, normalize_hub_repo_id
from src.gpu.multi_device.validators import first_peer_index


def resolve_llm_device_map_and_max_memory(
    *,
    settings: AppSettings | None,
    hub_model_id: str | None,
    cuda_device_index: int | None,
    effective_quant: str,
) -> tuple[Any, dict[int | str, str] | None, str]:
    """
    Return ``(device_map, max_memory_optional, telemetry_note)``.

    Non-None ``max_memory`` pairs ``device_map="balanced"`` for Accelerate multi-device slicing.
    """
    note = "legacy_llm_single_device"
    idx = cuda_device_index
    single_dm: dict[str, int]
    single_dm = {"": int(idx)} if idx is not None else {"": 0}

    if not vram_first_master_enabled(settings):
        return single_dm, None, note
    rn = normalize_hub_repo_id(str(hub_model_id or ""))
    row = lookup_shard_row(role="script", repo_id=rn if rn else "")
    if row.vram_first_strategy == "unsupported_intra_shard" or row.vram_first_strategy != "accelerate_llm_balanced":
        return single_dm, None, note
    if not row.llm_allow_accelerate_multi:
        return single_dm, None, note

    qq = effective_quant.strip().lower()
    if not llm_float_quant_ok(qq):
        note = "llm_shard_skipped_quant_gate"
        return single_dm, None, note

    try:
        import torch

        if not getattr(torch.cuda, "is_available", lambda: False)():
            return single_dm, None, note

        nc = int(torch.cuda.device_count())
        if nc < 2:
            return single_dm, None, note
        estimates = list_cuda_memory_estimates(nc)
        mm = build_accelerate_max_memory(estimates=estimates)
        if cuda_device_index is not None and first_peer_index(int(cuda_device_index), nc) is None:
            return single_dm, None, note

        note = "accelerate_balanced_max_memory_llm"
        return "balanced", mm, note
    except Exception:
        note = "llm_shard_skipped_runtime_error"
        return single_dm, None, note


def maybe_apply_diffusion_peer_modules(
    pipe: Any,
    *,
    settings: AppSettings | None,
    model_id: str,
    cuda_device_index: int | None,
    role: str,
    resolved_quant_mode: str,
    offload_mode: str,
) -> tuple[bool, str]:
    """Move registry-listed submodules onto a peer CUDA ordinal when offload is ``none``."""
    rid = normalize_hub_repo_id(str(model_id or ""))
    if not vram_first_master_enabled(settings):
        return False, "diffusion_peer_skipped_settings"
    if cuda_device_index is None:
        return False, "diffusion_peer_skipped_no_cuda_primary"
    if str(offload_mode or "").strip().lower() != "none":
        return False, "diffusion_peer_skipped_offload_not_none"

    rq = normalize_hub_repo_id(role)
    rrole = rq if rq in ("image", "video") else "image"
    if not diffusion_quant_allows_peer_split(resolved_quant_mode):
        return False, "diffusion_peer_skipped_quant_gate"

    row = lookup_shard_row(role=rrole, repo_id=rid if rid else "")
    if row.vram_first_strategy != "diffusion_peer_modules":
        return False, "diffusion_peer_skipped_row_strategy_not_peer"
    mods = tuple(row.diffusion_peer_modules)
    if not mods:
        return False, "diffusion_peer_skipped_empty_peer_list"

    try:
        import torch
        import torch.nn as nn
    except Exception:
        return False, "diffusion_peer_skipped_torch_nn"

    if not getattr(torch.cuda, "is_available", lambda: False)():
        return False, "diffusion_peer_skipped_no_cuda"

    nc = int(torch.cuda.device_count())
    peer_idx = first_peer_index(int(cuda_device_index), nc)
    if peer_idx is None:
        return False, "diffusion_peer_skipped_no_peer_cuda"

    dev_peer = torch.device(f"cuda:{peer_idx}")

    applied = False
    for attr in mods:
        m = getattr(pipe, attr, None)
        if m is None:
            continue
        if isinstance(m, nn.Module):
            try:
                m.to(dev_peer)
                applied = True
            except Exception:
                continue

    if applied:
        return True, f"diffusion_peer_applied_{rid or 'fallback'}:_to_cuda_{peer_idx}"
    return False, "diffusion_peer_no_modules_moved"
