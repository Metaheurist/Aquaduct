# `src/core/config.py` — Configuration

## Purpose
Central place for:
- model IDs
- output/cache directories
- basic video settings (resolution, FPS, scene / segment durations)
- UI/pipeline settings overrides (via `AppSettings`)

## Environment variables (host CPU)
Optional tuning for OpenMP/BLAS and PyTorch **CPU** thread pools (logical cores for host-side math — not GPU multithreading; see [`performance.md`](../pipeline/performance.md)):
- **`AQUADUCT_CPU_THREADS`** — target thread count (default `min(32, os.cpu_count())`). Does not override **`OMP_NUM_THREADS`** / **`MKL_NUM_THREADS`** / etc. if you already set them in the environment.
- **`AQUADUCT_TORCH_INTEROP_THREADS`** — optional `torch.set_num_interop_threads` (1–32). If unset, the app picks a higher value on CPU-only machines and a modest value when CUDA/MPS is available.

## Multi-GPU (CUDA policy override)
When set, **`AQUADUCT_CUDA_DEVICE`** forces **all** local CUDA stages (LLM, diffusion, etc.) onto that **ordinal** (`0`, `1`, …) or **`cuda:N`**. It overrides the **My PC** GPU policy saved in `ui_settings.json`. Used by [`src/util/cuda_device_policy.py`](../../src/util/cuda_device_policy.py). The **My PC** / **Model** tab fit tables still use the same resolver so labels stay consistent with runtime when this env var is unset; when set, fit heuristics follow the pinned index.

With **two or more** GPUs and **Auto** (no env override), the app assigns **script (LLM)** and **diffusion (image/video)** to **different** device indices so two heavy models are not routed to the same GPU by policy.

## Diffusion CPU offload (local image / video)
Local diffusers pipelines use [`src/util/diffusion_placement.py`](../../src/util/diffusion_placement.py). Environment:

| Variable | Meaning |
|----------|---------|
| **`AQUADUCT_DIFFUSION_CPU_OFFLOAD`** | **`auto`** (default): heuristics from detected VRAM + free host RAM. With **multiple CUDA devices**, **`auto` prefers sequential offload** (lowest peak VRAM on the diffusion GPU). **`model`**: move whole components at a time. **`sequential`**: one submodule at a time (slowest, lowest peak). **`off`** / **`none`** / **`0`**: keep the full pipeline on GPU when possible (needs enough VRAM). |
| **`AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD`** | Legacy: if **`1`** / **`true`**, same as **`sequential`** when the main variable is unset or **`auto`**. |

PyTorch may suggest **`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`** when the allocator reports large reserved-but-unallocated blocks; see [PyTorch CUDA memory notes](https://docs.pytorch.org/docs/stable/notes/cuda.html#optimizing-memory-usage-with-pytorch-cuda-alloc-conf).

## Local LLM inference (VRAM)
When **`model_execution_mode`** is **`local`**, long article text plus instructions can tokenize to a very long prompt. Attention prefill scales with sequence length and can trigger **`CUDA out of memory`** on tight GPUs (for example ~8GB) even with 4-bit weights.

- **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** — hard cap on **input** (prompt) tokens for the local transformers `generate()` path in [`src/content/brain.py`](../../src/content/brain.py). If unset, the base cap is **4096**, or **`min(4096, tokenizer.model_max_length)`** when the tokenizer exposes a finite `model_max_length`; values are clamped to **256–100000**. When this env var is **not** set and **CUDA** is available, an additional cap is applied from **total GPU VRAM** (for example **1536** tokens when total VRAM is under ~10 GiB) to reduce attention **prefill** OOM on tight GPUs. When the pipeline passes **`inference_settings`** (desktop / `run_once`), the cap is **also** reduced by the **script inference profile** from [`src/models/inference_profiles.py`](../../src/models/inference_profiles.py) (same **effective** VRAM per script role as the fit badges). Override explicitly with **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** if you need longer prompts and have headroom.

## VRAM inference profiles (local image / video / script)
For **local** runs, **image** and **video** diffusion call paths merge **per-repo profiles** (resolution, steps, frame counts, etc.) from [`src/models/inference_profiles.py`](../../src/models/inference_profiles.py) using **`effective_vram_gb_for_kind`** in [`src/util/cuda_device_policy.py`](../../src/util/cuda_device_policy.py) — consistent with **Auto** / **Single** GPU policy on the **My PC** tab. See [inference profiles](inference_profiles.md) for bands, console logging (`[Aquaduct][inference_profile]`), and **Auto-fit** log append.

## Per-model quantization (local)
`AppSettings` exposes per-row **quantization** modes that the **Settings → Model** tab dropdowns persist:

- **`script_quant_mode`** (LLM): `auto | bf16 | fp16 | int8 | nf4_4bit`
- **`image_quant_mode`** / **`video_quant_mode`** (diffusion): `auto | bf16 | fp16 | int8 | cpu_offload`
- **`voice_quant_mode`** (TTS): `auto | bf16 | fp16 | int8 | nf4_4bit | cpu_offload` (MOSS); Kokoro accepts `auto` only

Defaults are **`auto`**, which resolves to the highest-quality mode that fits the **effective per-role VRAM** ([`effective_vram_gb_for_kind`](../../src/util/cuda_device_policy.py)). The legacy boolean **`try_llm_4bit`** continues to migrate into `script_quant_mode="nf4_4bit"` when no explicit value is stored. See [quantization](quantization.md) for the policy module, VRAM multipliers, runtime fallbacks, and tests.

## Paths
`get_paths()` defines:
- `data/news_cache/` — per-format dedupe files `seen_<mode>.json` and `seen_titles_<mode>.json` (plus optional legacy `seen.json` / `seen_titles.json` for migration); local-only, not committed
- `runs/`
- `videos/` — under **`.Aquaduct_data/videos`** (finished video projects when **`media_mode`** is **`video`**)
- `pictures/` — under **`.Aquaduct_data/pictures`** (finished photo projects when **`media_mode`** is **`photo`**)
- `.cache/ffmpeg/`

[`media_output_root()`](../../src/core/config.py) returns **`paths.videos_dir`** or **`paths.pictures_dir`** based on the active **`media_mode`** (see below).

## Models
`get_models()` defines:
- LLM: `Qwen/Qwen3-14B` (curated default; see [models](models.md))
- Images: `black-forest-labs/FLUX.1-schnell` (default when **Image** is unset; field name `sdxl_turbo_id` is historical)
- Voice: `hexgrad/Kokoro-82M`

## Video format vs facts card
[`video_format_supports_facts_card()`](../../src/core/config.py) is **True** for **`news`**, **`explainer`**, and **`health_advice`**. The **Key facts** overlay uses the article fetch path; **Cartoon**, **Unhinged**, and **Creepypasta** runs do not show the card even if `facts_card_enabled` is on.

## Video settings
`VideoSettings` defaults:
- 1080×1920, 30fps
- micro-scene min/max seconds (slideshow segment length)
- images per video (slideshow **non–Pro** mode)
- **`pro_mode` / `pro_clip_seconds`**: when **`pro_mode`** is true and **slideshow is off** (normal UI), [`main.py`](../../main.py) runs **text-to-video** in **scene** segments (`pro_clip_seconds` each, with script-driven splits). When **`pro_mode`** is true and **slideshow is on** (legacy / hand-edited settings), the pipeline may still generate **round(pro_clip_seconds × fps)** diffusion frames (one per output frame), SDXL reference chain between frames, fixed-length timeline, and trim/pad narration to `pro_clip_seconds`. Optional env **`AQUADUCT_PRO_MAX_FRAMES`** caps that frame count.
- **`clips_per_video` / `clip_seconds`**: used for **motion mode** (slideshow off, Pro off): number and duration of **scene** segments from the Video model path (UI labels say “scenes”; keys stay historical).
- bitrate preset (low/med/high)
- export micro-scenes toggle (`export_microclips` in settings — key name unchanged)
- **`platform_preset_id`**: last selected **platform template** id from the Video tab tiles (empty string = **Custom**). See [`src/settings/video_platform_presets.py`](../../src/settings/video_platform_presets.py).

## App settings (UI + pipeline)
`AppSettings` includes:
- **GPU policy** (desktop; persisted in `ui_settings.json`; see [hardware.md](hardware.md); **My PC** tab maps **Auto** \| **Select GPU** to these keys — see [ui.md](../ui/ui.md)):
  - `gpu_selection_mode`: **`auto`** (default) or **`single`** — Auto routes LLM vs diffusion per [`cuda_device_policy`](../../src/util/cuda_device_policy.py); Single pins `gpu_device_index`.
  - `gpu_device_index`: CUDA ordinal used when `gpu_selection_mode == "single"` (shown in the **Device** combo only when **Select GPU** is chosen and CUDA GPUs exist).
  - `resource_graph_monitor_gpu_index`: optional int — last **Resource graph** “Monitor GPU” selection (`None` = default to device **0** when opening the graph).
- `media_mode`: **`video`** (default) or **`photo`** — selects the desktop **Photo \| Video** title-bar toggle; drives output folder (**`videos/`** vs **`pictures/`** under **`.Aquaduct_data/`**), which tabs are visible (e.g. **Video** vs **Picture**), and Library refresh (see [ui.md](../ui/ui.md))
- `tutorial_completed`: when `False`, the desktop UI may show the first-run **Help** tutorial once; set `True` after the user dismisses it (see [ui.md](../ui/ui.md))
- `video_format`: `news` | `cartoon` | `explainer` | `unhinged` | `creepypasta` | `health_advice` (drives which tag list applies to a run; see [UI](../ui/ui.md), [Crawler](../integrations/crawler.md))
- `run_content_mode`: `preset` | `custom` — **preset** uses the news cache + topics for script sourcing; **custom** uses `custom_video_instructions` (no headline pick from cache for that run)
- `custom_video_instructions`: multiline user notes; used when `run_content_mode == "custom"` (max length `MAX_CUSTOM_VIDEO_INSTRUCTIONS` in [`src/core/config.py`](../../src/core/config.py))
- `topic_tags_by_mode`: per-format tag lists (bias crawling + scripting for the active format); use [`src/content/topics.py`](../../src/content/topics.py) `effective_topic_tags()` for the current format
- `background_music_path`
- model overrides (repo IDs):
  - `llm_model_id`
  - `image_model_id`
  - `voice_model_id`
- **Hugging Face** / **Firecrawl**: `hf_token`, `hf_api_enabled`, `firecrawl_enabled`, `firecrawl_api_key`
- **ElevenLabs** (optional): `elevenlabs_enabled`, `elevenlabs_api_key` (or `ELEVENLABS_API_KEY` env) — see [ElevenLabs](../integrations/elevenlabs.md)
- **Characters**: `active_character_id` selects a row from `data/characters.json` (Character Builder); empty means no character — see [Characters](../ui/characters.md)
- **TikTok** (optional): `tiktok_enabled`, client key/secret, redirect URI, OAuth port, tokens, `tiktok_publishing_mode`, `tiktok_auto_upload_after_render` — see [TikTok](../integrations/tiktok.md)
- **YouTube** (optional, independent of TikTok): `youtube_enabled`, OAuth client ID/secret, redirect URI, OAuth port (default loopback port **8888**), tokens, `youtube_privacy_status`, `youtube_add_shorts_hashtag`, `youtube_auto_upload_after_render` — see [YouTube](../integrations/youtube.md)
- **Image safety**: `allow_nsfw` — when `True`, diffusion image generation runs without the built-in **safety checker** (see [Artist](../pipeline/artist.md))
- **Model execution (API vs local)** ([`src/core/config.py`](../../src/core/config.py), persisted in [`src/settings/ui_settings.py`](../../src/settings/ui_settings.py)):
  - `model_execution_mode`: `"local"` (default) or `"api"` — see [api_generation.md](../integrations/api_generation.md) and the **Model** tab notes in [ui.md](../ui/ui.md).
  - `api_models`: nested per-role `ApiRoleConfig` — `llm`, `image`, `video`, `voice` each with `provider`, `model`, optional `base_url` / `org_id` (LLM), `voice_id` (voice). Recommended API-mode providers (first in the UI list) include **Google AI Studio (Gemini)** for script, **SiliconFlow** for images, **Kling AI** (plus Magic Hour and Replicate) for Pro text-to-video, and **Inworld** for TTS; see [API generation](../integrations/api_generation.md) for required env keys (`GEMINI_API_KEY`, `SILICONFLOW_API_KEY`, `KLING_ACCESS_KEY`, `KLING_SECRET_KEY`, `MAGIC_HOUR_API_KEY`, `INWORLD_API_KEY`, etc.).
  - `api_openai_key`, `api_replicate_token`: optional saved keys; environment overrides: **`OPENAI_API_KEY`**, **`GEMINI_API_KEY`**, **`GOOGLE_API_KEY`**, **`SILICONFLOW_API_KEY`**, **`KLING_ACCESS_KEY`**, **`KLING_SECRET_KEY`**, **`MAGIC_HOUR_API_KEY`**, **`INWORLD_API_KEY`**, **`REPLICATE_API_TOKEN`** / **`REPLICATE_API_KEY`**, and provider-specific LLM keys as documented in [api_generation.md](../integrations/api_generation.md).
  - See [API generation](../integrations/api_generation.md) and [Models](models.md) for behavior when `api` mode is on.
- **Model files location (local inference only)** ([`src/core/models_dir.py`](../../src/core/models_dir.py)):
  - `models_storage_mode`: `"default"` — use **`.Aquaduct_data/models`** (same as `get_paths().models_dir`).
  - `models_external_path`: when `models_storage_mode == "external"`, non-empty path to a folder for Hugging Face snapshots (invalid paths fall back to default). Used for downloads, loading weights, and CLI `models` commands when saved in `ui_settings.json`.

Task queue for finished renders (Tasks tab) is stored in `data/upload_tasks.json` (paths + per-row TikTok/YouTube upload metadata); keep it local / gitignored.

## Title-to-folder normalization
`safe_title_to_dirname()` converts a video title to a Windows-safe directory name.

