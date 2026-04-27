# Hardware + model fit rules

## Purpose
The **My PC** tab displays detected hardware and estimates how well each curated model option will run on your machine.

The **Model** tab **Auto-fit for this PC** button uses the same VRAM/RAM heuristics to pick script, image, video, and voice repos from the curated list (`rank_models_for_auto_fit` in `src/models/hardware.py`).

Implemented in:
- `src/models/hardware.py`

## Hardware detection (best-effort)
The app attempts to detect:
- OS + CPU (via `platform`)
- RAM: total physical memory on Windows (`GlobalMemoryStatusEx`); on other OSes or if that fails, **`psutil.virtual_memory().total`**
- **GPUs + VRAM (multi-GPU)**:
  - Prefer **`torch.cuda`**: enumerate **`range(torch.cuda.device_count())`** and read names, total VRAM, multiprocessor count, and compute capability from **`torch.cuda.get_device_properties(i)`** (same ordinals local inference uses).
  - **Fallback** when CUDA is not loaded: parse **all** lines from **`nvidia-smi --query-gpu=name,memory.total`** (CSV).

If a field can’t be detected, the UI shows “(not detected)”.

### GPU policy (Auto vs single)
The desktop UI uses a segmented **Auto** \| **Select GPU** control on the **My PC** tab (see [ui.md](../ui/ui.md)); behavior below is the same whether you use that control or edit **`ui_settings.json`** directly.

Configured on the **My PC** tab and persisted in **`ui_settings.json`** (see [config.md](config.md)):
- **Auto**: **VRAM-heavy** local work (**image** / **video** diffusion) targets the GPU with the **largest total VRAM** (ties: lower CUDA index wins). **Script (LLM)** targets a **heuristic “compute”** GPU (multiprocessor count × clock rate — not a benchmark; newer/faster cards rank higher when VRAM alone does not decide). If **both** heuristics would choose the **same** CUDA index (for example two cards with equal VRAM so the tie goes to index 0, which also wins on compute), the **LLM** is moved to the **best remaining** GPU by the same compute score so **two GPUs** are used instead of stacking every stage on one card ([`src/util/cuda_device_policy.py`](../../src/util/cuda_device_policy.py)). When **at least two** CUDA devices are present, **LLM and diffusion indices are never the same** in Auto (so two heavy models are not assigned to one GPU by routing policy).
- **Single GPU**: pin **all** local CUDA stages to the chosen device index (LLM + diffusion + fit heuristics for that pin).

**Environment override**: if **`AQUADUCT_CUDA_DEVICE`** is set to a non-negative integer or **`cuda:N`**, that index is used for **every** stage and overrides the saved UI policy. See [`src/util/cuda_device_policy.py`](../../src/util/cuda_device_policy.py).

**Fit heuristics** (`effective_vram_gb_for_kind` in the same module): **script** rows use the LLM device’s VRAM; **image** / **video** use the diffusion device’s VRAM; **voice** follows the same device as the LLM slot for labeling (voice often runs on CPU in practice).

## Resource usage graph (title bar 📈)
The sample shows **CPU for the whole process tree** (Python plus subprocesses such as FFmpeg), **RSS for the tree**, and **CUDA free/total VRAM** for a **selected GPU** (combo when multiple GPUs are present; choice is persisted). VRAM often **drops** after a GPU stage finishes (e.g. after Pro text-to-video clips, while the pipeline muxes audio/captions with FFmpeg). The pipeline **runs stages sequentially** and may **unload** models between steps to limit peak memory — it is not designed to keep every model resident at maximum utilization at once.

For **local diffusion** (image + video model slots), the app can also use **CPU offload** (weights staged in system RAM vs VRAM) with automatic rules from VRAM + free RAM. With **multiple CUDA devices**, **`auto`** offload defaults to **sequential** staging on the **diffusion** GPU index to keep peak VRAM low — see [Performance: Diffusion VRAM vs system RAM](../pipeline/performance.md#diffusion-vram-vs-system-ram-cpu-offload) and [`src/util/diffusion_placement.py`](../../src/util/diffusion_placement.py).

## Minimum requirements (guidance)
Recommended for best results:
- **GPU VRAM**: ≥ 8GB
- **RAM**: ≥ 16GB

The pipeline can still run with fallbacks (template scripts, placeholder images) if a model can’t load.

## Fit markers
The My PC tab assigns each model option a marker (internal codes; UI labels match **`fit_marker_display()`** in `src/models/hardware.py`):
- `EXCELLENT`
- `OK`
- `RISKY`
- `NO_GPU` — shown in the UI as **VRAM Limit** (not enough VRAM for that model kind at the **effective** policy GPU)
- `UNKNOWN`

**Effective VRAM**: thresholds use the VRAM of the GPU resolved for that **kind** and the active **GPU policy** (Auto vs single), not “first GPU only” when multiple cards exist.

These are simple heuristics based mainly on VRAM and the model kind. **`rate_model_fit_for_repo`** also applies **per-repo** thresholds for frontier checkpoints (e.g. **FLUX** / **SD3.5**, **Wan 2.2** / **Mochi 1.5** / **CogVideoX 5B** / **HunyuanVideo** / **LTX-2** for T2V, and user-typed **SVD** / **LTX-Video** / **ZeroScope** ids) — see [`src/models/hardware.py`](../../src/models/hardware.py) (`vram_requirement_hint`, `rate_model_fit_for_repo`).

- **Image (SDXL Turbo class default)**:
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

### LLM on multiple GPUs (limits)
Stage routing picks **one** CUDA index for the local script model (see GPU policy above). **Model-parallel** splitting of a single LLM across two cards via Accelerate `max_memory` / multi-device `device_map` is **not** turned on automatically. **4-bit (bitsandbytes)** loading typically requires a **single** GPU; if you need multi-GPU LLM sharding, prefer FP16 and expect manual tuning outside this app.

## Quant-aware fit & VRAM prediction
The **Settings → Model** tab adds a per-row **quant** dropdown beside each repo combo. The VRAM label and `rate_model_fit_for_repo` then reflect the **predicted** memory at the chosen mode (e.g. `~7-9 GB · NF4 4-bit`) using `predict_vram_gb` in [`src/models/quantization.py`](../../src/models/quantization.py). `Auto` resolves through `pick_auto_mode` against the **effective per-role VRAM** (so it tracks the same GPU policy as the fit badges). **Auto-fit for this PC** now selects both the repo and the quant mode per row — see [quantization](quantization.md).
