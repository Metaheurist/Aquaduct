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

## Host RAM preflight (optional)
When **`AQUADUCT_HOST_RAM_PREFLIGHT`** is **`1`** / **`true`** / **`yes`** / **`on`**, [`preflight_check`](../../src/runtime/preflight.py) adds a **warning** (never a hard error) if **free host RAM** is under **~4 GiB** and **local** model execution is selected. Useful on laptops before large diffusers checkpoint loads.

Additional optional hints ([`preflight_host_hints.py`](../../src/runtime/preflight_host_hints.py)):

| Variable | Meaning |
|----------|---------|
| **`AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM`** | When **`1`** / **`true`** / **`yes`** / **`on`** and execution is **local**, emit a warning if **free host RAM** is below **`AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM_FREE_GIB`** (default **8**) **and** a selected repo looks large: **`hf_model_sizes.json`** Hub byte totals ≥ **`AQUADUCT_PREFLIGHT_HEAVY_REPO_HUB_GIB`** (default **6** GiB), or known frontier ids (e.g. Wan / HunyuanVideo / large FLUX / DeepSeek‑V3‑class script models). |
| **`AQUADUCT_CPU_PREFLIGHT`** | When **`1`** / **`true`** / **`yes`** / **`on`**, adds a soft warning if combined CPU utilization is ≥ **`AQUADUCT_CPU_PREFLIGHT_PCT`** (default **90**) before starting a run (`psutil`). |

Diffusers loading ([`diffusers_load.py`](../../src/util/diffusers_load.py)):

| Variable | Meaning |
|----------|---------|
| **`AQUADUCT_DIFFUSERS_DISABLE_MMAP`** | When **`1`** / **`true`** / **`yes`** / **`on`**, passes **`disable_mmap=True`** into diffusers **`from_pretrained`** on image/video pipeline loads ([`clips.py`](../../src/render/clips.py), [`artist.py`](../../src/render/artist.py)). Older diffusers builds that reject the kwarg fall back automatically. |

## Process-wide defaults (`main.py`)

Before most CUDA-heavy work begins, **`main`** applies **`setdefault`** so you can override in the outer environment:

| Variable | Default Aquaduct sets |
|----------|-------------------------|
| **`PYTORCH_CUDA_ALLOC_CONF`** | `expandable_segments:True,max_split_size_mb:128` — reduces fragmentation from large diffusers/transformers allocations ([PyTorch CUDA memory](https://docs.pytorch.org/docs/stable/notes/cuda.html#optimizing-memory-usage-with-pytorch-cuda-alloc-conf)). |
| **`HF_HUB_ENABLE_HF_TRANSFER`** | **`0`** — disables optional **`hf_transfer`** unless you opt in externally. |

## Stage memory budget (host RAM heuristic)

[`analyze_stage_memory_budget`](../../src/runtime/memory_budget_preflight.py) drives **warnings** (`check_stage_memory_budget`). When free RAM is **dramatically** below the heuristic vs **large** checkpoints (defaults: **video** footprints ≥ ~30 GiB Hub snapshot estimate), startup **preflight** surfaces a matching **fatal error** instead of letting Windows OOM‑kill Python mid‑`from_pretrained`.

| Variable | Meaning |
|----------|---------|
| **`AQUADUCT_MEMORY_PREFLIGHT`** | **`0`** / **`false`** / **`no`** / **`off`** disables warnings **and** fatal host‑RAM gates (**default**: enabled unless set off). |
| **`AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR`** | Float multiplier on cached Hub GiB (**default **2.0**) — unzip / transient spike headroom. |
| **`AQUADUCT_HOST_RAM_FLOOR_GIB`** | Absolute floor (GiB) free RAM (**default **5.0**) combined with the scaled model estimate (`max(floor, snapshot×factor)`). |
| **`AQUADUCT_MEMORY_PREFLIGHT_FAIL`** | **`1`** / **`true`** / **`on`** — every host‑RAM shortfall line becomes a **hard** preflight error (strict operator mode). |
| **`AQUADUCT_MEMORY_PREFLIGHT_FAIL_ROLES`** | Comma roles for **catastrophic** auto‑block (default **`video`**). Set to **empty** (`AQUADUCT_MEMORY_PREFLIGHT_FAIL_ROLES=`) to disable fatal shortfall gating while keeping warnings (**not** recommended for frontier T2V on low‑RAM PCs). |
| **`AQUADUCT_MEMORY_SEVERE_SHORTFALL_FRAC`** | If free RAM **&lt;** this fraction × heuristic threshold, treat as catastrophic for gated roles (default **0.35**). |
| **`AQUADUCT_MEMORY_BLOCK_MIN_VIDEO_GIB`** / **`…_IMAGE_GIB`** / **`…_SCRIPT_GIB`** | Minimum Hub snapshot estimate (GiB) before catastrophic rules apply per role (defaults **30** / **20** / **20**). |

See [Crash resilience — host RAM heuristic](../pipeline/crash-resilience.md).

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

- **`AQUADUCT_VRAM_PREEMPT_USED_FRAC`** — optional threshold **0.50–0.9999** (default **0.99**). Used by [`retry_stage`](../../src/runtime/oom_retry.py): when **GPU VRAM used / total** on the stage’s CUDA ordinal is at or above this value after [`cleanup_vram`](../../src/util/utils_vram.py), the pipeline tries a **larger or equal‑VRAM** GPU from the detected list, then lowers quantization — **before** the heavy stage runs — to reduce load-time OOMs. See [Inference profiles — troubleshooting](inference_profiles.md#troubleshooting-run-stops-during-loading-weights).

## VRAM watchdog (CUDA free memory before loads)
[`check_cuda_headroom`](../../src/util/vram_watchdog.py) runs before heavy CUDA loads (e.g. local LLM weights, **`prepare_for_next_model`** / diffusion staging via [`memory_budget.release_between_stages`](../../src/util/memory_budget.py)). It uses **`torch.cuda.mem_get_info`**. Set **`AQUADUCT_VRAM_WATCHDOG=0`** / **`false`** / **`off`** to disable both warn and abort paths.

| Variable | Meaning |
|----------|---------|
| **`AQUADUCT_VRAM_WARN_FREE_MIB`** | Absolute minimum **free** VRAM for a **warning** (default **768** MiB). Combined with the fractional rule below (`max` of both). |
| **`AQUADUCT_VRAM_WARN_FREE_FRAC`** | Warn when free VRAM **&lt;** this fraction of **total** (default **0.07**, clamped ~0.001–0.95). |
| **`AQUADUCT_VRAM_ABORT_FREE_MIB`** | Absolute minimum free VRAM before **`RuntimeError`** (default **96** MiB). |
| **`AQUADUCT_VRAM_ABORT_FREE_FRAC`** | Abort when free **&lt;** this fraction of total (default **0.025**). |

Moderate pressure logs to the pipeline console and may surface a **non-blocking** desktop notice when the pipeline worker provides a callback ([`pipeline_notice`](../../src/runtime/pipeline_notice.py)). Critical pressure raises **`RuntimeError`** with remediation hints.

## Model load heartbeat (stderr + Resource graph footer)
Long synchronous **`from_pretrained`** calls use [`diffusion_load_watch`](../../src/runtime/load_heartbeat.py). Console lines periodically report load progress; the latest line mirrors to the desktop **Resource usage** footer.

| Variable | Role |
|----------|------|
| **`AQUADUCT_LOAD_HEARTBEAT_INTERVAL_S`** | Seconds between beats (default **30**, minimum clamp **10**). |
| **`AQUADUCT_LOAD_FATAL_TIMEOUT_S`** or **`AQUADUCT_LOAD_TIMEOUT_S`** | If **> 0**, emits a stalled-load watchdog after elapsed seconds (**does not** safely cancel HF loads). |

[Performance.md](../pipeline/performance.md), [crash-resilience.md](../pipeline/crash-resilience.md).

## Local LLM inference (VRAM)
When **`model_execution_mode`** is **`local`**, long article text plus instructions can tokenize to a very long prompt. Attention prefill scales with sequence length and can trigger **`CUDA out of memory`** on tight GPUs (for example ~8GB) even with 4-bit weights.

- **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** — hard cap on **input** (prompt) tokens for the local transformers `generate()` path in [`src/content/brain.py`](../../src/content/brain.py). If unset, the base cap is **4096**, or **`min(4096, tokenizer.model_max_length)`** when the tokenizer exposes a finite `model_max_length`; values are clamped to **256–100000**. When this env var is **not** set and **CUDA** is available, an additional cap is applied from **total GPU VRAM** (for example **1536** tokens when total VRAM is under ~10 GiB) to reduce attention **prefill** OOM on tight GPUs. When the pipeline passes **`inference_settings`** (desktop / `run_once`), the cap is **also** reduced by the **script inference profile** from [`src/models/inference_profiles.py`](../../src/models/inference_profiles.py) (same **effective** VRAM per script role as the fit badges). Override explicitly with **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** if you need longer prompts and have headroom.

## VRAM inference profiles (local image / video / script)
For **local** runs, **image** and **video** diffusion call paths merge **per-repo profiles** (resolution, steps, frame counts, etc.) from [`src/models/inference_profiles.py`](../../src/models/inference_profiles.py) using **`effective_vram_gb_for_kind`** in [`src/util/cuda_device_policy.py`](../../src/util/cuda_device_policy.py) — consistent with **Auto** / **Single** GPU policy on the **My PC** tab. See [inference profiles](inference_profiles.md) for bands, console logging (`[Aquaduct][inference_profile]`), and **Auto-fit** log append.

## Per-model quantization (local)
`AppSettings` exposes per-row **quantization** modes that the **Settings → Model** tab dropdowns persist:

- **`auto_quant_downgrade_on_failure`** (default **True** — Model tab checkbox): feed [`retry_stage`](../../src/runtime/oom_retry.py) so load/OOM failures can step **down** manual quant ladders before giving up ([Quantization](quantization.md), [Crash resilience](../pipeline/crash-resilience.md)).
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
- **`spatial_upscale_mode`**: **`off`** (default) or **`auto`** — optional Real-ESRGAN-class **spatial** upsampling toward the export width×height before caption compositing ([`spatial_upscale.py`](../../src/render/spatial_upscale.py)). **`auto`** tries PyTorch on CUDA when **`basicsr`**, **`realesrgan`**, and **`opencv`** are installed, then the **`realesrgan-ncnn-vulkan`** binary; otherwise the editor keeps Lanczos resize. Ignored in **API** mode. Optional pip set: [`requirements-optional-upscale.txt`](../../requirements-optional-upscale.txt).

### Spatial upscale environment (optional)

| Variable | Role |
|----------|------|
| **`AQUADUCT_REALESRGAN_NCNN`** | Full path to **`realesrgan-ncnn-vulkan`** (or `.exe`) when not on `PATH`. |
| **`AQUADUCT_DISABLE_REALESRGAN_NCNN`** | **`1`** / **`true`** — skip the Vulkan path. |
| **`AQUADUCT_REALESRGAN_NCNN_MODEL`** | NCNN model name (default **`realesrgan-x4plus`**). |
| **`AQUADUCT_REALESRGAN_NCNN_SCALE`** | Integer scale **`2`–`4`** for NCNN (default **4**). |
| **`AQUADUCT_REALESRGAN_TILE`** | PyReal-ESRGAN tile size for CUDA (default **256**). |
| **`AQUADUCT_SPATIAL_UPSCALE_CLIP_TIMEOUT_S`** | Per-clip wall-time ceiling (seconds); abort SR for that clip only. |
| **`AQUADUCT_SPATIAL_UPSCALE_JOB_MAX_S`** | Max total wall time for a multi-clip upscale batch. |

Weights for the PyTorch **x4+** path download once into **`.Aquaduct_data/realesrgan/RealESRGAN_x4plus.pth`** (or app data dir from [`get_paths()`](../../src/core/config.py)).

## App settings (UI + pipeline)
`AppSettings` includes:
- **GPU policy** (desktop; persisted in `ui_settings.json`; see [hardware.md](hardware.md); **My PC** tab maps **Auto** \| **Select GPU** to these keys — see [ui.md](../ui/ui.md)):
  - `gpu_selection_mode`: **`auto`** (default) or **`single`** — Auto routes LLM vs diffusion per [`cuda_device_policy`](../../src/util/cuda_device_policy.py); Single pins `gpu_device_index`.
  - `gpu_device_index`: CUDA ordinal used when `gpu_selection_mode == "single"` (shown in the **Device** combo only when **Select GPU** is chosen and CUDA GPUs exist).
  - `multi_gpu_shard_mode`: **`off`** (default) or **`vram_first_auto`** — optional experimental **VRAM-first** intra-model splitting (Accelerate-balanced LLM loads + diffusers peer submodule moves) when **Auto** GPU policy applies, **`torch.cuda.device_count() >= 2`**, and **`AQUADUCT_CUDA_DEVICE`** is unset; see [hardware.md](hardware.md) and [performance.md](../pipeline/performance.md).
  - `resource_graph_monitor_gpu_index`: optional int — last **Resource graph** “Monitor GPU” selection (`None` = default to device **0** when opening the graph).
  - `resource_graph_split_view`: when **`true`**, the Resource graph **Monitor** dropdown was last left on **Split view — all GPUs** (one VRAM sparkline per CUDA device); persisted in `ui_settings.json`.
  - `resource_graph_compact`: when **`true`** (default; omitted key in older `ui_settings.json` also defaults to **mini**), the Resource usage window opens in **compact** layout (smaller sparklines, no chart footers, shorter split-view scroll). Set **`false`** after expanding via the title-bar toggle so the larger “expanded” layout persists.
- `media_mode`: **`video`** (default) or **`photo`** — selects the desktop **Photo \| Video** title-bar toggle; drives output folder (**`videos/`** vs **`pictures/`** under **`.Aquaduct_data/`**), which tabs are visible (e.g. **Video** vs **Picture**), and Library refresh (see [ui.md](../ui/ui.md))
- `tutorial_completed`: when `False`, the desktop UI may show the first-run **Help** tutorial once; set `True` after the user dismisses it (see [ui.md](../ui/ui.md))
- **`resume_partial_pipeline`**: **`false`** default — Video tab (**Resume partial pipeline**). When **`true`**, **`run_checkpoint.json`** milestones and **`pipeline_script_package.json`** are written under **`videos/<project>/assets/`** so a later desktop run can skip completed stages when fingerprint matches; see [`run_checkpoint`](../../src/runtime/run_checkpoint.py), [crash-resilience.md](../pipeline/crash-resilience.md).
- **`resume_partial_project_directory`**: ephemeral in-memory/ephemeral-save only — pinned output folder during a resumed session; stripped from **`ui_settings.json`** on Save ([`strip_ephemeral_save_keys`](../../src/settings/ui_settings.py)).
- `video_format`: `news` | `cartoon` | `explainer` | `unhinged` | `creepypasta` | `health_advice` (drives which tag list applies to a run; see [UI](../ui/ui.md), [Crawler](../integrations/crawler.md))
- `run_content_mode`: `preset` | `custom` — **preset** uses the news cache + topics for script sourcing; **custom** uses `custom_video_instructions` (no headline pick from cache for that run)
- `custom_video_instructions`: multiline user notes; used when `run_content_mode == "custom"` (max length `MAX_CUSTOM_VIDEO_INSTRUCTIONS` in [`src/core/config.py`](../../src/core/config.py))
- `topic_tags_by_mode`: per-format tag lists (crawling + scripting for the active format); use [`src/content/topics.py`](../../src/content/topics.py) `effective_topic_tags()` for the current format
- `topic_tag_notes`: optional `dict[str, str]` — per-tag **grounding** lines (Topics tab; keys normalized lowercase; values trimmed to **≤ 240** chars via [`sanitize_topic_tag_notes`](../../src/content/topic_constraints.py)). Merged into [`topic_constraints_block`](../../src/content/topic_constraints.py) at run time; see [Topics UI](../ui/topics.md)
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

