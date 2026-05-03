"""
Place diffusers pipelines on CUDA with optional CPU↔GPU weight movement.

This is not OS "swap" to disk; it is **offload**: weights live in system RAM and are moved to the GPU
for the active module/step, reducing peak VRAM at the cost of speed and some host RAM.

Policy is **auto** from GPU VRAM, total/available system RAM, and optional live ``psutil`` readings.
Override with environment variables when needed (see ``resolve_diffusion_offload_mode``).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from src.util.cuda_capabilities import cuda_device_reported_by_torch

if TYPE_CHECKING:
    from src.core.config import AppSettings

OffloadMode = Literal["none", "model", "sequential"]


def resolve_diffusion_offload_mode(
    settings: AppSettings | None = None,
    *,
    placement_role: Literal["image", "video"] | None = None,
) -> OffloadMode:
    """
    Choose how to stage diffusion weights between CPU RAM and GPU VRAM.

    Environment (highest priority first):

    - ``AQUADUCT_DIFFUSION_CPU_OFFLOAD``:
      - ``auto`` (default) — heuristics from ``get_hardware_info()`` + available RAM; **multiple CUDA
        devices** default to **sequential** offload (lowest peak VRAM on the diffusion GPU).
      - ``off`` / ``none`` / ``0`` / ``false`` — full ``.to("cuda")`` when CUDA is available
      - ``model`` — ``enable_model_cpu_offload()`` (balance of VRAM vs speed)
      - ``sequential`` — ``enable_sequential_cpu_offload()`` (lowest peak VRAM, slowest)

    - ``AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD=1`` (legacy): same as ``sequential`` when the
      variable above is unset or ``auto``.

    Under **VRAM-first multi-GPU** plus **Auto** CUDA routing, ``auto`` may choose full-GPU staging
    (``none``) so video pipelines can shard across devices. **Image** placement
    (``placement_role="image"``) still prefers **model** offload in that regime so resident full
    weights do not routinely OOM moderate-VRAM GPUs (for example SD3.5).
    """
    raw = os.environ.get("AQUADUCT_DIFFUSION_CPU_OFFLOAD", "").strip().lower()
    legacy_seq = os.environ.get("AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    if raw in ("off", "none", "0", "false", "no"):
        return "none"
    if raw == "model":
        return "model"
    if raw == "sequential":
        return "sequential"
    if raw not in ("", "auto"):
        # Unknown token: prefer safe low-VRAM path
        return "sequential"

    # auto (or empty)
    if legacy_seq and raw in ("", "auto"):
        return "sequential"

    return _resolve_auto_offload_mode(settings, placement_role=placement_role)


def _avail_ram_gb() -> float | None:
    try:
        import psutil

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:
        return None


def _cuda_device_count() -> int:
    try:
        import torch

        if cuda_device_reported_by_torch():
            return int(torch.cuda.device_count())
    except Exception:
        pass
    return 0


def _resolve_auto_offload_mode(
    settings: AppSettings | None = None,
    *,
    placement_role: Literal["image", "video"] | None = None,
) -> OffloadMode:
    vram_gb: float | None = None
    try:
        from src.models.hardware import get_hardware_info

        vram_gb = get_hardware_info().vram_gb
    except Exception:
        pass

    avail_gb = _avail_ram_gb()

    if vram_gb is None:
        # No GPU info: sequential offload is the safest default when CUDA still works but VRAM unknown
        return "sequential"

    # Multiple GPUs: default to sequential offload unless VRAM-first intra-shard mode is enabled —
    # that path prefers resident GPU weights so peer submodule moves can distribute work.
    if _cuda_device_count() >= 2:
        try:
            from src.gpu.multi_device.gates import vram_first_master_enabled

            if settings is not None and vram_first_master_enabled(settings):
                # Video sharding prefers resident GPU tensors; single-GPU image T2I on the diffusion
                # device still needs headroom alongside other workloads — avoid full ``pipe.to()`` here.
                if placement_role == "image":
                    if avail_gb is not None and avail_gb < 3.0:
                        return "sequential"
                    return "model"
                if avail_gb is None or avail_gb >= 8.0:
                    return "none"
        except Exception:
            pass
        return "sequential"

    # Very little free host RAM: avoid aggressive CPU staging (offload copies weights through RAM).
    # Prefer keeping the full pipeline on GPU only when VRAM is comfortably large.
    # 8–15 GB: full-GPU diffusion after LLM / image stages routinely OOMs (e.g. SVD img2vid on GPU 1).
    if avail_gb is not None and avail_gb < 3.0 and vram_gb >= 16.0:
        return "none"

    if vram_gb >= 16.0:
        if avail_gb is None or avail_gb >= 4.0:
            return "none"
        return "model"

    if vram_gb >= 8.0:
        return "model"

    return "sequential"


def dispose_diffusion_pipeline(pipe: object) -> None:
    """
    Detach diffusers offload hooks before deleting a pipeline reference.

    ``enable_model_cpu_offload`` / ``enable_sequential_cpu_offload`` register accelerate hooks;
    without clearing them first, dangling references often keep weights in heap memory until the
    process exits—even after Python ``gc`` and ``torch.cuda.empty_cache``.

    Older diffusers without ``maybe_free_model_hooks`` are a no-op.
    """

    try:
        fn = getattr(pipe, "maybe_free_model_hooks", None)
        if callable(fn):
            fn()
    except Exception:
        pass


def place_diffusion_pipeline(
    pipe,
    cuda_device_index: int | None = None,
    *,
    force_offload: OffloadMode | None = None,
    inference_settings: AppSettings | None = None,
    model_repo_id: str | None = None,
    placement_role: Literal["image", "video"] | None = None,
    quant_mode: str | None = None,
) -> None:
    """
    Move a diffusers ``pipe`` to CPU, or CUDA with none/model/sequential offload per
    ``resolve_diffusion_offload_mode()``.

    When ``cuda_device_index`` is set, full-GPU mode uses ``cuda:{index}``; offload modes
    pass ``gpu_id`` when the installed diffusers build supports it.

    ``force_offload`` overrides the env-driven decision (used by quant-mode ``cpu_offload``).
    """
    import torch

    try:
        if inference_settings is not None and bool(getattr(inference_settings, "_force_cpu_diffusion", False)):
            pipe.to("cpu")
            return
    except Exception:
        pass

    if not cuda_device_reported_by_torch():
        pipe.to("cpu")
        return

    dev = f"cuda:{int(cuda_device_index)}" if cuda_device_index is not None else "cuda"

    mode = (
        force_offload
        if force_offload is not None
        else resolve_diffusion_offload_mode(inference_settings, placement_role=placement_role)
    )
    if mode == "none":
        pipe.to(dev)
        _maybe_apply_vram_first_peer_modules(
            pipe,
            inference_settings=inference_settings,
            cuda_device_index=cuda_device_index,
            model_repo_id=model_repo_id,
            placement_role=placement_role,
            quant_mode=quant_mode,
            offload_mode=mode,
        )
        return

    if mode == "model":
        try:
            if cuda_device_index is not None:
                pipe.enable_model_cpu_offload(gpu_id=int(cuda_device_index))
            else:
                pipe.enable_model_cpu_offload()
            return
        except TypeError:
            try:
                pipe.enable_model_cpu_offload()
                return
            except Exception:
                pass
        except Exception:
            pass
        if _try_sequential_cpu_offload(pipe, cuda_device_index):
            return
        pipe.to(dev)
        _maybe_apply_vram_first_peer_modules(
            pipe,
            inference_settings=inference_settings,
            cuda_device_index=cuda_device_index,
            model_repo_id=model_repo_id,
            placement_role=placement_role,
            quant_mode=quant_mode,
            offload_mode="none",
        )
        return

    # sequential
    if _try_sequential_cpu_offload(pipe, cuda_device_index):
        return
    try:
        if cuda_device_index is not None:
            pipe.enable_model_cpu_offload(gpu_id=int(cuda_device_index))
        else:
            pipe.enable_model_cpu_offload()
        return
    except Exception:
        pass
    pipe.to(dev)
    _maybe_apply_vram_first_peer_modules(
        pipe,
        inference_settings=inference_settings,
        cuda_device_index=cuda_device_index,
        model_repo_id=model_repo_id,
        placement_role=placement_role,
        quant_mode=quant_mode,
        offload_mode="none",
    )


def _maybe_apply_vram_first_peer_modules(
    pipe,
    *,
    inference_settings: AppSettings | None,
    cuda_device_index: int | None,
    model_repo_id: str | None,
    placement_role: Literal["image", "video"] | None,
    quant_mode: str | None,
    offload_mode: OffloadMode,
) -> None:
    if not model_repo_id or not placement_role:
        return
    try:
        from src.gpu.multi_device.gates import effective_diffusion_quant
        from src.gpu.multi_device.runtime import maybe_apply_diffusion_peer_modules

        qm = effective_diffusion_quant(
            role=placement_role,
            settings=inference_settings,
            quant_mode_raw=str(quant_mode or "auto"),
            repo_id=str(model_repo_id),
        )
        ok, note = maybe_apply_diffusion_peer_modules(
            pipe,
            settings=inference_settings,
            model_id=str(model_repo_id),
            cuda_device_index=cuda_device_index,
            role=placement_role,
            resolved_quant_mode=qm,
            offload_mode=str(offload_mode),
        )
        from debug import debug_enabled, dprint

        if debug_enabled("gpu_plan"):
            dprint("gpu_plan", "diffusion_placement", f"peer_modules={ok}", note, f"repo={model_repo_id!r}")
    except Exception:
        pass


def _try_sequential_cpu_offload(pipe, cuda_device_index: int | None) -> bool:
    """Call diffusers ``enable_sequential_cpu_offload`` with ``gpu_id`` when available."""
    try:
        if cuda_device_index is not None:
            pipe.enable_sequential_cpu_offload(gpu_id=int(cuda_device_index))
        else:
            pipe.enable_sequential_cpu_offload()
        return True
    except TypeError:
        try:
            pipe.enable_sequential_cpu_offload()
            return True
        except Exception:
            return False
    except Exception:
        return False
