# `src/render/artist.py` — Artist (Images)

## Purpose
Generate 5–10 visuals per video based on script beat prompts.

## Primary mode
- Model: curated defaults are **FLUX.1** and **SD3.5** (see `model_options()`), or any user-pasted T2I Hub id
- **VRAM profiles (local)**: when `generate_images(..., inference_settings=...)` is set (UI / `main.run_once`), [`merge_t2i_from_settings`](../../src/models/inference_profiles.py) adjusts width, height, steps, and guidance from **`pick_image_profile`** on top of [`_diffusion_kw_for_model`](../../src/render/artist.py). See [Inference profiles](../reference/inference_profiles.md).
- Library: `diffusers` (`AutoPipelineForText2Image` / `AutoPipelineForImage2Image`)
- **SDXL / SD 1.5-class** (if used): **FP16** + `variant="fp16"` when available; SDXL-style Turbo distills use **very few steps** at `1024×1024` (SD 1.5 at `512×512`).
- **FLUX.1 / SD3 / SD3.5** (curated in `model_options()`): loaded with **bfloat16 on CUDA** when available; no `fp16` variant folder — see `_load_auto_t2i_pipeline` in [`src/render/artist.py`](../../src/render/artist.py). FLUX negative prompts use **`true_cfg_scale`** via **`_apply_flux_negative_cfg`** when `guidance_scale` is 0 (Schnell). Style-continuity **img2img** chains apply only to checkpoints that expose a compatible **image-to-image** pipeline on the Hub (many FLUX/SD3 repos are **text-to-image only**; the app falls back to plain txt2img).
- **Safety**: unless **`AppSettings.allow_nsfw`** is enabled, pipelines that load a **safety checker** (e.g. Stable Diffusion 1.5) keep it active; with **`allow_nsfw`**, the checker is cleared after load so frames are not blanked for classifier hits. **SD3.5 Large Turbo (ADD)** and most FLUX builds typically omit the classic SD safety classifier.

## Quality retries
When the pipeline **regenerates** a single slide (quality retry), output is written to a **temporary directory** first, then copied to `img_NNN.png`, so intermediate `img_001.png` files are never deleted while reworking a later slide.

## Fallback mode
If local diffusion can’t load/run, the module generates simple placeholder images containing the prompt text so the editor can still produce a video.

## Outputs
Written into:
- `videos/<title>/assets/images/img_001.png` …

