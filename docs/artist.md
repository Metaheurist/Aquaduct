# `src/artist.py` — Artist (Images)

## Purpose
Generate 5–10 visuals per video based on script beat prompts.

## Primary mode
- Model: `stabilityai/sdxl-turbo`
- Library: `diffusers`
- Settings: **FP16**, **1 inference step**, `1024×1024`

## Fallback mode
If SDXL Turbo can’t load/run, the module generates simple placeholder images containing the prompt text so the editor can still produce a video.

## Outputs
Written into:
- `videos/<title>/assets/images/img_001.png` …

