# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Video quality & tab redesign (in progress)

This is an in-flight track; bullets land per phase as they ship.

- **Phase 2 — optional temporal smoothing**: new
  [`src/render/temporal_smooth.py`](src/render/temporal_smooth.py)
  adds a post-generation motion-aware upsampling pass with three modes —
  `off` (default no-op), `ffmpeg` (bundled binary, `minterpolate=mci:aobmc`),
  and `rife` (lazy import of `rife_ncnn_vulkan_python`, gated on
  `RIFE_VRAM_BUDGET_MB ≥ 1500` and falling back to `ffmpeg` otherwise).
  `target_fps` is clamped to `[12, 60]`; smoothing is a no-op when the
  target is ≤ the clip's encoded fps. The pass replaces the original
  mp4 atomically and rewrites the `.mp4.meta.json` sidecar so the editor
  and audio aligner pick up the new fps and frame count without any
  further changes. `src/render/clips.py::generate_clips` now calls
  `_maybe_smooth_clips(...)` after the T2V/I2V batch and
  `src/runtime/preflight.py` adds RIFE-resource warnings (package
  missing, low VRAM, API-mode noise). New
  `VideoSettings.smoothness_mode: Literal["off", "ffmpeg", "rife"]` and
  `smoothness_target_fps: int = 24`. Tests:
  [`tests/render/test_temporal_smooth.py`](tests/render/test_temporal_smooth.py)
  (16 cases). Docs updated:
  [`docs/pipeline/video-quality.md`](docs/pipeline/video-quality.md).

- **Phase 8 — auto-cast parity & persistence**: the LLM cast generator
  ([`generate_cast_from_storyline_llm`](src/content/brain.py)) now also
  emits a per-character `voice_instruction`, and
  [`fallback_cast_for_show`](src/content/characters_store.py) mirrors the
  same field for every supported `video_format` (incl. a dedicated
  `creepypasta` narrator branch). Two new helpers,
  `cast_to_characters` and `merge_cast_into_store`, build full
  `Character` instances with deterministic IDs derived from
  `(name, video_format, headline_seed)` and upsert them into
  `data/characters.json`, so auto-generated casts now show up in the
  Characters tab and are deduplicated across re-runs.
  `cast_to_ephemeral_character` aggregates `voice_instruction` for
  multi-character formats (cartoon/unhinged) and propagates the single
  narrator instruction for news/explainer/creepypasta/health_advice.
  New `AppSettings.auto_save_generated_cast: bool = True` controls the
  promotion; a checkbox **"Save generated cast to Characters tab"** is
  added under the Character dropdown in the Run tab. Both `main.run_once`
  and `src.runtime.pipeline_api.run_once_api` call
  `merge_cast_into_store` after writing
  `assets/generated_cast.json`. Tests:
  [`tests/content/test_cast_persistence.py`](tests/content/test_cast_persistence.py)
  (18 cases). Docs:
  [`docs/pipeline/character-persistence.md`](docs/pipeline/character-persistence.md).

- **Phase 9 — fused prompt context**: new
  [`src/content/prompt_context.py`](src/content/prompt_context.py)
  resolves `video_format`, `personality`, `art_style`, and `branding`
  once per run and emits ready-to-paste blocks for the script LLM
  (`as_script_prompt_block()`), T2I affix (`as_t2i_affix()`), and T2V
  affix (`as_t2v_affix()`). `compose_prompt_context(app=...)` picks the
  current settings and `merge_with_supplement(...)` is idempotent so the
  block can safely fuse into the existing `script_digest`. Includes
  `format_voice_lock` (per-format default narrator voice),
  `reconcile_format_personality` (swaps `creepypasta+hype` →
  `creepypasta+neutral`, `unhinged+cozy` → `unhinged+comedic`, etc.) with
  conflict warnings that bubble up via `emit_pipeline_notice`. `main.py`
  calls it after `script_digest` is built so the script LLM sees the
  fused style brief alongside the web digest. Tests:
  [`tests/content/test_prompt_context.py`](tests/content/test_prompt_context.py)
  (14 cases). Docs:
  [`docs/pipeline/prompt-context.md`](docs/pipeline/prompt-context.md).

- **Phase 10 — chunked LLM article relevance pass**: new
  [`src/content/article_chunker.py`](src/content/article_chunker.py) and
  [`src/content/article_relevance.py`](src/content/article_relevance.py).
  After `crawler.fetch_article_text` returns and `article_clean` strips the
  obvious chrome, the pipeline hands each chunk to the shared script LLM
  (`llm_sess` from [`src/content/llm_session.py`](src/content/llm_session.py))
  with a single `{"keep": true|false}` reply per chunk; kept chunks are
  recomposed into a tight excerpt that the script prompt then sees instead
  of the full page body. Resource discipline: hard caps on chunk count
  (`AQUADUCT_ARTICLE_RELEVANCE_MAX_CHUNKS`, default 8) and chunk size
  (`AQUADUCT_ARTICLE_RELEVANCE_CHUNK_CHARS`, default 1800), per-chunk
  `max_new_tokens=96`, fallback to keep-all if every chunk is rejected, and
  a persistent per-URL cache keyed by URL + content hash. Setting:
  `AppSettings.video.article_relevance_screen` (default `True`); env
  override `AQUADUCT_ARTICLE_RELEVANCE_SCREEN=0` disables. The pipeline now
  also writes `assets/article.relevance.json` (kept indices / total chunks
  / cache hit / used LLM) for auditing. Tests:
  [`tests/content/test_article_chunker.py`](tests/content/test_article_chunker.py),
  [`tests/content/test_article_relevance.py`](tests/content/test_article_relevance.py).
  Docs: [`docs/pipeline/article-relevance.md`](docs/pipeline/article-relevance.md).

- **Phase 3 — script repair + article sanitizer**:
  [`brain._to_package`](src/content/brain.py) now synthesizes a
  `visual_prompt` from the narration (and on-screen text / title) when the
  LLM returns only one of the two fields, instead of silently dropping the
  segment — fixes the
  [`Two_Sentenced_Horror_Stories`](.Aquaduct_data/videos/Two_Sentenced_Horror_Stories/assets/pipeline_script_package.json)
  collapse where multiple beats reduced to a single placeholder. The
  synthesis is format-aware (`creepypasta`, `cartoon`, `unhinged`,
  `health_advice`, `news`, `explainer` all get tailored framing affixes).
  `video_package_from_llm_output(text, *, video_format)` and `_to_package`
  thread the active format; both transformers and OpenAI generation paths
  pass it. The `creepypasta` prompt is tightened to demand both fields per
  beat. New deterministic article sanitizer
  [`src/content/article_clean.py`](src/content/article_clean.py) strips
  Fandom/wiki rails (Fan Feed, Trending pages, Categories), citation markers,
  promo / cookie chrome, collapses numbered link lists, and caps to
  `max_chars`; `crawler.fetch_article_text(..., sanitize=True)` (default)
  runs it before returning. Tests:
  [`tests/content/test_brain_to_package_synthesis.py`](tests/content/test_brain_to_package_synthesis.py),
  [`tests/content/test_article_clean.py`](tests/content/test_article_clean.py).
  Docs: [`docs/pipeline/brain.md`](docs/pipeline/brain.md),
  [`docs/integrations/crawler.md`](docs/integrations/crawler.md).

- **Phase 1 — native FPS + per-clip duration alignment**: every T2V / I2V
  clip is encoded at the model's trained playback fps (CogVideoX **8**,
  Wan **16**, Mochi **30**, LTX **24**, Hunyuan **24**) instead of the user's
  export fps; LTX-2 keeps its `frame_rate` kwarg. Each clip mp4 now ships
  with a `<clip>.mp4.meta.json` sidecar (`model_id`, `encoded_fps`,
  `num_frames`, `duration_s`, `native_fps`, `user_fps`, `role`, `prompt`).
  [`src/render/editor.py`](src/render/editor.py)'s
  `assemble_generated_clips_then_concat` accepts a new
  **`clip_durations=`** kwarg and, when omitted, derives per-clip lengths
  from the sidecar (then `VideoFileClip.duration`, then legacy equal-T
  chunking). [`main.py`](main.py)'s Pro branch now sums the real per-clip
  durations into `total_T` before voice alignment so audio, captions, and
  video share one timeline. Per-clip caption overlays no longer leak `t0`
  via a closure (factory binds each `t_start` explicitly).
  Files: [`src/models/native_fps.py`](src/models/native_fps.py) (new),
  [`src/render/clips.py`](src/render/clips.py),
  [`src/render/editor.py`](src/render/editor.py), [`main.py`](main.py).
  Docs: **[`docs/pipeline/video-quality.md`](docs/pipeline/video-quality.md)**
  (new). Tests:
  [`tests/render/test_native_fps_encode.py`](tests/render/test_native_fps_encode.py),
  [`tests/render/test_audio_alignment_real_durations.py`](tests/render/test_audio_alignment_real_durations.py).
  Override: `AQUADUCT_NATIVE_FPS_OVERRIDE_<REPO>` (e.g.
  `AQUADUCT_NATIVE_FPS_OVERRIDE_THUDM__COGVIDEOX_5B=12`).

### Crash-resilience & “run-on-anything” mode
- **CUDA / Hub env** ([`main.py`](main.py)): `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:128`; `HF_HUB_ENABLE_HF_TRANSFER=0`.
- **Quant default** ([`src/core/config.py`](src/core/config.py), [`src/models/quantization.py`](src/models/quantization.py)): **`auto_quant_downgrade_on_failure`** default **on**.
- **Resume checkpoints** ([`src/runtime/run_checkpoint.py`](src/runtime/run_checkpoint.py), [`main.py`](main.py), [`UI/main_window.py`](UI/main_window.py)): `run_checkpoint.json` milestones + `pipeline_script_package.json`; optional resume of latest incomplete project under **`videos/`**; ephemeral **`resume_partial_project_directory`** (stripped from disk saves).
- **Voice** ([`main.py`](main.py), [`src/speech/voice.py`](src/speech/voice.py), [`src/runtime/variant_fallback.py`](src/runtime/variant_fallback.py)): local voice path uses **`retry_stage`**; pyttsx3-only sentinel repo `aquaduct/system-tts-pyttsx3`; MOSS → Kokoro → pyttsx3 style mapping in variant table.
- **Load heartbeat UI** ([`src/runtime/load_heartbeat.py`](src/runtime/load_heartbeat.py), [`UI/dialogs/resource_graph_dialog.py`](UI/dialogs/resource_graph_dialog.py)): Resource graph footer shows recent model-load heartbeat; **`AQUADUCT_LOAD_TIMEOUT_S`** mirrors **`AQUADUCT_LOAD_FATAL_TIMEOUT_S`** for the stalled-load watchdog.
- **Preflight HF** ([`src/runtime/preflight.py`](src/runtime/preflight.py)): token guidance for gated/frontier Hub ids when no token is configured.
- **Settings** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py)): **Use lighter Motion / Video checkpoint** when the video fit badge is red/amber (curated downgrade list).
- **Tests**: [`tests/runtime/test_resource_and_deps.py`](tests/runtime/test_resource_and_deps.py), [`tests/runtime/test_load_heartbeat.py`](tests/runtime/test_load_heartbeat.py), [`tests/content/test_llm_session.py`](tests/content/test_llm_session.py), [`tests/content/test_factcheck_pkg_roundtrip.py`](tests/content/test_factcheck_pkg_roundtrip.py).
- **Docs**: consolidated guide **[`docs/pipeline/crash-resilience.md`](docs/pipeline/crash-resilience.md)** (checkpoints/resume, heartbeat, RAM preflight, LLM holder, HF token); touches **[`README.md`](README.md)**, **[`docs/README.md`](docs/README.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/reference/inference_profiles.md`](docs/reference/inference_profiles.md), [`docs/reference/quantization.md`](docs/reference/quantization.md), [`docs/pipeline/performance.md`](docs/pipeline/performance.md), [`docs/pipeline/main.md`](docs/pipeline/main.md), [`docs/pipeline/brain.md`](docs/pipeline/brain.md), [`docs/pipeline/voice.md`](docs/pipeline/voice.md), [`docs/ui/ui.md`](docs/ui/ui.md)**.

### Multi-GPU VRAM-first intra-model splitting
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `multi_gpu_shard_mode` — **`off`** (default) or **`vram_first_auto`**; persisted in **`ui_settings.json`**.
- **My PC** ([`UI/tabs/my_pc_tab.py`](UI/tabs/my_pc_tab.py), [`UI/main_window.py`](UI/main_window.py)): **VRAM-first sharding** combo (Off \| VRAM-first multi-GPU); collected into **`AppSettings`** like other GPU fields.
- **Module** [`src/gpu/multi_device/`](src/gpu/multi_device/): **`registry.py`** — lookup + normalized Hub keys; one row per curated **`model_options()`** repo plus per-kind **`__fallback__`** unknown IDs; **`hardware_budget.py`** — `torch.cuda.mem_get_info` estimates + **`max_memory`** dict for Accelerate; **`gates.py`** — master toggle (`Auto`, ≥2 CUDA, no **`AQUADUCT_CUDA_DEVICE`**); **`validators.py`**; **`runtime.py`** — LLM **`device_map="balanced"`** + **`max_memory`** when BF16/FP16 and registry allows; optional diffusers **peer-GPU** submodule moves (`text_encoder`, …) after full-GPU placement.
- **CUDA env API** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): public **`cuda_env_override_device_index()`** ( **`AQUADUCT_CUDA_DEVICE`** ); **`resolve_voice_cuda_device_index()`** for TTS routing.
- **LLM** ([`src/content/brain.py`](src/content/brain.py)): **`load_causal_lm_from_pretrained(..., inference_settings=, hub_model_id=)`**; resolves **`auto`** quant before placement; BitsAndBytes paths stay **`{"": llm_index}`**; float paths may use Accelerate-balanced + **`max_memory`** when gates pass. **`_load_causal_lm_pair`** passes **`model_id`** + settings.
- **Factcheck** ([`src/content/factcheck.py`](src/content/factcheck.py), [`main.py`](main.py)): **`rewrite_with_uncertainty`** threads **`inference_settings`** and **`llm_cuda_device_index`** into the loader.
- **Diffusion** ([`src/util/diffusion_placement.py`](src/util/diffusion_placement.py)): optional **`inference_settings`** into **`resolve_diffusion_offload_mode`** — with VRAM-first + Auto + ≥2 GPUs + ≥**~8 GiB** free host RAM, **`auto`** offload may prefer **`none`** so peer submodule moves can run; **`place_diffusion_pipeline(..., model_repo_id=, placement_role=, quant_mode=)`**; post-load **`_maybe_apply_vram_first_peer_modules`** (effective quant includes resolved **`auto`**).
- **Image / video** ([`src/render/artist.py`](src/render/artist.py), [`src/render/clips.py`](src/render/clips.py)): **`_place_pipe_on_device`** / T2V paths pass **`inference_settings`**, repo id, and role into placement.
- **Voice** ([`src/speech/tts_kokoro_moss.py`](src/speech/tts_kokoro_moss.py), [`src/speech/voice.py`](src/speech/voice.py), [`main.py`](main.py), [`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py)): **MOSS** uses explicit **`cuda:N`** + **`torch.cuda.set_device`** when a voice CUDA index is resolved; **`synthesize`** / **`synthesize_unhinged_moss`** accept **`voice_cuda_device_index`**.
- **Debug** ([`debug/debug_log.py`](debug/debug_log.py)): **`gpu_plan`** category for placement breadcrumbs; [`debug/gpu_plan/README.md`](debug/gpu_plan/README.md).
- **Docs**: [`docs/reference/hardware.md`](docs/reference/hardware.md), [`docs/pipeline/performance.md`](docs/pipeline/performance.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/ui/ui.md`](docs/ui/ui.md).
- **Tests**: [`tests/gpu/test_multi_device.py`](tests/gpu/test_multi_device.py).

### CUDA / PyTorch host UX + tokenizer deps
- **CUDA helpers** ([`src/util/cuda_capabilities.py`](src/util/cuda_capabilities.py)): shared **`torch_cuda_kernels_work`**, **`cuda_device_reported_by_torch`** (centralized probes used across placement / loaders).
- **CPU-only PyTorch prompt** ([`UI/dialogs/cuda_torch_prompt_dialog.py`](UI/dialogs/cuda_torch_prompt_dialog.py)): modal when an NVIDIA GPU is visible but the active wheel is CPU-only; ties into install-deps flow.
- **Torch install / deps UI** ([`src/models/torch_install.py`](src/models/torch_install.py), [`UI/dialogs/install_deps_dialog.py`](UI/dialogs/install_deps_dialog.py), [`main.py`](main.py)): improved CUDA wheel guidance and install wiring.
- **Requirements** ([`requirements.txt`](requirements.txt)): **`sentencepiece`**, **`tiktoken`** for tokenizer paths used by some video / transformers stacks (e.g. CogVideoX).
- **Tests**: [`tests/models/test_torch_install_gate.py`](tests/models/test_torch_install_gate.py).

### Resource usage dialog (expanded)
- **UI** ([`UI/dialogs/resource_graph_dialog.py`](UI/dialogs/resource_graph_dialog.py)): substantial refresh — metrics, layout, and interaction updates for the title-bar **Resource usage** window.

### Pipeline / observability (incremental)
- **OOM recovery** ([`src/runtime/oom_retry.py`](src/runtime/oom_retry.py), [`tests/runtime/test_oom_retry_fit.py`](tests/runtime/test_oom_retry_fit.py)): broader edge-case handling and tests.
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py), [`tests/runtime/test_preflight.py`](tests/runtime/test_preflight.py)): extended coverage.
- **Resource sampling** ([`src/util/resource_sample.py`](src/util/resource_sample.py), [`tests/models/test_resource_sample.py`](tests/models/test_resource_sample.py)): sampling adjustments + tests.
- **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): minor probing refinements.
- **VRAM utilities** ([`src/util/utils_vram.py`](src/util/utils_vram.py), [`src/util/vram_watchdog.py`](src/util/vram_watchdog.py), [`src/util/cpu_parallelism.py`](src/util/cpu_parallelism.py)): alignment with shared CUDA helpers.
- **Quant loader tests** ([`tests/models/test_quant_loader_chain.py`](tests/models/test_quant_loader_chain.py)): updates for **`load_causal_lm_from_pretrained`** signature / kwargs.

### UI / help
- **Tutorial tooltips** ([`UI/help/tutorial_links.py`](UI/help/tutorial_links.py), [`tests/ui/test_help_tooltip_rich.py`](tests/ui/test_help_tooltip_rich.py)): content and test updates.
- **Settings / API widgets** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`UI/services/api_model_widgets.py`](UI/services/api_model_widgets.py)): small adjustments.

### Pipeline memory boundaries (host RAM / VRAM staging)
- **`src/util/memory_budget.py`**: `release_between_stages` orchestrates stage transitions by calling **`cleanup_vram`** or **`prepare_for_next_model`** only (no duplicate CUDA cache logic).
- **`main.py`**: boundaries after script LLM, voice, polish, Pro img2vid/T2V transitions, slideshow diffusion→mux, motion keyframes→clips, and encode-adjacent cheap drops; **`src/runtime/pipeline_api.py`** parity after script and voice polish (cheap clears).
- **`src/content/story_pipeline.py`**: after multistage refinement disposes the causal LM, **`release_between_stages`** runs with the LLM CUDA ordinal when a session actually loaded weights.
- **`UI/workers/impl.py`**: **`PreviewWorker`** / **`StoryboardWorker`** **`finally`** cleanup; **`CharacterPortraitWorker`** uses **`prepare_diffusion`** before local **`generate_images`**.
- **`src/render/clips.py`**: text-to-video / image-to-video preload passes **`cuda_device_index`** into **`prepare_diffusion`**; post-batch **`cheap`** boundary after **`del pipe`**.
- **`src/render/artist.py`**: **`_maybe_enable_slice_inference`** after placement on image pipelines; post-batch teardown uses **`release_between_stages`** (**`cheap`**).
- **`src/util/resource_sample.py`**, **`UI/dialogs/resource_graph_dialog.py`**: sparkline samples expose **tree RSS MB**, **host free RAM**, **machine-wide system RAM used %** (`psutil.virtual_memory().percent`), and **child-process count** (CPU / RAM tooltips; FFmpeg called out on CPU). Sampling uses **one** recursive process-tree walk per tick (CPU + RSS + child count).
- **`src/util/memory_budget.py`**: module doc notes CPU thread env belongs in hardware docs — boundaries do not alter ``OMP_*`` mid-run.
- **`src/runtime/preflight.py`**: optional **`AQUADUCT_HOST_RAM_PREFLIGHT`** adds a soft warning when free host RAM is under ~**4 GiB** in **local** execution mode.
- **`src/runtime/preflight_host_hints.py`**, **`preflight.py`**: optional **`AQUADUCT_PREFLIGHT_HEAVY_REPO_RAM`** (HF size cache + frontier repo ids vs free‑RAM threshold) and **`AQUADUCT_CPU_PREFLIGHT`** (high host CPU % via **`psutil`**).
- **`src/util/diffusers_load.py`**: **`AQUADUCT_DIFFUSERS_DISABLE_MMAP`** merges **`disable_mmap`** into diffusers **`from_pretrained`** with **`TypeError`** fallback; wired from **`clips.py`** / **`artist.py`**.
- **Debug** ([`debug/debug_log.py`](debug/debug_log.py)): **`memory_budget`** category for `dprint`.
- **Docs**: [`docs/reference/vram.md`](docs/reference/vram.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/ui/ui.md`](docs/ui/ui.md).
- **Tests**: [`tests/util/test_memory_budget.py`](tests/util/test_memory_budget.py), [`tests/runtime/test_preflight.py`](tests/runtime/test_preflight.py), [`tests/util/test_diffusers_load.py`](tests/util/test_diffusers_load.py), [`tests/runtime/test_vram_watchdog.py`](tests/runtime/test_vram_watchdog.py), [`tests/models/test_resource_sample.py`](tests/models/test_resource_sample.py).

### VRAM watchdog + pipeline notices
- **`src/util/vram_watchdog.py`**: **`check_cuda_headroom`** inspects **`torch.cuda.mem_get_info`** before heavy loads — logs warnings, optional **`emit_pipeline_notice`** to the desktop worker, or **`RuntimeError`** when free VRAM is critically low (tunable via **`AQUADUCT_VRAM_WATCHDOG`** and **`AQUADUCT_VRAM_*_FREE_*`** env vars). **`cuda_mem_snapshot`** for diagnostics.
- **`src/runtime/pipeline_notice.py`**: context‑scoped callback (**`pipeline_notice_scope`**) so worker threads can raise **non-blocking** UI notices without importing Qt.
- **`UI/workers/impl.py`**: **`PipelineWorker`** wraps **`run_once`** in **`pipeline_notice_scope`** ( **`pipeline_warning`** signal).
- **`UI/main_window.py`**: connects **`pipeline_warning`**; **`_run_when_ffmpeg_ready`** returns **`bool`** and **`_pipeline_launch_pending`** avoids queue races while FFmpeg prefetch is in flight or the worker has not yet **`start()`**‑ed.
- **`src/util/utils_vram.py`**, **`src/content/brain.py`**, **`src/util/memory_budget.py`**: integrate **`check_cuda_headroom`** at diffusion prep and LLM load boundaries.

### Inference profile logging + script JSON extraction
- **`src/models/inference_profiles.py`**: serialized **`log_inference_profiles_for_run`** (thread lock, batched stderr lines, mirror lines to **`logs/debug.log`** via **`append_debug_log`**).
- **`src/content/brain.py`**: **`_slice_first_balanced_json_object`** — robust extraction when models wrap JSON in fences or prose with nested braces.

### Desktop UI + Library
- **`AppSettings`** / **`ui_settings.json`**: **`resource_graph_split_view`** — optional **one VRAM sparkline per CUDA GPU** in the resource graph (wired from **`MainWindow`** snapshot → worker).
- **Resource usage** ([`UI/dialogs/resource_graph_dialog.py`](UI/dialogs/resource_graph_dialog.py)): title-bar **mini / expanded** toggle (SVG expand–compress) left of **Close**; **`resource_graph_compact`** in **`ui_settings.json`** (default **`true`** / missing key → compact). **[`FramelessDialog`](UI/dialogs/frameless_dialog.py)** **`insert_title_bar_widget_before_close`** for title-bar controls; new icons in **[`UI/widgets/title_bar_svg_icons.py`](UI/widgets/title_bar_svg_icons.py)** / **[`UI/widgets/title_bar_outline_button.py`](UI/widgets/title_bar_outline_button.py)**.
- **`UI/tabs/library_tab.py`**: scrollable Library tab; tighter default **videos** table height (min/max) for small screens.

### My PC — CPU name + nominal clock
- **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): CPU line uses WMI / ``/proc/cpuinfo`` / macOS ``sysctl`` when possible (commercial name + ``~X.XX GHz max`` from nominal max MHz where exposed); falls back to ``platform.processor()`` unchanged if lookups fail. Windows subprocess probes use **`CREATE_NO_WINDOW`** where supported so brief PowerShell/WMI checks do not flash a console.
- **Docs**: [`docs/reference/hardware.md`](docs/reference/hardware.md).
- **Tests**: [`tests/models/test_hardware_cpu_display.py`](tests/models/test_hardware_cpu_display.py).

### Pipeline observability + VRAM OOM recovery
- **Always-on run logging** ([`debug/debug_log.py`](debug/debug_log.py), [`debug/__init__.py`](debug/__init__.py)): [`pipeline_console`](debug/debug_log.py) / [`log_pipeline_exception`](debug/debug_log.py) — stderr lines `[Aquaduct][run] [stage] …`, failure traceback from [`main.py`](main.py) `run_once`; append to [`logs/debug.log`](src/util/repo_logs.py) when writable.
- **`main.py`**: `_run_stage(...)` milestones across the desktop pipeline; [`_clear_after_oom`](main.py) runs **`torch.cuda.synchronize()`** before CUDA cache flush; **`retry_stage`** calls for **video** diffusion pass **`max_quant_downgrades=8`** ([`pro_i2v`](main.py), [`pro_t2v`](main.py), [`clips`](main.py), [`scene_clips`](main.py)).
- **`src/runtime/oom_retry.py`**: broader [`is_oom_error`](src/runtime/oom_retry.py); [`pick_next_gpu_index_after_oom`](src/runtime/oom_retry.py) — prefer larger VRAM, then equal‑VRAM peer, never switch down to a smaller card as recovery; [**preempt**](src/runtime/oom_retry.py) when GPU VRAM use ≥ **`AQUADUCT_VRAM_PREEMPT_USED_FRAC`** (default **0.99**) after [`clear_cb`](src/util/utils_vram.py): try [`pick_relief_gpu_index`](src/runtime/oom_retry.py), then lower quant — **before** the stage runs; [`retry_stage`](src/runtime/oom_retry.py)(…, **`preempt_high_vram`**); default quant retries **5**; OOM recovery logging.
- **`src/render/clips.py`**: Wan / generic T2V load breadcrumbs (**`video_t2v_load`**, **`video_t2v_infer`**).
- **`UI/workers/impl.py`**: **`PreviewWorker`**, **`StoryboardWorker`**, **`PipelineWorker`**, FFmpeg/downloads/uploads/text expand/character/model workers — [`_reraise_system_interrupt`](UI/workers/impl.py); top-level **`except BaseException`** so e.g. **`torch.cuda.OutOfMemoryError`** reaches **`failed.emit`** with CUDA hints ([`_failure_text_with_cuda_hints`](UI/workers/impl.py)).
- **Tests**: [`tests/runtime/test_oom_retry_fit.py`](tests/runtime/test_oom_retry_fit.py).
- **Docs**: [`docs/reference/inference_profiles.md`](docs/reference/inference_profiles.md), [`debug/README.md`](debug/README.md).

### Health advice video format + **Realism** art style
- **Pipeline format** [`health_advice`](src/core/config.py): clinician-voiced wellness education scripts ([`src/content/brain.py`](src/content/brain.py) `_prompt_for_health_advice_items`, safety blocks, `_article_prompt_block` / `_vf_hint`); ephemeral / fallback **doctor or nurse** cast ([`src/content/characters_store.py`](src/content/characters_store.py)); multi-stage refinement ([`src/content/story_pipeline.py`](src/content/story_pipeline.py)); **Key facts** card enabled like news/explainer ([`video_format_supports_facts_card`](src/core/config.py)); diffusion cues ([`src/content/prompt_conditioning.py`](src/content/prompt_conditioning.py)).
- **Discover & crawl**: Firecrawl-first for `health_advice` (no Google News for Topics-only Discover); health-biased queries in [`src/content/crawler.py`](src/content/crawler.py); phrase ranking in [`src/content/topic_discovery.py`](src/content/topic_discovery.py); [`video_format_writes_topic_research_pack()`](src/content/topics.py) gates **`data/topic_research/<mode>/`** writes and digest ([`src/content/topic_research_assets.py`](src/content/topic_research_assets.py)); [`TopicDiscoverWorker`](UI/workers/impl.py).
- **Story web context** ([`src/content/story_context.py`](src/content/story_context.py)): `health_advice` uses richer scrape budget + wellness supplement searches like creative modes.
- **Resolution in script LLM context**: [`main.py`](main.py) and [`UI/workers/impl.py`](UI/workers/impl.py) prepend **width×height** (and portrait/landscape hint) into the script supplement for `health_advice`.
- **UI**: Run tab **Health advice (wellness tips)**; Topics mode + Discover copy for health ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py), [`UI/tabs/topics_tab.py`](UI/tabs/topics_tab.py), [`UI/main_window.py`](UI/main_window.py)). Pro img→vid tip includes `health_advice` ([`main.py`](main.py)).
- **Art style**: **Realism mode** preset `realism` ([`src/settings/art_style_presets.py`](src/settings/art_style_presets.py)) — photoreal / editorial stills bias, distinct from **Documentary real** (`docu_real`).
- **Tests**: [`tests/cli/test_config_and_settings.py`](tests/cli/test_config_and_settings.py), [`tests/content/test_story_context.py`](tests/content/test_story_context.py), [`tests/content/test_crawler_health_queries.py`](tests/content/test_crawler_health_queries.py).
- **Docs**: [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/pipeline/editor.md`](docs/pipeline/editor.md), [`docs/integrations/crawler.md`](docs/integrations/crawler.md), [`README.md`](README.md).

### Docs / UI: local T2V stalls during **Loading weights**
- **Docs** ([`docs/reference/inference_profiles.md`](docs/reference/inference_profiles.md)): troubleshooting when loading frontier T2V checkpoints fails or the process exits mid-load (VRAM, **CPU offload**, lighter model, GPU policy).
- **UI** ([`UI/workers/impl.py`](UI/workers/impl.py)): CUDA OOM–style errors from pipeline/preview/storyboard workers append a short recovery hint.

### Developer debug: `MODULE_DEBUG_FLAGS`, category registry, and `debug/` tools
- **Debug core** ([`debug/debug_log.py`](debug/debug_log.py), [`debug/__init__.py`](debug/__init__.py)): in-repo boolean `MODULE_DEBUG_FLAGS` (union with `AQUADUCT_DEBUG`, per-category env, and `--debug`); expanded `DEBUG_CATEGORIES` / aliases; stderr `dprint` uses the same timestamped line as file append; module docstring documents empty env + file flags and a possible future “env only” escape hatch.
- **Docs** ([`debug/README.md`](debug/README.md), [`debug/<category>/README.md`](debug/)): index and one README per category; helpers [`debug/tools/print_active.py`](debug/tools/print_active.py), [`debug/tools/smoke_categories.py`](debug/tools/smoke_categories.py), shim [`debug/print_active.py`](debug/print_active.py); [`docs/README.md`](docs/README.md) links the `debug/` tree; [`tests/README.md`](tests/README.md) lists [`tests/debug/`](tests/debug/).
- **Observability**: bounded `dprint` at pipeline API / worker / OpenAI / crawler boundaries; UI shell (save settings, queue, tasks stop/pause, downloads); quantization + hardware fit when `models` / `ui` debug is on; download failure logging in [`src/models/model_manager.py`](src/models/model_manager.py); API script path in [`src/content/brain_api.py`](src/content/brain_api.py); diffusion **placement** (CUDA / quant / offload) in [`src/render/artist.py`](src/render/artist.py) and [`src/render/clips.py`](src/render/clips.py) when `artist` / `clips` is on.
- **Tests** ([`tests/debug/test_debug_registry.py`](tests/debug/test_debug_registry.py)): flag merge, `AQUADUCT_DEBUG=all` with file flags off, `resolve_quant_mode` smoke, `invalidate_debug_cache`, and AST check that every `dprint` category in `src`/`UI`/`debug` matches `DEBUG_CATEGORIES`.

### Tasks tab — remove **queued** pipeline runs without waiting on the active job
- **UI** ([`UI/main_window.py`](UI/main_window.py)): **Remove** on a **Waiting in queue…** row drops that FIFO snapshot immediately (no disk output yet). The in-progress row uses **Stop** to cancel instead.

### Model tab — quantization **slider** + separate **Automatic**
- **UI** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`UI/main_window.py`](UI/main_window.py)): per-role **Automatic (fit this GPU)** checkbox (persists `auto`) and a discrete horizontal **NoWheelSlider** over enabled manual modes only, ordered **low VRAM → higher quality** via [`manual_quant_modes_low_to_high`](src/models/quantization.py). **Auto-fit** drives the same controls after ranked picks. Kokoro voice rows lock Automatic and hide the slider.
- **Policy** ([`src/models/quantization.py`](src/models/quantization.py)): `manual_quant_modes_low_to_high`, `index_of_manual_mode`, `manual_mode_at_index`.
- **Tests** ([`tests/models/test_quantization_manual_order.py`](tests/models/test_quantization_manual_order.py)); **Docs**: [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/quantization.md`](docs/reference/quantization.md).

### Fix: Model tab — responsive **row cards** for local model controls
- **UI** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py)): replaced the fragile five-column model grid with one **row card** per role. Each card now stacks title + fit badge, full-width Hub model dropdown, disk/VRAM metadata, and full-width quant dropdown, so long model names, **On disk** status, VRAM labels, and quant mode text no longer overlap or compete for a single horizontal row.
- **Scroll / 1080p fit**: the Local Model content is now wrapped in a vertical `QScrollArea`, and model / quant combo minimum widths were lowered so cards keep readable natural height instead of being squeezed edge-to-edge at 1080p.

### Fix: Model tab — **quantization** dropdown selection no longer snaps back
- **UI** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py)): `_update_fit_badges` repopulates the per-role quant combo; the selection is now restored from the **live** combo value when the same Hub id is still selected (otherwise from `AppSettings` after a model change). **Auto-fit** calls `_collect_settings_from_ui()` into `win.settings` before the badge refresh so ranked quant modes are not overwritten by stale settings.

### Per-model **quantization controls** (Script / Image / Video / Voice)
- **Policy module** ([`src/models/quantization.py`](src/models/quantization.py)): central definitions for `QuantMode` (`auto`, `bf16`, `fp16`, `int8`, `nf4_4bit`, `cpu_offload`) and `QuantRole` (`script | image | video | voice`); `supported_quant_modes()` enumerates per-role options for the UI (LLMs offer `nf4_4bit`, diffusion rows offer `cpu_offload` etc.); `predict_vram_gb()` applies per-mode multipliers on top of `vram_requirement_hint()` ranges; `pick_auto_mode()` and `resolve_quant_mode()` resolve `auto` against the **effective per-role VRAM** ([`src.util.cuda_device_policy.effective_vram_gb_for_kind`](src/util/cuda_device_policy.py) / [`resolve_effective_vram_gb`](src/models/inference_profiles.py)) so the user’s **GPU policy** (Auto vs Single-pinned) keeps `auto`, fit badges, and Auto-fit consistent.
- **Settings & persistence** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): new `script_quant_mode`, `image_quant_mode`, `video_quant_mode`, `voice_quant_mode` fields on `AppSettings` (default `auto`). The loader sanitizes unknown / alias strings and migrates legacy `try_llm_4bit=True` to `script_quant_mode="nf4_4bit"` when no explicit value is stored.
- **Settings UI** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`UI/main_window.py`](UI/main_window.py)): each Model row gets a compact **quant dropdown** beside the model combo. The VRAM label shows a quant-aware predicted range (e.g. `~7-9 GB · NF4 4-bit`) with a tooltip explaining the multiplier and any experimental fallback. **Auto-fit for this PC** now selects both repo and quant per row from the new ranking. `_collect_settings_from_ui()` persists the dropdowns into `AppSettings`.
- **Auto-fit ranking** ([`src/models/hardware.py`](src/models/hardware.py)): `AutoFitRanked` carries `script_quant_modes / image_quant_modes / video_quant_modes / voice_quant_modes` aligned to ranked repo ids; `rank_models_for_auto_fit()` resolves the best mode using `pick_auto_mode()` against the per-role effective VRAM, so memory-saving modes are selected on small GPUs and quality-preferred modes on large ones.
- **Runtime loaders honor quant mode with safe fallbacks**:
  - **LLM** ([`src/content/brain.py`](src/content/brain.py)): `load_causal_lm_from_pretrained(..., quant_mode=...)` resolves `auto`, attempts the requested `BitsAndBytesConfig` (4-bit NF4 / int8) or fp16/bf16 dtype, and falls back to fp16/CPU on failure with status messages. `_generate_with_transformers` and `rewrite_with_uncertainty` ([`src/content/factcheck.py`](src/content/factcheck.py)) now thread `quant_mode` through; [`main.py`](main.py) passes `app.script_quant_mode`.
  - **Image diffusion** ([`src/render/artist.py`](src/render/artist.py)): `_load_auto_t2i_pipeline` / `_load_auto_i2i_pipeline` accept `quant_mode` (driving dtype + experimental `BitsAndBytesConfig` for diffusers when supported); `_place_pipe_on_device` forces `place_diffusion_pipeline(..., force_offload="model")` for `cpu_offload`.
  - **Video diffusion** ([`src/render/clips.py`](src/render/clips.py)): `_load_text_to_video_pipeline` resolves `quant_mode → torch_dtype` (experimental int8/4-bit falls back to fp16 because backend support varies); `place_diffusion_pipeline(..., force_offload="model" if quant_mode == "cpu_offload" else None)`.
  - **Voice** ([`src/speech/tts_kokoro_moss.py`](src/speech/tts_kokoro_moss.py), [`src/speech/voice.py`](src/speech/voice.py)): MOSS attempts dtype/`BitsAndBytesConfig` per `quant_mode` (with `cpu_offload` forcing CPU); Kokoro accepts the parameter for API symmetry but falls back to its stable path. [`main.py`](main.py) passes `app.voice_quant_mode` into `synthesize`, `synthesize_unhinged_moss`, and `synthesize_unhinged_rotating_kokoro`.
- **Diffusion placement** ([`src/util/diffusion_placement.py`](src/util/diffusion_placement.py)): `place_diffusion_pipeline(..., force_offload=...)` lets the quant policy override the env-driven offload mode without changing the device-resolution path (still via [`cuda_device_policy.resolve_diffusion_cuda_device_index`](src/util/cuda_device_policy.py)).
- **Inference profile logging** ([`src/models/inference_profiles.py`](src/models/inference_profiles.py)): `format_inference_profile_report()` now logs the resolved `quant=` mode per role beside the VRAM band and profile label.
- **Tests**: [`tests/models/test_quantization_policy.py`](tests/models/test_quantization_policy.py) (mode labels, role-supported modes, settings normalization, VRAM multipliers, hint parsing, `pick_auto_mode` thresholds), [`tests/models/test_quant_loader_chain.py`](tests/models/test_quant_loader_chain.py) (mocked `BitsAndBytesConfig` selection per `quant_mode` and CPU fallback), [`tests/models/test_auto_fit.py`](tests/models/test_auto_fit.py) (Auto-fit picks both repo and quant for low/high VRAM hosts), [`tests/ui/test_ui_settings_quantization.py`](tests/ui/test_ui_settings_quantization.py) (save/load roundtrip, legacy `try_llm_4bit` migration, alias / unknown-mode handling).
- **Docs**: [`docs/reference/quantization.md`](docs/reference/quantization.md), with cross-links from [`README.md`](README.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/reference/models.md`](docs/reference/models.md), [`docs/reference/hardware.md`](docs/reference/hardware.md), [`docs/reference/inference_profiles.md`](docs/reference/inference_profiles.md), [`docs/pipeline/brain.md`](docs/pipeline/brain.md), [`docs/pipeline/artist.md`](docs/pipeline/artist.md), [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/README.md`](docs/README.md).

### Tests: modular `tests/` layout
- **Layout**: `pytest` still collects from the `tests` tree; modules live under `tests/<area>/` for easier navigation: **`cli`**, **`ui`**, **`models`**, **`platform`** (HTTP clients), **`runtime`**, **`content`**, **`render`**, **`discover`**, **`social`**, **`core`**. Shared fixtures stay in [`tests/conftest.py`](tests/conftest.py). See [`tests/README.md`](tests/README.md).
- **Docs**: Links in `README.md`, `DEPENDENCIES.md`, `docs/review/`, `docs/reference/inference_profiles.md`, and historical entries in this file now point at the new paths (run `pytest` the same as before: `tests` is the collection root).
- **CLI smoke**: [`tests/cli/test_cli_smoke.py`](tests/cli/test_cli_smoke.py) resolves the repository root by locating `main.py` so it works from the nested path.

### API mode: **Kling AI** default for Pro *motion* (text-to-video) + Pika note
- **Catalog** ([`src/settings/api_model_catalog.py`](src/settings/api_model_catalog.py)): **Video (Pro)** list leads with **Kling** — display text notes **~66 credits / 24h** (enough for roughly **6×5s** clips) and **Pika.art** as a ~**30 credits / month** alternative. **Magic Hour** and **Replicate** remain the next options.
- **Client** ([`src/platform/kling_client.py`](src/platform/kling_client.py)): HS256 **JWT** from `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` (and optional `KLINGAPI_*` aliases, `KLING_API_BASE`); `POST /v1/videos/text2video` with nested `input` (flat JSON fallback on HTTP 400), poll `GET /v1/videos/text2video/{task_id}`. **Dispatch** in [`src/runtime/api_generation.py`](src/runtime/api_generation.py) `cloud_video_mp4_paths`; preflight in [`src/runtime/model_backend.py`](src/runtime/model_backend.py); **UI** row gating in [`UI/main_window.py`](UI/main_window.py); tooltips in [`UI/services/api_model_widgets.py`](UI/services/api_model_widgets.py).
- **Tests** ([`tests/platform/test_kling_client.py`](tests/platform/test_kling_client.py), [`tests/runtime/test_api_model_catalog.py`](tests/runtime/test_api_model_catalog.py)). **Docs**: [api_generation.md](docs/integrations/api_generation.md), [config.md](docs/reference/config.md), [models.md](docs/reference/models.md).

### API mode: recommended cloud providers (Gemini, SiliconFlow, Magic Hour, Inworld)
- **Catalog** ([`src/settings/api_model_catalog.py`](src/settings/api_model_catalog.py)): per-role “recommended” providers appear first in the **Generation APIs** dropdowns: **Google AI Studio (Gemini)** for the script LLM (OpenAI-compatible `https://generativelanguage.googleapis.com/v1beta/openai`), **SiliconFlow** for OpenAI-style image generation (Flux/SD3 slugs), Pro video via **Kling** (above), **Magic Hour**, or **Replicate**, and **Inworld** for low-latency TTS. Display names include short free-tier hints; existing providers (OpenAI, Groq, Replicate, ElevenLabs, …) remain available.
- **Keys / preflight** ([`src/runtime/model_backend.py`](src/runtime/model_backend.py)): `effective_siliconflow_api_key`, `effective_kling_access_key` / `effective_kling_secret_key`, `effective_magic_hour_api_key`, `effective_inworld_api_key`; Pro mode accepts **Kling**, **Replicate**, or **Magic Hour** for cloud clips when the corresponding credentials are set.
- **LLM** ([`src/platform/openai_client.py`](src/platform/openai_client.py)): `_normalize_openai_api_base_path` — Gemini’s OpenAI root must not receive an extra `/v1` suffix. **Image** ([`build_image_generation_openai_client`](src/platform/openai_client.py)): SiliconFlow; `download_image_png` also accepts `url` in the response and converts to PNG via **PIL** when needed.
- **Video** ([`src/platform/kling_client.py`](src/platform/kling_client.py), [`src/platform/magichour_client.py`](src/platform/magichour_client.py), [`src/runtime/api_generation.py`](src/runtime/api_generation.py)): `cloud_video_mp4_paths` dispatches Kling, Replicate, or Magic Hour. **Voice** ([`src/speech/inworld_tts.py`](src/speech/inworld_tts.py), [`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py)): Inworld non-streaming TTS with chunking, MP3→WAV via FFmpeg, optional multi-part concat. **UI** ([`UI/main_window.py`](UI/main_window.py), [`UI/services/api_model_widgets.py`](UI/services/api_model_widgets.py)): row enablement and tooltips for the new env vars.
- **Tests**: [`tests/runtime/test_api_model_catalog.py`](tests/runtime/test_api_model_catalog.py), [`tests/platform/test_openai_client.py`](tests/platform/test_openai_client.py), [`tests/runtime/test_api_generation.py`](tests/runtime/test_api_generation.py), [`tests/models/test_model_backend.py`](tests/models/test_model_backend.py) (and existing preflight tests).
- **Docs**: [README](README.md), [docs/integrations/api_generation.md](docs/integrations/api_generation.md), [docs/reference/config.md](docs/reference/config.md), [docs/reference/models.md](docs/reference/models.md), [docs/ui/ui.md](docs/ui/ui.md), [docs/README.md](docs/README.md).

### Fix: curated Qwen3 14B Hub id — `Qwen/Qwen3-14B` (not `-Instruct`)
- **Problem**: curated default **`Qwen/Qwen3-14B-Instruct`** does not exist on the Hub and returned **404 / "Repository Not Found"** in [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1) and [`scripts/download_hf_models.py`](scripts/download_hf_models.py) even when `HF_TOKEN` was authenticated.
- **Reason**: Qwen3 dropped the separate `-Instruct` suffix used in Qwen2.5 — the base repo [`Qwen/Qwen3-14B`](https://huggingface.co/Qwen/Qwen3-14B) is already the chat / instruct repo (see model card, architecture `Qwen3ForCausalLM`, tokenizer with `<|im_start|>` chat template).
- **Fix**: normalize Hub id to **`Qwen/Qwen3-14B`** in [`src/core/config.py`](src/core/config.py) (`get_models().llm_id`), [`src/models/model_manager.py`](src/models/model_manager.py) (Script row 1), [`src/models/inference_profiles.py`](src/models/inference_profiles.py) (`pick_script_profile` exact-match + `_fallback_llm`), [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1), [`scripts/download_hf_models.py`](scripts/download_hf_models.py), [`scripts/prune_models.py`](scripts/prune_models.py). The parallel copy at **`H:\AI Models\download_all_for_transfer.ps1`** was updated in place.
- **Docs**: [`docs/reference/config.md`](docs/reference/config.md), [`docs/reference/models.md`](docs/reference/models.md) (note that Qwen3 has no `-Instruct` suffix), [`docs/pipeline/brain.md`](docs/pipeline/brain.md), [`docs/build/model_youtube_demos.md`](docs/build/model_youtube_demos.md).

### Local pipeline: **VRAM inference profiles** (Auto / Single GPU policy)
- **Module** [`src/models/inference_profiles.py`](src/models/inference_profiles.py): maps **effective VRAM per role** (same as [`cuda_device_policy.effective_vram_gb_for_kind`](src/util/cuda_device_policy.py) + fit badges) to **bands** (`lt_8` … `ge_40`, `unknown`). Per **Hub id**, selects **ScriptProfile** (input / output token caps; repo-specific caps for Qwen3, Miqu, Fimbulvetr, DeepSeek, etc.), **ImageProfile** (resolution, steps, guidance for FLUX / SD3.5 families), **VideoProfile** (frames, steps, resolution where applicable, `extra` for guidance / LTX-2 negative / frame_rate), and **VoiceProfile** (placeholder for Kokoro / MOSS).
- **Merge helpers**: `merge_t2i_from_settings` / `merge_t2v_from_settings` applied after model baselines in [`src/render/artist.py`](src/render/artist.py) and [`src/render/clips.py`](src/render/clips.py). **LTX-2**: `(num_frames - 1) % 8 == 0` enforced after merge. **CogVideoX 5B** / **Mochi**: band adjusts frames / steps without forcing resolution where the pipeline uses defaults.
- **Brain** ([`src/content/brain.py`](src/content/brain.py)): `inference_settings` on `generate_script` / `expand_custom_video_instructions`; [`_llm_max_input_tokens_cap`](src/content/brain.py) and `max_new_tokens` respect profiles when env **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** is unset.
- **Story pipeline** ([`src/content/story_pipeline.py`](src/content/story_pipeline.py)): `run_multistage_refinement(..., app_settings=...)` passes settings into `_generate_with_transformers`.
- **Orchestration** ([`main.py`](main.py)): `log_inference_profiles_for_run` after preflight; all `generate_images` / `generate_clips` / expand paths pass `AppSettings`. **UI** ([`UI/workers/impl.py`](UI/workers/impl.py), [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py)): same merge for workers; **Auto-fit for this PC** appends `[Aquaduct][inference_profile]` lines to the log.
- **Facade** ([`src/runtime/generation_facade.py`](src/runtime/generation_facade.py)): `inference_settings` passed to `generate_script` for local mode.
- **Tests**: [`tests/models/test_inference_profiles.py`](tests/models/test_inference_profiles.py). **Docs**: [`docs/reference/inference_profiles.md`](docs/reference/inference_profiles.md), cross-links in [README](README.md), [config](docs/reference/config.md), [models](docs/reference/models.md), [brain](docs/pipeline/brain.md), [artist](docs/pipeline/artist.md), [ui](docs/ui/ui.md), [main](docs/pipeline/main.md).

### Download list mirror (Windows)
- The optional **standalone** bulk downloader on the transfer drive **`H:\AI Models\download_all_for_transfer.ps1`** now has the same `ALL_REPOS` block as [`scripts/download_hf_models.py`](scripts/download_hf_models.py) (curated models in the app + CLI). Documented in [`docs/reference/models.md`](docs/reference/models.md).

### Video: **Mochi 1.5** + **LTX-2** (curated)
- **Mochi** ([`src/models/model_manager.py`](src/models/model_manager.py)): `genmo/mochi-1.5-final` replaces `genmo/mochi-1-preview` (1.5: reduced temporal jitter, longer default run length). **Clips** ([`src/render/clips.py`](src/render/clips.py)): `CURATED_VIDEO_CLIP_REPO_IDS`, higher **num_frames** cap, same `MochiPipeline` loader.
- **LTX-2** ([`Lightricks/LTX-2`](https://huggingface.co/Lightricks/LTX-2)): fifth curated T2V row — `LTX2Pipeline`, 9:16 **4K**-class defaults (**2176×3840**), VAE **tiling**, optional **PyAV** (`av`) for **encode_video** muxed audio+video. **VRAM** in [`src/models/hardware.py`](src/models/hardware.py); auto-fit ordering **last** among curated T2V (heavy id).
- **Downloads**: [`scripts/download_hf_models.py`](scripts/download_hf_models.py) `ALL_REPOS`, [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1). **Docs / tests**: [`docs/reference/models.md`](docs/reference/models.md), [`docs/reference/hardware.md`](docs/reference/hardware.md), [`tests/models/test_diffusion_presets_coverage.py`](tests/models/test_diffusion_presets_coverage.py).

### Image: **FLUX.1.1 [pro] ultra** (curated)
- **Model tab** ([`src/models/model_manager.py`](src/models/model_manager.py)): `black-forest-labs/FLUX.1.1-pro-ultra` with T2I preset, VRAM hints, and auto-fit ordering in [`src/render/artist.py`](src/render/artist.py), [`src/models/hardware.py`](src/models/hardware.py). Hub access may require login / acceptance; see [`docs/reference/models.md`](docs/reference/models.md) for official BFL quants (FLUX.2 **fp8** / **NVFP4**, etc.) vs this 1.1 id.
- **Downloads**: [`scripts/download_hf_models.py`](scripts/download_hf_models.py) `ALL_REPOS`, [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1).
- **Docs**: [`docs/reference/models.md`](docs/reference/models.md), [`docs/build/model_youtube_demos.md`](docs/build/model_youtube_demos.md).

### Script (LLM): **DeepSeek-V3** 671B MoE (curated)
- **Model tab** ([`src/models/model_manager.py`](src/models/model_manager.py)): fourth script option — **`deepseek-ai/DeepSeek-V3`** (671B total / ~37B active per token, 128K context) for open-weight **complex plot and reasoning** when you have the GPU, RAM, and disk for full-weight or community quantization paths. **VRAM** hints and `rate_model_fit_for_repo` in [`src/models/hardware.py`](src/models/hardware.py).
- **Downloads**: [`scripts/download_hf_models.py`](scripts/download_hf_models.py) `ALL_REPOS`, [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1).
- **Docs**: [`docs/reference/models.md`](docs/reference/models.md), [`docs/pipeline/brain.md`](docs/pipeline/brain.md), [`docs/build/model_youtube_demos.md`](docs/build/model_youtube_demos.md).

### Script (LLM): default **Qwen3 14B**
- **Default** curated script model is now **`Qwen/Qwen3-14B`** (replaces the prior 8B Llama-family default; Qwen3 does **not** publish a separate `-Instruct` suffix — the base repo is the chat/instruct model). Rationale: stronger creative and multi-turn behavior in current public stacks; use standard chat / non–extended-thinking generation paths in your own inference setup when you want fastest prose. **VRAM** heuristics for this id in [`src/models/hardware.py`](src/models/hardware.py).
- **Downloads / prune** lists updated: [`src/core/config.py`](src/core/config.py) `get_models()`, [`scripts/download_hf_models.py`](scripts/download_hf_models.py), [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1), [`scripts/prune_models.py`](scripts/prune_models.py).
- **Docs**: [`docs/reference/config.md`](docs/reference/config.md), [`docs/reference/models.md`](docs/reference/models.md), [`docs/pipeline/brain.md`](docs/pipeline/brain.md), [`docs/build/model_youtube_demos.md`](docs/build/model_youtube_demos.md).

### Video: curated T2V stack (Wan 2.2, Mochi, CogVideoX 5B, HunyuanVideo)
- **Model tab** ([`src/models/model_manager.py`](src/models/model_manager.py)): four **video** options — *Wan 2.2 T2V A14B* (`Wan-AI/Wan2.2-T2V-A14B-Diffusers`), *Mochi 1* (`genmo/mochi-1-preview`), *CogVideoX 5B*, *HunyuanVideo* — with `ui_sequence` row order. Replaces the prior SVD / ZeroScope / Cog2B / LTX curated set (those Hub ids still work if pasted). **VRAM** heuristics ([`src/models/hardware.py`](src/models/hardware.py)) and auto-fit **preference** order updated (Cog5B first for lighter GPUs).
- **Clips** ([`src/render/clips.py`](src/render/clips.py)): `CURATED_VIDEO_CLIP_REPO_IDS`, `WanPipeline` + VAE + `UniPC` flow-shift, `MochiPipeline`, prompt/CLIP handling for T5/UMT5-class stacks.
- **Downloads**: [`scripts/download_hf_models.py`](scripts/download_hf_models.py), [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1), and the parallel copy at `H:\AI Models\download_all_for_transfer.ps1` (same `ALL_REPOS` as the app). **Dependencies**: `diffusers>=0.32.0` for **Wan** / **Mochi** pipelines in [`requirements.txt`](requirements.txt).
- **Docs / tests**: [`docs/reference/models.md`](docs/reference/models.md), [`tests/models/test_diffusion_presets_coverage.py`](tests/models/test_diffusion_presets_coverage.py), [`tests/models/test_auto_fit.py`](tests/models/test_auto_fit.py).

### Image: curated list (FLUX + SD3.5 + turbo)
- **Model tab** ([`src/models/model_manager.py`](src/models/model_manager.py)): five **image** options — *FLUX.1 [dev]*, *FLUX.1 [schnell]*, *Stable Diffusion 3.5 Large*, *3.5 Medium*, *Stable Diffusion 3 Turbo* (`stabilityai/stable-diffusion-3.5-large-turbo` — ADD, few-step). `ui_sequence` keeps this order in the dropdown. Replaces the prior SDXL/SD1.5/SD3 Medium set as curated defaults; users can still paste other Hub ids.
- **T2I presets** ([`src/render/artist.py`](src/render/artist.py)): `CURATED_TEXT2IMAGE_REPO_IDS` + `_IMAGE_T2I_PRESETS` for the five repos; default **`sdxl_turbo_id` fallback** in [`src/core/config.py`](src/core/config.py) is **`black-forest-labs/FLUX.1-schnell`**. **Hardware** auto-fit/tie preferences ([`src/models/hardware.py`](src/models/hardware.py)) and **prune** example preset updated.
- **Scripts**: [`scripts/download_hf_models.py`](scripts/download_hf_models.py) (`MINIMAL_REPOS` + `ALL_REPOS` image block), [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1), [`scripts/prune_models.py`](scripts/prune_models.py).
- **Docs / tests**: [`docs/reference/models.md`](docs/reference/models.md), [`tests/models/test_auto_fit.py`](tests/models/test_auto_fit.py), [`tests/models/test_diffusion_presets_coverage.py`](tests/models/test_diffusion_presets_coverage.py).

### Script (LLM): curated storytelling stack (four picks) — *superseded default; see “Qwen3 14B” above*
- **Model tab** ([`src/models/model_manager.py`](src/models/model_manager.py)): Script row **(1)** is **`Qwen/Qwen3-14B`**; **(2) Fimbulvetr** — `Sao10K/Fimbulvetr-11B-v2`, **(3) Midnight Miqu** — `sophosympatheia/Midnight-Miqu-70B-v1.5`, **(4) DeepSeek-V3** — `deepseek-ai/DeepSeek-V3`. Users can still paste any compatible Hub id.
- **Fit** ([`src/models/hardware.py`](src/models/hardware.py)): Tighter per-repo **script** VRAM hints for these picks (plus 8B-class legacy heuristics when a typed id matches).
- **Downloads**: lists aligned in [`scripts/download_hf_models.py`](scripts/download_hf_models.py), [`scripts/download_all_for_transfer.ps1`](scripts/download_all_for_transfer.ps1). [`scripts/prune_models.py`](scripts/prune_models.py) example preset id updated.
- **Docs**: [`docs/reference/config.md`](docs/reference/config.md), [`docs/pipeline/brain.md`](docs/pipeline/brain.md), [`docs/reference/models.md`](docs/reference/models.md), [`docs/build/model_youtube_demos.md`](docs/build/model_youtube_demos.md).

### GPU / diffusion: multi-GPU offload, placement, video prompts, and SVD VRAM
- **Device routing** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): In **Auto** with **two or more** CUDA devices, **LLM** and **diffusion** are always assigned **different** ordinals (max-VRAM GPU for image/video, compute-heuristic GPU for script; if those collide, LLM moves to the best remaining GPU). A small safety net avoids assigning both roles to the same index if that ever regresses.
- **Diffusion offload** ([`src/util/diffusion_placement.py`](src/util/diffusion_placement.py)): **`auto`** chooses **sequential** CPU offload when **`torch.cuda.device_count() >= 2`** to keep peak VRAM low on the diffusion GPU. **`enable_sequential_cpu_offload`** now receives **`gpu_id`** when a diffusion CUDA index is set (previously only model offload passed it). Single-GPU **`auto`** still uses **full GPU** (`none`) only from **≥16 GiB** detected VRAM (with host-RAM exceptions unchanged); 8–15 GiB uses **model** offload unless overridden.
- **Video clips** ([`src/render/clips.py`](src/render/clips.py)): **CLIP** text paths: optional **77-token** round-trip via `CLIPTokenizerFast` after word/char caps (skipped for CogVideoX / LTX). **SVD** img2vid: tighter **`num_frames`** cap on **≤12 GiB** cards, smaller **`decode_chunk_size`** on those GPUs, prior OOM-oriented placement tweaks retained.
- **Tests**: [`tests/models/test_diffusion_placement.py`](tests/models/test_diffusion_placement.py) (multi-GPU sequential default, `gpu_id` on sequential), [`tests/render/test_clips_img2vid_prompt.py`](tests/render/test_clips_img2vid_prompt.py).
- **Docs**: [`README.md`](README.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/reference/hardware.md`](docs/reference/hardware.md), [`docs/pipeline/performance.md`](docs/pipeline/performance.md), [`docs/reference/vram.md`](docs/reference/vram.md), [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/models.md`](docs/reference/models.md).

### Curated frontier models (image + video), download list, and docs
- **Model registry** ([`src/models/model_manager.py`](src/models/model_manager.py)): **Image** — *FLUX.1 Schnell*, *Stable Diffusion 3 Medium*, *FLUX.1-dev* alongside SDXL / SD 1.5 / SDXL Base. **Video** — *CogVideoX 2B/5B*, *LTX-Video*, *HunyuanVideo* alongside SVD, ZeroScope, ModelScope T2V.
- **Rendering** ([`src/render/artist.py`](src/render/artist.py)): T2I loading via **`_load_auto_t2i_pipeline`** / **`_load_auto_i2i_pipeline`** (BF16 for FLUX/SD3; FP16+`variant` for SDXL-class); **`_apply_flux_negative_cfg`** for Flux + negative prompt; presets in **`_IMAGE_T2I_PRESETS`** / **`_diffusion_kw_for_model`**. **Tests**: [`tests/models/test_diffusion_presets_coverage.py`](tests/models/test_diffusion_presets_coverage.py).
- **Clips** ([`src/render/clips.py`](src/render/clips.py)): **`CogVideoXPipeline`**, **`LTXPipeline`**, **`HunyuanVideoPipeline`** where applicable; **`CURATED_VIDEO_CLIP_REPO_IDS`**, **`_video_pipe_kwargs`**, **`_load_text_to_video_pipeline`**. **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): VRAM hints + **`rate_model_fit_for_repo`** / **`_MOTION_VIDEO_PREF_ORDER`** for new video ids.
- **Docs**: [`README.md`](README.md), [`docs/reference/models.md`](docs/reference/models.md) (curated table + download commands), [`docs/pipeline/artist.md`](docs/pipeline/artist.md), [`docs/reference/hardware.md`](docs/reference/hardware.md).
- **Scripts** ([`scripts/download_hf_models.py`](scripts/download_hf_models.py)): **`ALL_REPOS`** aligned with `model_options()` for `python scripts/download_hf_models.py --all`.

### UI: vector icons, tab alignment, theme palettes, LLM VRAM caps, multi-GPU Auto split
- **Title bar** ([`UI/widgets/title_bar_outline_button.py`](UI/widgets/title_bar_outline_button.py), [`UI/widgets/title_bar_svg_icons.py`](UI/widgets/title_bar_svg_icons.py), [`UI/main_window.py`](UI/main_window.py)): Save / resource graph / Help / Close use **QSvgRenderer**-drawn strokes (theme-colored) instead of emoji/text; LRU-cached pixmaps.
- **Characters toolbar** ([`UI/widgets/toolbar_svg_icons.py`](UI/widgets/toolbar_svg_icons.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)): Add / duplicate / delete use SVG icons (muted palette); removed Fusion standard pixmaps + duplicate fallback glyph.
- **Tasks run controls** ([`UI/tabs/tasks_tab.py`](UI/tabs/tasks_tab.py), [`UI/main_window.py`](UI/main_window.py)): Refresh / pause|play / stop use SVG icons (accent / text / danger); `_sync_tasks_pause_button_appearance` swaps pause vs play vectors.
- **Frozen EXE** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden import **`PyQt6.QtSvg`** for SVG rendering.
- **Tabs** ([`UI/theme/palette.py`](UI/theme/palette.py)): **`QTabWidget::tab-bar { left: 10px; }`** so the tab strip aligns with the pane below (reduces left overhang on dark Fusion).
- **Branding palettes** ([`UI/theme/palette.py`](UI/theme/palette.py), [`UI/tabs/branding_tab.py`](UI/tabs/branding_tab.py)): Added presets **forest**, **lavender**, **ember**, **slate**, **rose**, **amber**, **nord**, **dracula** (in addition to default / tiktok / ocean / sunset / mono).
- **Local LLM VRAM** ([`src/content/brain.py`](src/content/brain.py)): When **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** is unset, **CUDA total VRAM** tightens the default input cap (e.g. &lt;10 GiB → **1536** tokens) to reduce prefill OOM on ~8 GB cards; `empty_cache()` before `generate()` retained/extended.
- **Multi-GPU Auto** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): If **max-VRAM** and **compute** heuristics pick the **same** GPU, **LLM** moves to the **best remaining** compute GPU so a second card is used; [`UI/widgets/gpu_policy_toggle.py`](UI/widgets/gpu_policy_toggle.py) + resource graph Monitor tooltip updated. **Tests**: [`tests/models/test_cuda_device_policy.py`](tests/models/test_cuda_device_policy.py).

### Desktop UI: section cards, My PC GPU refresh, tab polish
- **Theme** ([`UI/theme.py`](UI/theme.py)): `QFrame#SettingsSectionCard` uses palette **`card`**; scoped QSS for inputs inside cards (slightly lifted background) so nested controls do not read as a flat double slab.
- **Sections** ([`UI/tab_sections.py`](UI/tab_sections.py)): **`section_card()`** returns a framed layout helper aligned with **`section_title()`** (documented as using the **`card`** token).
- **My PC** ([`UI/tabs/my_pc_tab.py`](UI/tabs/my_pc_tab.py), [`UI/gpu_policy_toggle.py`](UI/gpu_policy_toggle.py)): GPU spec as **plain lines** (`Name (X.X GB)` per adapter); **Auto** \| **Select GPU** segmented control (replaces combo-only policy); **Device** combo only when **Select GPU** and CUDA GPUs exist; removed redundant VRAM summary row, env override label block, and old fit/env clutter. **`GpuPolicyToggle`** tooltips describe stage routing (non-pooled VRAM) and **`AQUADUCT_CUDA_DEVICE`** override.
- **Collect settings** ([`UI/main_window.py`](UI/main_window.py)): GPU mode from **`gpu_policy_toggle`** (settings fallback if absent); removed legacy **`gpu_policy_combo`** branch.
- **Run** ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py)): **Actions** no longer shows a long Tasks hint line; status guidance on **Run** tooltip + **`refresh_run_tab_for_media_mode`** (Photo vs Video).
- **Topics** ([`UI/tabs/topics_tab.py`](UI/tabs/topics_tab.py)): Tag editor inside a **section card**; shorter intro; long copy on mode combo tooltip.
- **Library** ([`UI/tabs/library_tab.py`](UI/tabs/library_tab.py)): **videos/**/**pictures/** table and **runs/** table each in a **section card**; shorter intro; **`win._library_media_title`** for dynamic section title.
- **API** ([`UI/tabs/api_tab.py`](UI/tabs/api_tab.py)): Hugging Face, Firecrawl, ElevenLabs, TikTok, YouTube blocks use **section cards** + spacing; shorter subtitle with env override tooltip.
- **Characters** ([`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)): **Characters** list/preset and **Profile** editor in separate **section cards**; shorter copy; tips in tooltips.
- **Branding** ([`UI/tabs/branding_tab.py`](UI/tabs/branding_tab.py)): Shorter subtitle + tooltip.
- **Docs**: [`README.md`](README.md), [`docs/ui/ui.md`](docs/ui/ui.md) (composition, Run/Topics/Library/API/Characters/Theme, My PC), [`docs/reference/hardware.md`](docs/reference/hardware.md), [`docs/reference/config.md`](docs/reference/config.md) (GPU policy UI mapping), [`docs/reference/models.md`](docs/reference/models.md), [`docs/pipeline/performance.md`](docs/pipeline/performance.md).

### Multi-GPU: My PC, resource monitor, runtime policy
- **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): `GpuDevice`, `list_cuda_gpus()`, VRAM-max and heuristic compute pickers; `HardwareInfo` can summarize multiple GPUs.
- **Policy** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): Auto vs single, `effective_vram_gb_for_kind`, `resolve_llm_cuda_device_index` / `resolve_diffusion_cuda_device_index`; optional **`AQUADUCT_CUDA_DEVICE`** override; `DevicePlan` includes reserved **`use_model_parallel_llm`** (currently always `False` — no automatic Accelerate multi-GPU LLM sharding; 4-bit stays single-GPU).
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `gpu_selection_mode`, `gpu_device_index`, `resource_graph_monitor_gpu_index` in `ui_settings.json`.
- **UI** (see also **Desktop UI: section cards…** above): **My PC** model **Fit** table + GPU policy persistence; **Resource graph** monitor combo + `sample_gpu_mem_pct()`; **Model** tab fit parity with effective VRAM + tab-switch refresh ([`UI/main_window.py`](UI/main_window.py)).
- **Runtime**: [`src/content/brain.py`](src/content/brain.py), [`src/util/diffusion_placement.py`](src/util/diffusion_placement.py), [`src/render/artist.py`](src/render/artist.py), [`src/render/clips.py`](src/render/clips.py), [`main.py`](main.py) / [`UI/workers.py`](UI/workers.py) pass resolved CUDA indices.
- **Docs**: [`README.md`](README.md), [`docs/reference/hardware.md`](docs/reference/hardware.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/models.md`](docs/reference/models.md), [`docs/pipeline/performance.md`](docs/pipeline/performance.md), [`docs/reference/vram.md`](docs/reference/vram.md). **Tests**: [`tests/models/test_cuda_device_policy.py`](tests/models/test_cuda_device_policy.py), [`tests/models/test_resource_sample.py`](tests/models/test_resource_sample.py).

### Photo mode + API: still images only (no MP4 / clips)
- **Pipeline** ([`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py)): **`run_once_api`** now branches on **`media_mode == "photo"`** after the script step: generates **API** stills via **`generate_still_png_bytes`**, optional layout / grid (`Picture` settings), writes **`final.png`**, and returns — **no** voice, **no** Replicate video clips, **no** slideshow MP4.
- **API preflight** ([`src/runtime/model_backend.py`](src/runtime/model_backend.py)): when **`media_mode` is `photo`**, only **LLM** + **Image** providers/keys are required (voice and video/Replicate rules for motion do not apply).

### Local LLM: prompt truncation (VRAM)
- **Brain** ([`src/content/brain.py`](src/content/brain.py)): local transformers `generate()` tokenizes the instruction prompt with **`truncation=True`** and a cap (default **4096**, or **`min(4096, tokenizer.model_max_length)`** when finite). Override with **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** (256–100000). Calls **`torch.cuda.empty_cache()`** before **`generate()`** when CUDA is available to reduce fragmentation-related OOM on tight GPUs.
- **Docs**: [`docs/reference/config.md`](docs/reference/config.md).

### Run guard: local models + API preflight before pipeline
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py)): **`local_hf_model_snapshot_errors()`** — in **Local** mode, requires on-disk Hub snapshots for the roles the pipeline loads (defaults match [`main.py`](main.py) `run_once`): **Photo** mode → Script (LLM) + Image; **Video** mode → Script + Image + Voice + Video (motion). Skipped in **API** mode (existing **`api_preflight_errors`** applies).
- **UI** ([`UI/main_window.py`](UI/main_window.py)): on failed strict preflight, **Run** / queued jobs / approved preview / approved storyboard open the **Model** tab and show a borderless **Download models before running** or **Configure API before running** dialog (other preflight failures use a generic title). Queueing while a job runs also runs preflight before enqueueing.

### Startup splash (desktop cold start)
- **UI** ([`UI/startup_splash.py`](UI/startup_splash.py), [`UI/app.py`](UI/app.py)): after **`QApplication`** starts, a frameless **splash** shows **Aquaduct**, a **progress bar** (determinate steps + **indeterminate** during blocking imports / `MainWindow()` init), and **elapsed seconds**. Set **`AQUADUCT_NO_SPLASH=1`** to disable. **`MainWindow`** is imported inside **`main()`** so the window can paint before the heaviest import work.
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden import **`UI.startup_splash`**.
- **Docs**: [`docs/ui/ui.md`](docs/ui/ui.md).

### Desktop UI: Photo / Video mode and smooth dialog chrome
- **Media mode** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): persisted **`media_mode`**: **`video`** (default) or **`photo`** in `ui_settings.json`. The title bar **Photo \| Video** toggle switches the pipeline output root ([`media_output_root()`](src/core/config.py)): **`.Aquaduct_data/videos`** vs **`.Aquaduct_data/pictures`**, tab visibility (e.g. **Picture** vs **Video** tab, Captions/Effects in video mode), and Library refresh targets.
- **Dialog chrome** ([`UI/title_bar_outline_button.py`](UI/title_bar_outline_button.py), [`UI/frameless_dialog.py`](UI/frameless_dialog.py), [`UI/tutorial_dialog.py`](UI/tutorial_dialog.py), [`UI/download_popup.py`](UI/download_popup.py), [`UI/install_deps_dialog.py`](UI/install_deps_dialog.py)): borderless dialogs, the Help tutorial (**Previous** / **Next** / **Close**), model download/import popups, and the install-dependencies footer use **`TitleBarOutlineButton`** with antialiased rounded strokes (same approach as the main window title bar), via **`styled_outline_button()`**. Legacy stylesheet **`QPushButton#closeBtn`** rules were removed from [`UI/theme.py`](UI/theme.py). **`FramelessDialog`** sets **`_frameless_close_button`** so the install-dependencies dialog can enable/disable the title **✕** while pip runs.
- **Docs**: [`README.md`](README.md), [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/config.md`](docs/reference/config.md).
- **Tests**: [`tests/ui/test_title_bar_outline_button.py`](tests/ui/test_title_bar_outline_button.py), [`tests/core/test_app_dirs.py`](tests/core/test_app_dirs.py) (`test_media_output_root_video_vs_photo`), [`tests/cli/test_config_and_settings.py`](tests/cli/test_config_and_settings.py) (`test_ui_settings_media_mode_roundtrip`), [`tests/runtime/test_import_smoke_api.py`](tests/runtime/test_import_smoke_api.py) (imports for `UI.frameless_dialog`, `UI.title_bar_outline_button`).

### Help / first-run tutorial
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): **`tutorial_completed`** in `ui_settings.json` — false until the user dismisses the first-run help.
- **UI** ([`UI/tutorial_dialog.py`](UI/tutorial_dialog.py), [`UI/main_window.py`](UI/main_window.py), [`UI/theme.py`](UI/theme.py)): title bar **?** next to **📈** opens a frameless **Help** dialog with a **topic list** (left) and **slide** pages (right) with **Previous** / **Next**; **Close** ends the session. **`QTimer`** (~1.8s) shows the same dialog once on first launch if `tutorial_completed` is false (after the optional HF token prompt). [`UI/main_window.py`](UI/main_window.py) **`_collect_settings_from_ui`** preserves **`tutorial_completed`**. **`TutorialDialog`** accepts **`start_topic_id`** / **`start_slide`** and **`go_to_topic()`** so callers can open on a specific topic/slide.
- **Help links in tooltips** ([`UI/tutorial_links.py`](UI/tutorial_links.py)): many tab hints use HTML tooltips with an **Open in Help →** link (`topic://…?slide=…`). A **`RichHelpTooltipFilter`** on **`QApplication`** shows a small **`QTextBrowser`** popup (native tooltips are not clickable) and opens Help at the right topic when the link is clicked. Wired on title bar **💾** / **📈** / **?**, Run, Topics, Video, Tasks, Library, Model, and Characters where hints map to tutorial topics.
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden imports **`UI.tutorial_dialog`**, **`UI.tutorial_links`**.
- **Docs / tests**: [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/config.md`](docs/reference/config.md), [`tests/cli/test_config_and_settings.py`](tests/cli/test_config_and_settings.py) (`test_ui_settings_tutorial_completed_roundtrip`), [`tests/runtime/test_import_smoke_api.py`](tests/runtime/test_import_smoke_api.py) (`test_import_ui_tutorial_links`).

### CPU parallelism (OpenMP, BLAS, PyTorch, Hub probes)
- **Runtime** ([`src/util/cpu_parallelism.py`](src/util/cpu_parallelism.py)): early **`configure_cpu_parallelism()`** sets **`OMP_NUM_THREADS`**, **`MKL_NUM_THREADS`**, **`OPENBLAS_NUM_THREADS`**, **`NUMEXPR_NUM_THREADS`**, **`VECLIB_MAXIMUM_THREADS`** when unset (default target **`min(32, os.cpu_count())`**; override with **`AQUADUCT_CPU_THREADS`**). This tunes **host CPU** threads for math libraries — not GPU multithreading. Called from [`main.py`](main.py), [`UI/ui_app.py`](UI/ui_app.py), and [`UI/app.py`](UI/app.py) before heavy imports.
- **PyTorch** ([`src/models/torch_dtypes.py`](src/models/torch_dtypes.py), [`src/content/brain.py`](src/content/brain.py)): after **`import torch`**, **`apply_torch_cpu_settings`** sets **`torch.set_num_threads`** from **`effective_cpu_thread_count()`** and **`torch.set_num_interop_threads`** from **`torch_interop_thread_count()`** — higher inter-op when **no CUDA/MPS** (more overlapping CPU-side ops), modest when an accelerator is present; optional override **`AQUADUCT_TORCH_INTEROP_THREADS`** (1–32).
- **UI** ([`UI/workers.py`](UI/workers.py)): **`ModelSizePingWorker`** probes Hugging Face repos with a **thread pool** (I/O-bound); **`ModelIntegrityVerifyWorker`** verifies multiple repos **in parallel** (capped for disk I/O).
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden import **`src.util.cpu_parallelism`**.
- **Docs / tests**: [`docs/pipeline/performance.md`](docs/pipeline/performance.md), [`docs/reference/config.md`](docs/reference/config.md), [`README.md`](README.md), [`tests/models/test_cpu_parallelism.py`](tests/models/test_cpu_parallelism.py).

### Library tab: browse past outputs
- **UI** ([`UI/tabs/library_tab.py`](UI/tabs/library_tab.py), [`UI/library_fs.py`](UI/library_fs.py), [`UI/main_window.py`](UI/main_window.py)): new **Library** tab lists **`videos/`** projects that contain **`final.mp4`** (title from `meta.json`, modified time, file size) and all **`runs/`** workspace folders (intermediate pipeline artifacts). Toolbar opens the **`videos/`** or **`runs/`** root; per-row actions open the project folder, **`assets/`**, or play **`final.mp4`**; double-click opens the folder. **Refresh** rescans disk; switching to the tab refreshes; pipeline **`_on_done`** refreshes after each run completes.
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden imports for **`UI.tabs.library_tab`**, **`UI.library_fs`**, **`UI.tab_sections`**.
- **Tests**: [`tests/core/test_library_fs.py`](tests/core/test_library_fs.py).

### Run / Video / Model tabs: section groups and spacing
- **UI** ([`UI/tab_sections.py`](UI/tab_sections.py)): shared **`section_title()`** and **`add_section_spacing()`** for consistent subsection labels and vertical gaps on the dark theme.
- **Run** ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py)): **Output**, **Script & content**, **Actions**.
- **Video** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py)): clearer breaks between platform template, **Output & timing**, **Quality / performance**, **Story pipeline (LLM)**, and **Advanced** (spacing replaces horizontal rules between major blocks).
- **Model** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py)): spacing after the download/install toolbar before the stack; spacing before **Model files location**; shared titles for model list and storage.

### Run tab: N videos = N independent pipeline tasks
- **UI** ([`UI/main_window.py`](UI/main_window.py)): **Videos to generate** no longer uses a single **Batch pipeline (N videos)** worker. Setting **N > 1** appends **N−1** jobs to the FIFO queue and starts the first **`PipelineWorker`** immediately — each completion adds its own Tasks row and the next queued run starts ([`UI/workers.py`](UI/workers.py): removed **`PipelineBatchWorker`**).
- **Queue while busy**: one click with **N = 3** appends **three** separate queue entries (not one entry with quantity 3).
- **Tasks table**: each **FIFO-queued** pipeline job has its own row (**Queued pipeline run**, **Waiting in queue…**) under the active run so **`Tasks (n)`** matches visible pipeline work ([`UI/main_window.py`](UI/main_window.py) `_tasks_refresh`).
- **Docs / tests**: [`docs/ui/ui.md`](docs/ui/ui.md), [`tests/ui/test_ui_main_window.py`](tests/ui/test_ui_main_window.py), [`tests/runtime/test_pipeline_run_queue_contract.py`](tests/runtime/test_pipeline_run_queue_contract.py), [`UI/tabs/run_tab.py`](UI/tabs/run_tab.py) tooltip.

### Diffusion: automatic CPU offload (VRAM vs system RAM)
- **Placement** ([`src/util/diffusion_placement.py`](src/util/diffusion_placement.py)): shared **`place_diffusion_pipeline()`** for local **image** ([`src/render/artist.py`](src/render/artist.py)) and **video** ([`src/render/clips.py`](src/render/clips.py)) diffusers loads — **`enable_model_cpu_offload()`** / **`enable_sequential_cpu_offload()`** vs full **`cuda`** based on **detected GPU VRAM** and **available system RAM** (`psutil`), not OS disk swap.
- **Auto policy** (override with **`AQUADUCT_DIFFUSION_CPU_OFFLOAD`**: `auto` \| `off` \| `model` \| `sequential`; legacy **`AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD=1`** still forces sequential when unset/`auto`): favors full GPU when VRAM is ample and host RAM is free; uses **model** offload for mid VRAM (~8–12 GB); **sequential** when VRAM is tight or unknown; if **free RAM &lt; ~3 GB** but **VRAM ≥ ~8 GB**, prefers **full GPU** to avoid extra CPU staging.
- **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): **total system RAM** falls back to **`psutil`** when the Windows-specific probe is unavailable (Linux/macOS).
- **Tests**: [`tests/models/test_diffusion_placement.py`](tests/models/test_diffusion_placement.py).

### Pro mode: multi-scene video + image-to-video (SVD)
- **Pipeline** ([`main.py`](main.py)): when **Pro** is on, **slideshow off**, and the **Video** model id is **img2vid** (e.g. `stabilityai/stable-video-diffusion-img2vid-xt` or ids containing **`img2vid`**), the app **generates one keyframe per scene** with the **Image** model, then runs **img2vid** on those paths — same idea as motion mode without Pro. **Text-to-video** models (e.g. ZeroScope) still use **`init_images=None`**. Scene prompts honor **`video_format`**: **news** anchors with the headline; **cartoon** / **unhinged** omit the title prefix ([`_split_into_pro_scenes_from_script`](main.py)); [`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py) passes **`video_format`** consistently.
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py)): **no longer blocks** Pro + SVD; **slideshow + Pro + SVD** falls back to **still frames from the Image model** (the frame-stacking Pro path cannot drive SVD clip-by-clip).
- **UI** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py)): Pro checkbox label/tooltip describe **text-to-video** vs **image model → img2vid**.
- **Tests**: [`tests/render/test_pro_img2vid_mock_run.py`](tests/render/test_pro_img2vid_mock_run.py), [`tests/runtime/test_preflight.py`](tests/runtime/test_preflight.py).

### Resource usage window (title bar 📈)
- **UI** ([`UI/resource_graph_dialog.py`](UI/resource_graph_dialog.py)): removed the long explanatory block; live CPU/RAM/GPU lines stay compact; sparkline axis labels unchanged.

### Misc
- **Run id** ([`main.py`](main.py)): **`_now_run_id()`** uses **timezone-aware** UTC (`datetime.now(timezone.utc)`) instead of deprecated **`utcnow()`**.

### Model storage (default vs external), pipeline resolution, and offsite downloads
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `models_storage_mode` (`default` \| `external`), `models_external_path` — **Default** uses **`.Aquaduct_data/models`**; **External** uses an absolute folder for Hub snapshots (created when valid).
- **Runtime** ([`src/core/models_dir.py`](src/core/models_dir.py)): `models_dir_for_app()`, `get_models_dir()` (pipeline override during local `run_once`), `set_pipeline_models_dir` / `clear_pipeline_models_dir` in a **`finally`** block in [`main.py`](main.py) so inference always resolves the active folder.
- **Loaders** ([`src/render/clips.py`](src/render/clips.py), [`src/render/artist.py`](src/render/artist.py), [`src/content/brain.py`](src/content/brain.py), [`src/content/factcheck.py`](src/content/factcheck.py)): `resolve_pretrained_load_path` uses **`get_models_dir()`** during runs.
- **UI** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`UI/models_storage_toggle.py`](UI/models_storage_toggle.py), [`UI/main_window.py`](UI/main_window.py)): **Model** tab (local mode) — **Model files location**: **Default \| External**, path field, **Browse…**, **Apply**, **Detect**; downloads / disk badges / verify use **`effective_models_dir()`** from collected settings. **Clear data** does not delete an external models tree (tooltip).
- **CLI** ([`src/cli/main.py`](src/cli/main.py)): `models list` / `models download` use **`models_dir_for_app(load_settings())`** so CLI matches saved storage mode.
- **Offsite bundle** ([`Model-Downloads/generate_offsite_bundle.py`](Model-Downloads/generate_offsite_bundle.py), [`Model-Downloads/README.md`](Model-Downloads/README.md)): generates a **standalone** `offsite/` folder (gitignored) with embedded **`HF_TOKEN`** from the current env and the full curated repo list — copy to another PC, `pip install -r requirements-offsite.txt`, run `download_all_models.py`, then copy `models/` back. Root [`.gitignore`](.gitignore) ignores `Model-Downloads/*` except the generator + README.
- **Orchestrator** ([`main.py`](main.py)): routes **`python main.py <subcommand>`** to [`src/cli/main.py`](src/cli/main.py); legacy **`--cli`** loop reloads **`load_settings()`** each iteration and applies HF token helper; **`--music`** uses **`dataclasses.replace`** on loaded settings.

### Topics tab: Discover, creative extraction, and topic research pack
- **Discover vs pipeline** ([`src/content/crawler.py`](src/content/crawler.py), [`UI/workers.py`](UI/workers.py)): `fetch_latest_items(..., topic_discover_only=True)` is used only from **Topics → Discover** so **Cartoon** / **Unhinged** skip Google News RSS there; **runs**, **storyboard**, and **`get_scored_items`** keep the default so RSS + MarkTechPost can still backfill when Firecrawl returns nothing (fixes empty storyboard / preset fetches).
- **Topic phrases from Firecrawl titles** ([`src/content/topic_discovery.py`](src/content/topic_discovery.py)): lowercase / meme-style phrase extraction plus **fallback to full page titles** when token heuristics yield nothing (Discover no longer dies on all-lowercase headlines).
- **Firecrawl search preview images** ([`src/content/firecrawl_news.py`](src/content/firecrawl_news.py), [`NewsItem`](src/content/crawler.py)): optional `image_url` from v2 search row metadata; passed into script `sources` when present.
- **Topic research pack** ([`src/content/topic_research_assets.py`](src/content/topic_research_assets.py)): after **Cartoon** / **Unhinged** Discover, writes **`data/topic_research/<mode>/manifest.json`** and **`images/`** (download preview URLs or best-effort **`og:image`** for a few pages). **`topic_research_digest_for_script()`** feeds the latest manifest into **`build_script_context`** `extra_markdown` from [`main.py`](main.py) and [`UI/workers.py`](UI/workers.py) (Preview/Storyboard) for script inference when story web context / reference images / article scrape material is assembled.
- **Discover UX** ([`UI/tabs/topics_tab.py`](UI/tabs/topics_tab.py), [`UI/main_window.py`](UI/main_window.py)): mode-aware dialogs (creative seeds vs headlines), Firecrawl-required messaging for creative Discover, higher fetch limit (24), log line to the topic research folder.
- **Tests**: [`tests/discover/test_firecrawl_crawler.py`](tests/discover/test_firecrawl_crawler.py) (Discover vs pipeline RSS), [`tests/discover/test_topic_discovery.py`](tests/discover/test_topic_discovery.py), [`tests/content/test_topic_research_assets.py`](tests/content/test_topic_research_assets.py).

### Windows EXE build, tests, and operator docs
- **PyInstaller spec** ([`aquaduct-ui.spec`](aquaduct-ui.spec)): portable `SPECPATH` + `docs/**/*.md` (recursive) glob (no machine-absolute paths); `pathex` set to repo root; explicit `hiddenimports` aligned with current packages (`src.speech.elevenlabs_tts`, `src.content.characters_store`, `UI.no_wheel_controls`, `UI.model_execution_toggle`, `UI.api_model_widgets`, tab modules, `src.runtime.pipeline_api`, `src.runtime.generation_facade`).
- **Build script** ([`build/build.ps1`](build/build.ps1)): same hidden-import belt-and-suspenders as the spec; **`-UseSpec`** to build via the spec; post-build **`scripts/frozen_smoke.py`** for UI and spec builds; **`$LASTEXITCODE`** check after PyInstaller.
- **Frozen import smoke** ([`UI/ui_app.py`](UI/ui_app.py), [`scripts/frozen_smoke.py`](scripts/frozen_smoke.py)): env **`AQUADUCT_IMPORT_SMOKE=1`** runs headless imports and exits before Qt when validating a built EXE.
- **Build docs** ([`build/README.md`](build/README.md)): verification checklist, `-debug` / `--debug`, `-UseSpec`, smoke commands, corrected module names in packaging notes.
- **Tests** ([`pytest.ini`](pytest.ini), [`tests/runtime/test_import_smoke_api.py`](tests/runtime/test_import_smoke_api.py)): documented **`qt`** / **`slow`** markers; import smoke for API pipeline modules and `UI.api_model_widgets`.
- **Docs**: new [`docs/build/building_windows_exe.md`](docs/build/building_windows_exe.md) (build/verify/troubleshoot) and [`docs/pipeline/performance.md`](docs/pipeline/performance.md) (import-time `cProfile` notes); cross-links in [`README.md`](README.md) (table of contents + **Docs**), [`docs/pipeline/main.md`](docs/pipeline/main.md), [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/integrations/api_generation.md`](docs/integrations/api_generation.md); test tier table in [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Desktop UI
- **Tasks tab badge** ([`UI/tabs/tasks_tab.py`](UI/tabs/tasks_tab.py), [`UI/main_window.py`](UI/main_window.py)): tab text shows **`Tasks (n)`** while pipeline/preview/storyboard work, queued runs, or TikTok/YouTube uploads are active (`n` is zero when idle). Docs: [`docs/ui/ui.md`](docs/ui/ui.md).
- **Run while busy** ([`UI/main_window.py`](UI/main_window.py)): removed disabling the **Run** button when a pipeline starts; **Run** is re-enabled immediately after the worker thread starts so additional clicks **enqueue** FIFO runs (matches docs: queue while a job is active).
- **Topics → Discover**: see **Topics tab: Discover, creative extraction, and topic research pack** above for crawler flags, Firecrawl-only creative Discover vs pipeline RSS fallback, UI copy, and saved research under `data/topic_research/`. Docs: [`docs/integrations/crawler.md`](docs/integrations/crawler.md), [`docs/ui/ui.md`](docs/ui/ui.md).
- **Wheel guard** ([`UI/no_wheel_controls.py`](UI/no_wheel_controls.py)): all main-window combo boxes and numeric spins use subclasses that **ignore the mouse wheel**, so scrolling a tab or scroll area does not accidentally change a setting. Values still change via click, keyboard, or the spin up/down buttons.

### Local vs API model execution
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `model_execution_mode` (`local` \| `api`), nested `api_models` per role, `api_openai_key`, `api_replicate_token`; env `OPENAI_API_KEY`, `REPLICATE_API_TOKEN` override saved keys.
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py), [`src/runtime/model_backend.py`](src/runtime/model_backend.py)): API mode validates providers/keys and Pro + Replicate rules; skips requiring torch/diffusers for API-only runs.
- **Pipeline** ([`main.py`](main.py), [`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py), [`src/content/brain_api.py`](src/content/brain_api.py), [`src/runtime/api_generation.py`](src/runtime/api_generation.py), [`src/platform/openai_client.py`](src/platform/openai_client.py), [`src/platform/replicate_client.py`](src/platform/replicate_client.py)): OpenAI script JSON, DALL·E / Replicate stills, OpenAI TTS or local/ElevenLabs voice, slideshow assembly; Pro uses Replicate MP4 segments when configured.
- **Generation facade** ([`src/runtime/generation_facade.py`](src/runtime/generation_facade.py)): local vs API script generation routes through `get_generation_facade` from [`main.py`](main.py) and [`pipeline_api.py`](src/runtime/pipeline_api.py).
- **UI** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`UI/model_execution_toggle.py`](UI/model_execution_toggle.py), [`UI/tabs/api_tab.py`](UI/tabs/api_tab.py), [`UI/api_model_widgets.py`](UI/api_model_widgets.py), [`UI/main_window.py`](UI/main_window.py)): Model tab **Local | API** segmented toggle; **Generation APIs** on the Model tab in API mode live in a **scroll area** with a taller default window height; panel reparents between API and Model tabs; gather/save wiring.
- **Workers** ([`UI/workers.py`](UI/workers.py), [`UI/brain_expand.py`](UI/brain_expand.py)): Preview/storyboard/brain-expand use API LLM/images when mode is API.
- **Characters** ([`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py), [`generate_character_from_preset_openai`](src/content/brain_api.py)): **Generate with LLM** and **portrait** use OpenAI / configured Image API in API mode instead of local HF weights.
- **HTTP**: limited retries with backoff on transient OpenAI and Replicate create errors ([`src/platform/openai_client.py`](src/platform/openai_client.py), [`src/platform/replicate_client.py`](src/platform/replicate_client.py)); [`api_role_ready`](src/runtime/model_backend.py) / [`resolve_local_vs_api`](src/runtime/model_backend.py) helpers for routing checks.
- **API LLM providers**: **Generation APIs** LLM dropdown adds OpenAI-compatible hosts (Groq, Together, Mistral, OpenRouter, DeepSeek, xAI, Fireworks, Cerebras, Nebius) with default base URLs and env-specific API keys ([`src/settings/api_model_catalog.py`](src/settings/api_model_catalog.py), [`src/runtime/model_backend.py`](src/runtime/model_backend.py) `effective_llm_api_key`, [`src/platform/openai_client.py`](src/platform/openai_client.py), [`UI/api_model_widgets.py`](UI/api_model_widgets.py), [`UI/main_window.py`](UI/main_window.py)).
- **Docs**: [`docs/integrations/api_generation.md`](docs/integrations/api_generation.md); [`docs/reference/config.md`](docs/reference/config.md) (`AppSettings` API fields).
- **Tests**: [`tests/models/test_model_backend.py`](tests/models/test_model_backend.py), [`tests/runtime/test_api_generation.py`](tests/runtime/test_api_generation.py), [`tests/platform/test_replicate_client.py`](tests/platform/test_replicate_client.py), [`tests/content/test_brain_api.py`](tests/content/test_brain_api.py), [`tests/runtime/test_api_model_catalog.py`](tests/runtime/test_api_model_catalog.py), [`tests/runtime/test_generation_facade.py`](tests/runtime/test_generation_facade.py), [`tests/models/test_model_execution_toggle.py`](tests/models/test_model_execution_toggle.py), [`tests/ui/test_ui_model_execution_mode.py`](tests/ui/test_ui_model_execution_mode.py) (skips if PyQt6 absent), [`tests/runtime/test_preflight.py`](tests/runtime/test_preflight.py) (local explicit vs default), plus [`tests/ui/test_ui_settings_api_models.py`](tests/ui/test_ui_settings_api_models.py), [`tests/platform/test_openai_client.py`](tests/platform/test_openai_client.py), [`tests/content/test_story_context.py`](tests/content/test_story_context.py) (meme-forward Firecrawl queries for cartoon/unhinged), [`tests/discover/test_firecrawl_crawler.py`](tests/discover/test_firecrawl_crawler.py) / [`tests/discover/test_crawler_seen_modes.py`](tests/discover/test_crawler_seen_modes.py) (Discover headline vs creative modes).

### Automatic cast when no Character is selected
- **Fallback + LLM cast** ([`src/content/characters_store.py`](src/content/characters_store.py), [`src/content/brain.py`](src/content/brain.py)): format-aware default cast (e.g. news-style narrator vs multi-voice cartoon), optional **`generate_cast_from_storyline_llm`** aligned to the storyline, and ephemeral **`Character`** shaping for diffusion when no saved character is active. Cast JSON may be written to each video’s **`assets/generated_cast.json`** from the storyboard / pipeline path ([`UI/workers.py`](UI/workers.py), [`main.py`](main.py)).
- **Tests**: [`tests/content/test_generated_cast.py`](tests/content/test_generated_cast.py); [`tests/content/test_characters_store.py`](tests/content/test_characters_store.py) updated.

### UI copy, preflight, and progress: “scenes” (not “clips”)
- User-facing **Video** / **Model** tab labels, **preflight** errors, and **run progress** strings use **scene(s)** / **motion mode** instead of **clip(s)** / **clip mode** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py), [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`src/runtime/preflight.py`](src/runtime/preflight.py), [`main.py`](main.py)). Persisted setting keys (`clips_per_video`, `clip_seconds`, …) and asset folder names (`clips`, `pro_clips`) are unchanged for compatibility.
- **Docs** ([`README.md`](README.md), [`docs/ui/ui.md`](docs/ui/ui.md), [`docs/pipeline/editor.md`](docs/pipeline/editor.md), [`docs/reference/config.md`](docs/reference/config.md), [`docs/reference/models.md`](docs/reference/models.md), [`docs/pipeline/main.md`](docs/pipeline/main.md)) updated to match.

### Story pipeline: multi-stage script + web context + reference images
- **Video settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): new toggles under `VideoSettings`:
  - `story_multistage_enabled`: run format-specific multi-pass script refinement (beat structure, safety, length, clarity; comedy modes focus dialogue/pacing/punchline).
  - `story_web_context`: optional Firecrawl search/scrape digest for extra context (saved under `runs/.../assets/script_context/web_digest.md`).
  - `story_reference_images`: optionally download a few images from scraped pages and use the first as an **img2img** init for the first generated frame (when supported).
- **Pipeline wiring** ([`main.py`](main.py), [`UI/workers.py`](UI/workers.py)): context gathering + refinement run before storyboard/image generation; storyboard preview path uses cache-backed context.
- **Meme-forward web context (cartoon / unhinged)** ([`src/content/story_context.py`](src/content/story_context.py)): when **Gather web context** / **reference images** run, Firecrawl searches bias toward **memes, viral, templates**; two **supplement** searches merge extra results; up to **4** pages scraped and up to **5** reference images saved for diffusion img2img (vs 2 / 3 for other formats). [`UI/tabs/video_tab.py`](UI/tabs/video_tab.py) tooltips updated; tests: [`tests/content/test_story_context.py`](tests/content/test_story_context.py).
- **Diffusion** ([`src/render/artist.py`](src/render/artist.py)): `generate_images` accepts `external_reference_image` + `external_reference_strength` and uses it for first-frame init (style chain and non-chain).

### Source layout (Python packages)
- Flat `src/*.py` modules are reorganized into packages: **`src/core/`** (config, paths, app dirs), **`src/content/`** (brain, crawler, storyboard, topics, …), **`src/render/`** (artist, editor, captions, clips, ffmpeg slideshow, …), **`src/runtime/`** (preflight, pipeline control), **`src/settings/`** (UI settings, video/effects/art-style presets), **`src/speech/`** (voice, TTS, audio FX), **`src/platform/`** (upload tasks, TikTok/YouTube), **`src/util/`** (ffmpeg, VRAM, CLI helpers), and **`src/models/`** (HF access, model manager, hardware, torch install, pillow compat). Imports and tests updated throughout; legacy one-file paths removed.
- **Docs**: cross-references under `docs/` and file links in this changelog’s **Unreleased** / historical entries now use the package paths above (no stale `src/brain.py`-style links).

### Video: Pro mode (text-to-video vs slideshow frame sequence)
- **Settings** ([`src/core/config.py`](src/core/config.py)): `VideoSettings.pro_mode`, `pro_clip_seconds`, plus existing motion fields (`clips_per_video`, `clip_seconds`, …). Persisted in [`src/settings/ui_settings.py`](src/settings/ui_settings.py).
- **Primary Pro path** ([`main.py`](main.py)): when **`pro_mode`** is on and **slideshow is off** (the default from the desktop UI), the script is split into **scene** prompts (**`assets/pro_prompt.txt`**). **Text-to-video** Video models (e.g. ZeroScope) generate segments directly; **img2vid** models (e.g. Stable Video Diffusion) first render **keyframes** with the **Image** model under **`assets/pro_keyframes/`**, then run **img2vid** clips into **`assets/pro_clips/`**. Narration is stretched to the combined segment duration; concatenation via **`assemble_generated_clips_then_concat`**. Short prompts + caps avoid **CLIP** token overflow on tight text encoders ([`src/render/clips.py`](src/render/clips.py)).
- **Legacy path**: if **`use_image_slideshow`** and **`pro_mode`** are both true (e.g. hand-edited settings), the older **one diffusion still per output frame** path still runs: **`round(pro_clip_seconds × fps)`** images with the SDXL **reference chain**, optional manifest key **`pro_generated_frames`**, final **`assemble_pro_frame_sequence_then_concat`** ([`src/render/editor.py`](src/render/editor.py); cap **`AQUADUCT_PRO_MAX_FRAMES`** via `pro_mode_frame_count`).
- **UI** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py)): Pro mode **unchecks and disables** slideshow; **Images per video** stays hidden while Pro is on; labels describe **scene** length and **text-to-video** vs **image → img2vid**.
- **Platform preset**: **`pro_shortform_60fps`** tile ([`src/settings/video_platform_presets.py`](src/settings/video_platform_presets.py)); `find_best_preset_for_video` matches `pro_mode` / `pro_clip_seconds`.
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py)): Pro requires slideshow off, a configured **Video** model id, and positive **`pro_clip_seconds`**; motion mode validates **scenes per video** / **seconds per scene** when slideshow is off. Legacy slideshow + Pro still uses frame-count warnings where applicable.
- **Tests**: [`tests/render/test_pro_mode_frames.py`](tests/render/test_pro_mode_frames.py); [`tests/runtime/test_preflight.py`](tests/runtime/test_preflight.py) and settings / preset tests extended for the rules above.

### Model tab: VRAM / size labels (encoding)
- UI strings for approximate VRAM and disk placeholders use **ASCII-safe** text in [`src/models/model_manager.py`](src/models/model_manager.py) and [`src/models/hardware.py`](src/models/hardware.py) (fixes mojibake like `Ôëê` / `ÔÇô` on Windows). [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py) paired-model size hint aligned.

### Run queue: Preview / Storyboard busy
- **Run** (and approve-run paths) enqueue when **`PipelineWorker`**, **`PreviewWorker`**, or **`StoryboardWorker`** is active via **`_pipeline_run_should_queue()`** ([`UI/main_window.py`](UI/main_window.py)). **`_try_start_next_queued_pipeline`** waits until none of those are busy. After preview/storyboard dialogs close (or fail/cancel), the next queued pipeline job can start.

### Characters tab: LLM auto presets
- **Preset** dropdown + **Generate with LLM** fills **name**, **identity**, **visual style**, **negatives**, and **use project default voice** from the script model using built-in archetypes ([`src/content/character_presets.py`](src/content/character_presets.py), [`generate_character_from_preset_llm`](src/content/brain.py), [`CharacterGenerateWorker`](UI/workers.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)). Optional one-line **extra notes** biases the run. Docs: [`docs/ui/characters.md`](docs/ui/characters.md).

### Brain / Model tab: same script LLM as the combo
- **`resolve_llm_model_id()`** ([`UI/brain_expand.py`](UI/brain_expand.py)) prefers the **Model** tab **`Script (LLM)`** combo’s **`currentData()`**, then saved `llm_model_id`, then the default from [`get_models()`](src/core/config.py). Character generation and **🧠** field expansion no longer use a stale saved id when the combo was changed but **Save** was not clicked — avoiding surprise Hub downloads for a different repo.

### Hugging Face: workers + gated-model errors
- **[`src/models/hf_access.py`](src/models/hf_access.py)**: **`ensure_hf_token_in_env`** applies the saved API token to **`HF_TOKEN`** / **`HUGGINGFACEHUB_API_TOKEN`** inside **`TextExpandWorker`** and **`CharacterGenerateWorker`** when the process env was empty (same rules as the main window: Hugging Face API enabled + token). **`humanize_hf_hub_error`** maps 401 / gated-repo failures to a short dialog instead of a full traceback.
- Workers receive **`hf_token`** / **`hf_api_enabled`** from settings ([`UI/workers.py`](UI/workers.py), [`UI/brain_expand.py`](UI/brain_expand.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)).

### Editor / MoviePy: Pillow 10+ and RGBA compositing
- **[`src/models/pillow_compat.py`](src/models/pillow_compat.py)**: Pillow removed **`Image.ANTIALIAS`**; older MoviePy still references it in **`resize`** — compat shim runs before MoviePy import in [`src/render/editor.py`](src/render/editor.py).
- **CompositeVideoClip** could raise **`operands could not be broadcast`** when mixing **RGB** base frames with **RGBA** caption overlays — **`_ensure_rgba_np`** pads an opaque alpha channel on base image/video clips and watermarks before compositing ([`src/render/editor.py`](src/render/editor.py)).
- **`.gitignore`**: ignore MoviePy temp files (`*TEMP_MPY*.mp4`).

### Model load path: project snapshot vs Hugging Face cache
- **`resolve_pretrained_load_path`** ([`src/models/model_manager.py`](src/models/model_manager.py)) no longer points `from_pretrained` at an **empty or stub** folder under `models/` (which caused extra Hub traffic). It requires the same **minimum on-disk size** as **`model_has_local_snapshot`**. If the project copy is missing or too small, it next uses **`snapshot_download(..., local_files_only=True)`** so a **full** snapshot already in the default Hugging Face cache (e.g. downloaded outside Aquaduct) is loaded by path instead of treating the repo id as a fresh remote pull. Docs: [`docs/reference/models.md`](docs/reference/models.md).

### Tests
- Removed **[`tests/test_torch_install.py`](tests/test_torch_install.py)** (fragile / slow environment-specific assertions).
- Added [`tests/content/test_character_presets.py`](tests/content/test_character_presets.py), [`tests/models/test_hf_access.py`](tests/models/test_hf_access.py).

### Video formats: topic sourcing + voice by mode
- **News** and **Explainer** now share the **same** headline search bias (AI / product releases) and the same short-form script defaults; Explainer no longer uses a separate “tutorial / science education” RSS query (`src/content/crawler.py`, `video_format_uses_news_style_sourcing()` in [`src/content/topics.py`](src/content/topics.py)).
- **Cartoon** headline queries bias toward **new animation / streaming / premiere / trailer / buzz**; brain prompts stress **not** a tutorial or how-to (`src/content/brain.py`).
- **Unhinged** queries bias toward **viral / meme / internet-culture** seeds; unhinged prompt copy notes trend satire (`src/content/crawler.py`, `src/content/brain.py`). Docs: [`docs/integrations/crawler.md`](docs/integrations/crawler.md).

### Key facts card: News & Explainer only
- The on-screen **Key facts** card (from article text) is **not** rendered for **Cartoon** or **Cartoon (unhinged)** pipeline modes — only **News** and **Explainer** (`video_format`). [`video_format_supports_facts_card()`](src/core/config.py); [`assemble_microclips_then_concat` / `assemble_generated_clips_then_concat`](src/render/editor.py) take `video_format=` from [`main.py`](main.py). **Captions** tab includes a short note.

### Video tab: platform presets (tiles) + social templates
- **Platform template** at the top of **Video** uses **selectable tiles** (game-style preset cards): one tile per curated social profile (short-form vertical HD/720p, Instagram/Facebook square and 4:5, Pinterest 2:3, YouTube/LinkedIn 1080p, landscape 720p, etc.) plus **Custom** for full manual control. Definitions live in [`src/settings/video_platform_presets.py`](src/settings/video_platform_presets.py). Clicking a tile applies **resolution**, **FPS**, **micro-scene min/max**, **images per video**, **bitrate**, **scenes per video** (`clips_per_video`), and **seconds per scene** (`clip_seconds`). The selection is stored as **`video.platform_preset_id`** in [`ui_settings.json`](src/settings/ui_settings.py) and surfaced in [`UI/main_window.py`](UI/main_window.py) as **`_video_platform_preset_id`**. Editing any of those fields switches the UI to **Custom**.
- **Resolution** dropdown (formerly labeled “Video format”) lists all template sizes from the same module.

### Image generation: NSFW option + quality-regenerate fix
- **Allow NSFW image output** on **Video** ([`AppSettings.allow_nsfw`](src/core/config.py)): clears the diffusion **safety checker** / **feature extractor** after load so models such as SD 1.5 do not return black frames when the classifier flags content ([`src/render/artist.py`](src/render/artist.py)). Persisted in UI settings; passed through [`main.py`](main.py) and [`UI/workers.py`](UI/workers.py).
- **Quality retries** for slideshow/keyframes used to call `generate_images(..., max_images=1)`, which always wrote `img_001.png`, then [`apply_regenerated_image`](src/render/artist.py) deleted that source after copying—wiping **earlier** slides when regenerating a **later** index. Retries now use a **temporary output directory** before copying to the real path ([`main.py`](main.py)).

### Model tab: Install dependencies (progress dialog)
- **Install dependencies** opens a frameless **Installing dependencies** dialog with **step labels** (PyTorch vs `requirements.txt`), a **progress bar** (**indeterminate** until pip prints tqdm-style `%` lines, then **0–100%** from parsed output), a **current action** line from `pip_line_hint` (Collecting / Downloading / Installing…), and a **scrolling log**. Close is disabled until the run finishes. Streaming uses [`src/models/torch_install.py`](src/models/torch_install.py): `run_subprocess_streaming` splits on `\r` and `\n` so same-line pip progress is visible; `pip install` invocations inject `--progress-bar on`; `pip_download_percent` maps lines to the bar. Implementation: [`UI/install_deps_dialog.py`](UI/install_deps_dialog.py).

### PyTorch dtype helper (LLM expand / transformers)
- **`src/models/torch_dtypes.py`**: central `torch_float16()` for BitsAndBytes / `from_pretrained` dtypes. If `import torch` is a **broken or stub** install (no `torch.float16`), raises a clear `RuntimeError` pointing to `scripts/install_pytorch.py --with-rest` instead of `AttributeError: module 'torch' has no attribute 'float16'`. Used from [`src/content/brain.py`](src/content/brain.py), [`src/content/factcheck.py`](src/content/factcheck.py), [`src/render/artist.py`](src/render/artist.py), [`src/render/clips.py`](src/render/clips.py). Tests: [`tests/models/test_torch_dtypes.py`](tests/models/test_torch_dtypes.py).

### Model tab: download all voice models
- **Download ▾ → Download all voice models** queues Hugging Face snapshots for every curated TTS option (Kokoro, MMS-TTS, MeloTTS, Microsoft SpeechT5, Parler-TTS, XTTS, Bark, …), skipping repos already under `models/`. Implementation: [`UI/main_window.py`](UI/main_window.py) (`_download_all_voice_models`), [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py). Docs: [`docs/reference/models.md`](docs/reference/models.md), [`docs/ui/ui.md`](docs/ui/ui.md).

### Model tab: Auto-fit for this PC
- **Auto-fit for this PC** on the **Model** tab picks script / video / voice models from detected VRAM and RAM using `rank_models_for_auto_fit` in [`src/models/hardware.py`](src/models/hardware.py) (same rules as fit badges; SDXL Turbo is preferred over SD 1.5 when VRAM ≥ ~8 GB and Turbo is still OK). Skips disabled Hub rows; logs the selection and **saves settings**. Docs: [`docs/ui/ui.md`](docs/ui/ui.md). Tests: [`tests/models/test_auto_fit.py`](tests/models/test_auto_fit.py).

### Resource usage graph (fix)
- **Resource usage** (title bar 📈) sparklines crashed after the first second of data: `QBrush` was used for the area fill but not imported from `PyQt6.QtGui` ([`UI/resource_graph_dialog.py`](UI/resource_graph_dialog.py)).
- Timer updates (`_on_tick`) are wrapped in **try/except** so a bad sample tick does not tear down the main window.

### Terminal: activate venv (Windows)
- **[`scripts/setup_terminal_env.ps1`](scripts/setup_terminal_env.ps1)**: dot-source from the repo root (`. .\scripts\setup_terminal_env.ps1`) to **activate `.venv`** and `cd` to the project. Documents optional **`HF_TOKEN`** / Hub usage. See [`README.md`](README.md) and [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Voice models (download list)
- **Settings → Model → Voice** includes more Hugging Face TTS checkpoints for local snapshot download: **MMS-TTS English**, **MeloTTS English**, **SpeechT5**, **Parler-TTS mini v1**, and **Bark**, alongside existing **Kokoro 82M** and **coqui XTTS v2**. Same repos are listed in [`scripts/download_hf_models.py`](scripts/download_hf_models.py) `ALL_REPOS`. VRAM hints for **Bark** / **Parler** in [`src/models/hardware.py`](src/models/hardware.py). Docs: [`docs/reference/models.md`](docs/reference/models.md), [`docs/pipeline/voice.md`](docs/pipeline/voice.md), [`docs/build/model_youtube_demos.md`](docs/build/model_youtube_demos.md).

### Run tab: queue multiple pipeline jobs
- While a **pipeline** or **batch** run is active, clicking **Run** again **appends** another job to a FIFO queue (snapshot of settings + batch quantity at click time) instead of being ignored. Same for **Approve and run** (preview) and **approved storyboard render** when a pipeline is already running.
- When the current run **finishes** or **fails**, the next queued job starts after preflight (and FFmpeg readiness). **Stop** cancels the active run and **clears** any queued jobs, with a log line counting dropped items.
- Implementation: [`UI/main_window.py`](UI/main_window.py) (`_pipeline_run_queue`, `_try_start_next_queued_pipeline`, `_attach_and_start_pipeline_worker`). Docs: [`README.md`](README.md), [`docs/ui/ui.md`](docs/ui/ui.md). Tests: [`tests/ui/test_ui_main_window.py`](tests/ui/test_ui_main_window.py) (Qt), [`tests/runtime/test_pipeline_run_queue_contract.py`](tests/runtime/test_pipeline_run_queue_contract.py) (no Qt — queue payload shapes).

### Resource graph (title bar)
- Title bar **📈** between **💾 Save** and **✕**: opens a non-modal **Resource usage** window with sparkline graphs (this process CPU, RAM % of system, GPU VRAM % when CUDA is active), **1 second** refresh ([`src/util/resource_sample.py`](src/util/resource_sample.py), [`UI/resource_graph_dialog.py`](UI/resource_graph_dialog.py)). **`psutil`** is a runtime dependency.

### PyTorch install (auto CUDA / CPU)
- **`requirements.txt`**: single runtime list **without** `torch` (so CUDA wheels are not skipped). Consolidated former `requirements-base.txt` into this file.
- **[`src/models/torch_install.py`](src/models/torch_install.py)** + **[`scripts/install_pytorch.py`](scripts/install_pytorch.py)**: detect NVIDIA via `nvidia-smi` / WMI (Windows), install **`torch` / `torchvision` / `torchaudio`** from **CUDA 12.4** wheels when appropriate, else **CPU** wheels; **macOS** uses default PyPI. **`--with-rest`** runs `pip install -r requirements.txt` afterward. Replaces a CPU-only `torch` when a GPU is present (`pip uninstall` + reinstall).
- **Model tab** “Install dependencies” calls the same combined install ([`UI/main_window.py`](UI/main_window.py)). **[`build/build.ps1`](build/build.ps1)** and **[`scripts/setup_venv_one_by_one.ps1`](scripts/setup_venv_one_by_one.ps1)** use `install_pytorch.py --with-rest`. Docs: [`README.md`](README.md), [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Video format: Cartoon (unhinged)
- **Pipeline mode** `video_format="unhinged"` (fourth option with News / Cartoon / Explainer): chaotic Gen‑Z–style cartoon comedy scripts, headline/query bias for comedy/absurdist animation topics (see [`src/content/crawler.py`](src/content/crawler.py)), and LLM steering via [`src/content/brain.py`](src/content/brain.py) (`_vf_hint`, dedicated unhinged prompt path).
- **TTS** ([`main.py`](main.py), [`src/speech/voice.py`](src/speech/voice.py)): with **local** pyttsx3 only, narration is split into beats (hook → segment narrations → CTA); each beat uses a **rotating** system voice (round-robin, max **12** distinct voices), segment WAVs are **concatenated** to `assets/voice.wav`, and word timestamps are **merged** in `captions.json`. If the active **character** turns off default voice (custom voice) or uses **ElevenLabs**, the pipeline keeps a **single** `synthesize()` pass for the full narration (no rotation).

### Frameless dialogs (match main window)
- **Alerts and modal popups** use a shared borderless shell ([`UI/frameless_dialog.py`](UI/frameless_dialog.py)): custom title bar, **✕** close button (`#closeBtn`), drag by title bar only, rounded panel via `QDialog#FramelessDialogShell` in [`UI/theme.py`](UI/theme.py).
- Replaces native **`QMessageBox`** across the app (main window, Characters, brain expand, etc.). **Hugging Face token** prompt, **Preview** / **Storyboard Preview** dialogs, and **Topics → Discover** pickers use **`FramelessDialog`** or helpers (`aquaduct_information`, `aquaduct_warning`, `aquaduct_question`, `aquaduct_message_with_details`, `show_hf_token_dialog`). **Native file pickers** (`QFileDialog`) unchanged.
- **Tests**: existing UI tests unchanged; run `pytest tests/ui/test_ui_workers.py tests/ui/test_ui_download_pause.py tests/ui/test_ui_main_window.py` (or full suite with `pytest -q`).

### Run tab: Custom video instructions (Preset vs Custom)
- **Content source** on **Run**: **Preset** keeps the existing flow (news cache + topic tags + personality). **Custom** uses multiline **video instructions** you write; the app does **not** pick headlines from the cache for that run. The script model runs twice: **expand** rough notes into a structured creative brief (plain text), then **generate** the same JSON `VideoPackage` the rest of the pipeline consumes (slower than Preset). Topic tags from the Topics tab still bias hashtags when relevant.
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `run_content_mode` (`preset` | `custom`), `custom_video_instructions` (capped length `MAX_CUSTOM_VIDEO_INSTRUCTIONS`).
- **Orchestration** ([`main.py`](main.py)): Custom mode builds synthetic `sources` for metadata (`source: "custom"`), skips article fetch, calls [`src/content/brain.py`](src/content/brain.py) `expand_custom_video_instructions` then `generate_script(..., creative_brief=..., video_format=...)`. **Auto** personality uses instruction text in [`src/content/personality_auto.py`](src/content/personality_auto.py) `extra_scoring_text`. **Factcheck** `rewrite_with_uncertainty` is skipped when there is no article (Custom-only scripts).
- **UI** ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py), [`UI/main_window.py`](UI/main_window.py)): Preset/Custom radio + instructions editor; **Preview** / **Storyboard preview** / **Run** require non-empty instructions in Custom mode.
- **Workers** ([`UI/workers.py`](UI/workers.py)): `PreviewWorker` and `StoryboardWorker` mirror the same Custom vs Preset branching as `run_once`.
- **Tests**: [`tests/content/test_brain.py`](tests/content/test_brain.py) (creative-brief prompt path), [`tests/content/test_brain_expand.py`](tests/content/test_brain_expand.py) (`expand_custom_video_instructions`), [`tests/cli/test_config_and_settings.py`](tests/cli/test_config_and_settings.py) (settings roundtrip), [`tests/ui/test_ui_workers.py`](tests/ui/test_ui_workers.py) (`PreviewWorker` custom path skips news cache). [`tests/ui/test_ui_download_pause.py`](tests/ui/test_ui_download_pause.py) dummy download worker updated for `ModelDownloadWorker(..., remote_bytes_by_repo=...)`.

### Tasks: pipeline progress + pause/stop
- **Tasks** tab **Status** column shows **stage + percent** (e.g. `Pipeline: Writing script (LLM)… — 22%`) during runs, not only “Running…”. Emitted from [`main.py`](main.py) `run_once(..., on_progress=)` → [`UI/workers.py`](UI/workers.py) `PipelineWorker.progress` / batch remapped `PipelineBatchWorker.progress`; labels in [`UI/progress_tasks.py`](UI/progress_tasks.py) (`pipeline_run`, `pipeline_video`).
- **Pause** / **Resume** and **Stop** while a pipeline, batch run, Preview, or Storyboard job is active (cooperative cancel between steps via [`src/runtime/pipeline_control.py`](src/runtime/pipeline_control.py); `main.run_once` checkpoints). Stop also requests `QThread` interruption.
- **`tests/runtime/test_pipeline_control.py`**: unit tests for pause/cancel behavior.

### Model tab: integrity badges + result dialog
- After **Download ▾ → Verify checksums**, results are stored in [`data/model_integrity_status.json`](data/model_integrity_status.json) (gitignored) and shown on each model row: **✓ Verified**, **✗ Missing files**, **✗ Corrupt**, **✗ Missing & corrupt**, **⚠ Verify error**, or **✓ On disk** when snapshots exist but checksums were never run. Helpers: [`src/models/model_integrity_cache.py`](src/models/model_integrity_cache.py).
- Verification completion opens a **readable popup** (summary + “Show Details…” full log), not only the activity log ([`UI/main_window.py`](UI/main_window.py)).
- **`tests/models/test_model_integrity.py`**: integrity cache classification; [`tests/content/test_brain_expand.py`](tests/content/test_brain_expand.py) covers `expand_custom_field_text` with mocked generation.

### LLM “brain” on custom text fields
- **`UI/brain_expand.py`**: 🧠 button on the corner of supported fields runs [`src/content/brain.py`](src/content/brain.py) **`expand_custom_field_text`** in [`UI/workers.py`](UI/workers.py) **`TextExpandWorker`** (uses **Script model (LLM)** from the Model tab).
- Wired on **Characters** (identity, visual style, negatives), **Topics** tag input, and **Storyboard Preview** scene prompt (when the dialog has a main window parent).

### Characters tab layout
- Denser spacing, shorter list, horizontal Add/Duplicate/Delete row, capped text areas ([`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)).

### Characters + ElevenLabs TTS
- **Characters** tab: create, edit, and delete user-defined **characters** (name, identity, visual style, negative prompts, per-character voice options). Persisted locally as `data/characters.json` (gitignored).
- **Run** tab: **Character** dropdown; chosen character feeds **LLM script context** and optional **storyboard** character consistency ([docs/ui/characters.md](docs/ui/characters.md)).
- **API** tab: **ElevenLabs** — enable + API key (optional `ELEVENLABS_API_KEY` env). When enabled and a character has an **ElevenLabs voice** selected, **cloud TTS** is used (MP3 → WAV via FFmpeg); on failure or missing key, the pipeline falls back to Kokoro/pyttsx3 ([docs/integrations/elevenlabs.md](docs/integrations/elevenlabs.md)).
- Implementation: [`src/content/characters_store.py`](src/content/characters_store.py), [`src/speech/elevenlabs_tts.py`](src/speech/elevenlabs_tts.py), [`src/speech/voice.py`](src/speech/voice.py) `synthesize`, [`main.py`](main.py) run wiring, [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py), [`UI/workers.py`](UI/workers.py) async voice list refresh.
- **Tests**: [`tests/content/test_characters_store.py`](tests/content/test_characters_store.py), [`tests/platform/test_elevenlabs_tts.py`](tests/platform/test_elevenlabs_tts.py) (mocked HTTP); settings/preflight tests extended for new fields.

### Packaging (Windows one-file EXE)
- [`build/build.ps1`](build/build.ps1) and [`aquaduct-ui.spec`](aquaduct-ui.spec): extra `--hidden-import` / `collect_all` for HTTPS (`requests`, `urllib3`, `certifi`, `charset_normalizer`), `pyttsx3`, `src.speech.elevenlabs_tts`, `src.content.characters_store`, `UI.no_wheel_controls`, `UI.model_execution_toggle`, `UI.api_model_widgets`, runtime `src.runtime.pipeline_api` / `generation_facade`, and UI tab modules; bundle all `docs/**/*.md` for UI builds (spec uses portable `SPECPATH` globs). Still bundles `imageio`/related metadata and submodules for `src` / `UI`; UI EXE supports **`-debug` / `--debug`** for a console. See [build/README.md](build/README.md) and [docs/build/building_windows_exe.md](docs/build/building_windows_exe.md).

### Fixes
- [`main.py`](main.py): removed a redundant inner `import ensure_ffmpeg` inside `run_once` that shadowed the top-level import and caused `UnboundLocalError` when FFmpeg was missing at startup.

### Tasks + TikTok
- **Tasks** tab: queued finished videos (`data/upload_tasks.json`), open/play, copy caption, manual “posted”, remove; auto-listed after each successful run.
- **API** tab: **TikTok** section (OAuth PKCE + local callback, inbox upload via Content Posting API). Optional **auto-start TikTok upload** when a render completes.
- See [docs/integrations/tiktok.md](docs/integrations/tiktok.md).

### Tasks + YouTube (Shorts / Data API v3)
- **Separate enable** from TikTok: **`youtube_enabled`** and its own OAuth client (default loopback port **8888**, vs TikTok **8765**).
- **API** tab: **YouTube** section — client ID/secret, redirect URI, default privacy, optional **#Shorts** in title/description, optional **auto-upload after render**.
- **Tasks** tab: **YouTube** status column, **Upload to YouTube**; uploads via resumable `videos.insert` (`src/platform/youtube_upload.py`, `UI/workers.py` `YouTubeUploadWorker`).
- See [docs/integrations/youtube.md](docs/integrations/youtube.md).

### Model integrity (checksums)
- **Model** tab → **Download ▾**: **Verify checksums** for selected installed models or for **all** folders under `models/`.
- Uses `huggingface_hub.HfApi.verify_repo_checksums` (SHA-256 for LFS weights, git blob ids for small files); needs network + HF auth for gated repos.
- Implementation: `src/models/model_manager.py` (`verify_project_model_integrity`, `list_installed_repo_ids_from_disk`), `UI/workers.py` `ModelIntegrityVerifyWorker`.

### Topics and video format
- **Per-format topic lists**: `AppSettings.topic_tags_by_mode` stores tags separately for `news`, `cartoon`, and `explainer`. The active list for a run comes from `video_format` via `src/content/topics.py` (`effective_topic_tags()`). Legacy flat `topic_tags` in `ui_settings.json` is migrated into `topic_tags_by_mode["news"]` on load.
- **Run tab**: **Video format** combo (News / Cartoon / Explainer) chooses both the pipeline mode and which topic list applies; hint text explains the link to the Topics tab.
- **Topics tab**: **Mode** selector edits one list at a time; **Discover** (headline-based topic suggestions) uses the **selected mode’s** tag list and adds approved picks to that list (not News-only).

### News cache (dedupe)
- **Per-format seen files**: URL and title-history caches are split by format — `data/news_cache/seen_<mode>.json` and `seen_titles_<mode>.json` (for example `seen_news.json`, `seen_cartoon.json`). Legacy flat `seen.json` / `seen_titles.json` is read once to seed **news** when the per-mode file is missing.
- **Clear cache** (Video tab): removes legacy files and all `seen_*.json` / `seen_titles_*.json` in `data/news_cache/`. Implementation: `src/content/crawler.py` `clear_news_seen_cache_files()` (used by the desktop UI).

### Crawler / API
- Optional **Firecrawl** integration for search/scrape (`src/content/firecrawl_news.py`); configurable in the app **API** tab and env (`FIRECRAWL_API_KEY`).
- **`cache_mode`** on `get_latest_items` / `get_scored_items` ties dedupe to the current `video_format`.
- **Mode-aware headline queries**: `news` / `cartoon` / `explainer` use different Google News / Firecrawl search templates (cartoon and explainer no longer reuse the AI-tool “release” phrasing from news). `fetch_latest_items(..., topic_mode=...)` drives **Discover** and matches pipeline `video_format`.

### Tests
- **`tests/discover/test_crawler_seen_modes.py`**: per-mode isolation, legacy migration, `clear_news_seen_cache_files`, `news_cache_mode_for_run` / `effective_topic_tags` coverage in config tests.
- **`tests/conftest.py`**: `patch_paths` also patches `UI.main_window.get_paths` so UI tests use temp dirs.

### Naming
- The application is branded **Aquaduct** everywhere user-visible (window title, header, scripts, docs). Windows EXE outputs are **`aquaduct.exe`** (CLI) and **`aquaduct-ui.exe`** (desktop); PyInstaller spec: `aquaduct-ui.spec`.

### Desktop UI (PyQt6)
- **Model** tab (formerly “Settings”): model downloads + dependencies; consolidated actions into a **Download ▾** menu (download selected / download all selected / download all models; dependency checks under the same menu). Cleaner models row and download flow.
- **Model downloads**: If a repo is **already present** under `models/` (verified snapshot, not an empty/partial folder), **Download selected**, **Download all selected**, and **Download all models** **skip** it and continue with the next repo. Logs which repos were skipped.
- **Download progress**: Clearer status text (human-readable bytes, per-repo file progress, overall queue percent, Hub “probe” size note so multi-repo totals are not confused with a single progress bar).
- **Models list**: Hub reachability/size probe at startup; local **installed** markers; grayed options when a repo is not available locally yet.
- **Branding**: Changing the **Palette** preset updates the **Theme color** hex fields and swatches to match `PRESET_PALETTES`. On first open, unchecked rows sync to the preset; rows with overrides left checked keep saved colors.
- **Preview pipeline**: Auto personality selection no longer does an extra full LLM load before script generation (rules-only pick; faster preview start).

### Core / libraries
- **`src/model_manager`**: `model_has_local_snapshot()`, `probe_hf_model()`, `remote_repo_size_bytes()`, Hub-backed **integrity verification** helpers for local snapshots.
- **Video model selection**: Image + video HF repos download together when the selection is a **pair** (both snapshots required).

### Scripts
- **`scripts/download_hf_models.py`**: Portable HF snapshot downloader into `./models` (same layout as the app), with optional `--out` and token via env/CLI.

### Docs & tests
- Docs refreshed for UI (Tasks progress, Model integrity badges/dialog, **🧠** field expansion, **frameless dialogs**), **README**, [docs/ui/ui.md](docs/ui/ui.md), [docs/reference/models.md](docs/reference/models.md), [docs/ui/characters.md](docs/ui/characters.md), [docs/pipeline/brain.md](docs/pipeline/brain.md), [docs/reference/config.md](docs/reference/config.md), [docs/pipeline/main.md](docs/pipeline/main.md); branding palette behavior, models/skip semantics, **TikTok**, **YouTube**, **checksum verification**, **Characters**, **ElevenLabs**, **Preset vs Custom** run content, and **borderless alerts**.
- **`tests/content/test_personality_auto.py`** updated for rules-only auto pick.
- **`tests/social/test_upload_tasks.py`**, **`tests/social/test_tiktok_post.py`**, **`tests/models/test_model_integrity.py`**, **`tests/content/test_brain_expand.py`** (mocked LLM expand). UI tests need **`pip install -r requirements-dev.txt`** (pytest-qt + PyQt6 for `qtbot`).

## 0.1.0 — 2026-04-15
- Initial MVP scaffold: crawler → local script generation → local TTS + captions → SDXL Turbo images → micro-scene editor → per-video outputs under `videos/`.
