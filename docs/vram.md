# `src/util/utils_vram.py` — VRAM / memory cleanup

## Purpose
Keep the pipeline stable on **8GB VRAM** by aggressively freeing memory between stages.

## What it does
- `cleanup_vram()`:
  - `gc.collect()`
  - `torch.cuda.empty_cache()` + `torch.cuda.ipc_collect()` (best-effort)
- `vram_guard()` context manager:
  - wraps a stage and always runs cleanup afterward

## Why it matters
The pipeline may load:
- a quantized LLM
- SDXL Turbo FP16
- (optionally) TTS on GPU

Loading these simultaneously can cause OOM. Staging + cleanup reduces the chance of VRAM fragmentation and OOM errors.

## Multi-GPU (related)
Which **CUDA device** holds the local LLM vs diffusion for a run follows **GPU policy** in the desktop **My PC** tab (persisted in `ui_settings.json`) or the optional **`AQUADUCT_CUDA_DEVICE`** environment override — not covered by `cleanup_vram()` alone. See [Hardware + model fit](hardware.md) and [Config: multi-GPU](config.md#multi-gpu-cuda-policy-override).

**Diffusion offload** ([`src/util/diffusion_placement.py`](../src/util/diffusion_placement.py)): with multiple CUDA devices, **`AQUADUCT_DIFFUSION_CPU_OFFLOAD=auto`** defaults to **sequential** staging on the diffusion GPU to reduce peak VRAM; see [Performance](performance.md#diffusion-vram-vs-system-ram-cpu-offload) and [Config](config.md#diffusion-cpu-offload-local-image--video).

