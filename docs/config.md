# `src/config.py` — Configuration

## Purpose
Central place for:
- model IDs
- output/cache directories
- basic video settings (resolution, FPS, clip durations)
- UI/pipeline settings overrides (via `AppSettings`)

## Paths
`get_paths()` defines:
- `data/news_cache/` — per-format dedupe files `seen_<mode>.json` and `seen_titles_<mode>.json` (plus optional legacy `seen.json` / `seen_titles.json` for migration); local-only, not committed
- `runs/`
- `videos/`
- `.cache/ffmpeg/`

## Models
`get_models()` defines:
- LLM: `meta-llama/Llama-3.2-3B-Instruct`
- Images: `stabilityai/sdxl-turbo`
- Voice: `hexgrad/Kokoro-82M`

## Video format vs facts card
[`video_format_supports_facts_card()`](../src/config.py) is **True** only for `news` and `explainer`. The **Key facts** overlay uses the article fetch path; **Cartoon** / **Unhinged** runs do not show the card even if `facts_card_enabled` is on.

## Video settings
`VideoSettings` defaults:
- 1080×1920, 30fps
- micro-clip min/max seconds
- images per video
- bitrate preset (low/med/high)
- export micro-clips toggle
- **`platform_preset_id`**: last selected **platform template** id from the Video tab tiles (empty string = **Custom**). See [`src/video_platform_presets.py`](../src/video_platform_presets.py).

## App settings (UI + pipeline)
`AppSettings` includes:
- `video_format`: `news` | `cartoon` | `explainer` (drives which tag list applies to a run)
- `run_content_mode`: `preset` | `custom` — **preset** uses the news cache + topics for script sourcing; **custom** uses `custom_video_instructions` (no headline pick from cache for that run)
- `custom_video_instructions`: multiline user notes; used when `run_content_mode == "custom"` (max length `MAX_CUSTOM_VIDEO_INSTRUCTIONS` in `src/config.py`)
- `topic_tags_by_mode`: per-format tag lists (bias crawling + scripting for the active format); use `src/topics.py` `effective_topic_tags()` for the current format
- `background_music_path`
- model overrides (repo IDs):
  - `llm_model_id`
  - `image_model_id`
  - `voice_model_id`
- **Hugging Face** / **Firecrawl**: `hf_token`, `hf_api_enabled`, `firecrawl_enabled`, `firecrawl_api_key`
- **ElevenLabs** (optional): `elevenlabs_enabled`, `elevenlabs_api_key` (or `ELEVENLABS_API_KEY` env) — see [ElevenLabs](elevenlabs.md)
- **Characters**: `active_character_id` selects a row from `data/characters.json` (Character Builder); empty means no character — see [Characters](characters.md)
- **TikTok** (optional): `tiktok_enabled`, client key/secret, redirect URI, OAuth port, tokens, `tiktok_publishing_mode`, `tiktok_auto_upload_after_render` — see [TikTok](tiktok.md)
- **YouTube** (optional, independent of TikTok): `youtube_enabled`, OAuth client ID/secret, redirect URI, OAuth port (default loopback port **8888**), tokens, `youtube_privacy_status`, `youtube_add_shorts_hashtag`, `youtube_auto_upload_after_render` — see [YouTube](youtube.md)
- **Image safety**: `allow_nsfw` — when `True`, diffusion image generation runs without the built-in **safety checker** (see [Artist](artist.md))

Task queue for finished renders (Tasks tab) is stored in `data/upload_tasks.json` (paths + per-row TikTok/YouTube upload metadata); keep it local / gitignored.

## Title-to-folder normalization
`safe_title_to_dirname()` converts a video title to a Windows-safe directory name.

