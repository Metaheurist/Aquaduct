# Hardware + model fit rules

## Purpose
The **My PC** tab displays detected hardware and estimates how well each curated model option will run on your machine.

The **Model** tab **Auto-fit for this PC** button uses the same VRAM/RAM heuristics to pick script, video, and voice repos from the curated list (`rank_models_for_auto_fit` in `src/models/hardware.py`).

Implemented in:
- `src/models/hardware.py`

## Hardware detection (best-effort)
The app attempts to detect:
- OS + CPU (via `platform`)
- RAM (Windows: `GlobalMemoryStatusEx`)
- GPU + VRAM:
  - primary: `nvidia-smi --query-gpu=name,memory.total`
  - fallback: `torch.cuda` device properties (if PyTorch is installed and CUDA is available)

If a field can’t be detected, the UI shows “(not detected)”.

## Minimum requirements (guidance)
Recommended for best results:
- **GPU VRAM**: ≥ 8GB
- **RAM**: ≥ 16GB

The pipeline can still run with fallbacks (template scripts, placeholder images) if a model can’t load.

## Fit markers
The My PC tab assigns each model option a marker:
- `EXCELLENT`
- `OK`
- `RISKY`
- `NO_GPU`
- `UNKNOWN`

These are simple heuristics based mainly on VRAM and the model kind:
- **Video/images (SDXL Turbo)**:
  - `EXCELLENT`: ≥ 10GB VRAM
  - `OK`: ≥ 8GB VRAM
  - `RISKY`: ≥ 6GB VRAM
  - `NO_GPU`: < 6GB VRAM (placeholder images are used)
- **Script (LLM)**:
  - Assumes small 1.5B–3B class models with 4-bit target.
  - `EXCELLENT`: ≥ 8GB VRAM
  - `OK`: ≥ 3–5GB VRAM depending on speed label
  - `RISKY`: below that (pipeline falls back to template scripting)
- **Voice (TTS)**:
  - Marked `OK` because the MVP has an offline TTS fallback.

These rules are meant to be conservative and easy to understand, not perfect benchmarks.

