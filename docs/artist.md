# `src/render/artist.py` — Artist (Images)

## Purpose
Generate 5–10 visuals per video based on script beat prompts.

## Primary mode
- Model: `stabilityai/sdxl-turbo` (or another repo chosen on the **Model** tab)
- Library: `diffusers`
- Settings: **FP16**, **1 inference step**, `1024×1024`
- **Safety**: unless **`AppSettings.allow_nsfw`** is enabled, pipelines that load a **safety checker** (e.g. Stable Diffusion 1.5) keep it active; with **`allow_nsfw`**, the checker is cleared after load so frames are not blanked for classifier hits. SDXL Turbo typically has no NSFW classifier in the same form.

## Quality retries
When the pipeline **regenerates** a single slide (quality retry), output is written to a **temporary directory** first, then copied to `img_NNN.png`, so intermediate `img_001.png` files are never deleted while reworking a later slide.

## Fallback mode
If SDXL Turbo can’t load/run, the module generates simple placeholder images containing the prompt text so the editor can still produce a video.

## Outputs
Written into:
- `videos/<title>/assets/images/img_001.png` …

