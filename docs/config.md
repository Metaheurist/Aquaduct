# `src/config.py` — Configuration

## Purpose
Central place for:
- model IDs
- output/cache directories
- basic video settings (resolution, FPS, clip durations)
- UI/pipeline settings overrides (via `AppSettings`)

## Paths
`get_paths()` defines:
- `data/news_cache/` (`seen.json` and `seen_titles.json` are local-only; not committed)
- `runs/`
- `videos/`
- `.cache/ffmpeg/`

## Models
`get_models()` defines:
- LLM: `meta-llama/Llama-3.2-3B-Instruct`
- Images: `stabilityai/sdxl-turbo`
- Voice: `hexgrad/Kokoro-82M`

## Video settings
`VideoSettings` defaults:
- 1080×1920, 30fps
- micro-clip min/max seconds
- images per video
- bitrate preset (low/med/high)
- export micro-clips toggle

## App settings (UI + pipeline)
`AppSettings` includes:
- `topic_tags`: used to bias crawling + scripting
- `background_music_path`
- model overrides (repo IDs):
  - `llm_model_id`
  - `image_model_id`
  - `voice_model_id`

## Title-to-folder normalization
`safe_title_to_dirname()` converts a video title to a Windows-safe directory name.

