# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### GPU / diffusion: multi-GPU offload, placement, video prompts, and SVD VRAM
- **Device routing** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): In **Auto** with **two or more** CUDA devices, **LLM** and **diffusion** are always assigned **different** ordinals (max-VRAM GPU for image/video, compute-heuristic GPU for script; if those collide, LLM moves to the best remaining GPU). A small safety net avoids assigning both roles to the same index if that ever regresses.
- **Diffusion offload** ([`src/util/diffusion_placement.py`](src/util/diffusion_placement.py)): **`auto`** chooses **sequential** CPU offload when **`torch.cuda.device_count() >= 2`** to keep peak VRAM low on the diffusion GPU. **`enable_sequential_cpu_offload`** now receives **`gpu_id`** when a diffusion CUDA index is set (previously only model offload passed it). Single-GPU **`auto`** still uses **full GPU** (`none`) only from **≥16 GiB** detected VRAM (with host-RAM exceptions unchanged); 8–15 GiB uses **model** offload unless overridden.
- **Video clips** ([`src/render/clips.py`](src/render/clips.py)): **CLIP** text paths: optional **77-token** round-trip via `CLIPTokenizerFast` after word/char caps (skipped for CogVideoX / LTX). **SVD** img2vid: tighter **`num_frames`** cap on **≤12 GiB** cards, smaller **`decode_chunk_size`** on those GPUs, prior OOM-oriented placement tweaks retained.
- **Tests**: [`tests/test_diffusion_placement.py`](tests/test_diffusion_placement.py) (multi-GPU sequential default, `gpu_id` on sequential), [`tests/test_clips_img2vid_prompt.py`](tests/test_clips_img2vid_prompt.py).
- **Docs**: [`README.md`](README.md), [`docs/config.md`](docs/config.md), [`docs/hardware.md`](docs/hardware.md), [`docs/performance.md`](docs/performance.md), [`docs/vram.md`](docs/vram.md), [`docs/ui.md`](docs/ui.md), [`docs/models.md`](docs/models.md).

### Curated frontier models (image + video), download list, and docs
- **Model registry** ([`src/models/model_manager.py`](src/models/model_manager.py)): **Image** — *FLUX.1 Schnell*, *Stable Diffusion 3 Medium*, *FLUX.1-dev* alongside SDXL / SD 1.5 / SDXL Base. **Video** — *CogVideoX 2B/5B*, *LTX-Video*, *HunyuanVideo* alongside SVD, ZeroScope, ModelScope T2V.
- **Rendering** ([`src/render/artist.py`](src/render/artist.py)): T2I loading via **`_load_auto_t2i_pipeline`** / **`_load_auto_i2i_pipeline`** (BF16 for FLUX/SD3; FP16+`variant` for SDXL-class); **`_apply_flux_negative_cfg`** for Flux + negative prompt; presets in **`_IMAGE_T2I_PRESETS`** / **`_diffusion_kw_for_model`**. **Tests**: [`tests/test_diffusion_presets_coverage.py`](tests/test_diffusion_presets_coverage.py).
- **Clips** ([`src/render/clips.py`](src/render/clips.py)): **`CogVideoXPipeline`**, **`LTXPipeline`**, **`HunyuanVideoPipeline`** where applicable; **`CURATED_VIDEO_CLIP_REPO_IDS`**, **`_video_pipe_kwargs`**, **`_load_text_to_video_pipeline`**. **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): VRAM hints + **`rate_model_fit_for_repo`** / **`_MOTION_VIDEO_PREF_ORDER`** for new video ids.
- **Docs**: [`README.md`](README.md), [`docs/models.md`](docs/models.md) (curated table + download commands), [`docs/artist.md`](docs/artist.md), [`docs/hardware.md`](docs/hardware.md).
- **Scripts** ([`scripts/download_hf_models.py`](scripts/download_hf_models.py)): **`ALL_REPOS`** aligned with `model_options()` for `python scripts/download_hf_models.py --all`.

### UI: vector icons, tab alignment, theme palettes, LLM VRAM caps, multi-GPU Auto split
- **Title bar** ([`UI/widgets/title_bar_outline_button.py`](UI/widgets/title_bar_outline_button.py), [`UI/widgets/title_bar_svg_icons.py`](UI/widgets/title_bar_svg_icons.py), [`UI/main_window.py`](UI/main_window.py)): Save / resource graph / Help / Close use **QSvgRenderer**-drawn strokes (theme-colored) instead of emoji/text; LRU-cached pixmaps.
- **Characters toolbar** ([`UI/widgets/toolbar_svg_icons.py`](UI/widgets/toolbar_svg_icons.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)): Add / duplicate / delete use SVG icons (muted palette); removed Fusion standard pixmaps + duplicate fallback glyph.
- **Tasks run controls** ([`UI/tabs/tasks_tab.py`](UI/tabs/tasks_tab.py), [`UI/main_window.py`](UI/main_window.py)): Refresh / pause|play / stop use SVG icons (accent / text / danger); `_sync_tasks_pause_button_appearance` swaps pause vs play vectors.
- **Frozen EXE** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden import **`PyQt6.QtSvg`** for SVG rendering.
- **Tabs** ([`UI/theme/palette.py`](UI/theme/palette.py)): **`QTabWidget::tab-bar { left: 10px; }`** so the tab strip aligns with the pane below (reduces left overhang on dark Fusion).
- **Branding palettes** ([`UI/theme/palette.py`](UI/theme/palette.py), [`UI/tabs/branding_tab.py`](UI/tabs/branding_tab.py)): Added presets **forest**, **lavender**, **ember**, **slate**, **rose**, **amber**, **nord**, **dracula** (in addition to default / tiktok / ocean / sunset / mono).
- **Local LLM VRAM** ([`src/content/brain.py`](src/content/brain.py)): When **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** is unset, **CUDA total VRAM** tightens the default input cap (e.g. &lt;10 GiB → **1536** tokens) to reduce prefill OOM on ~8 GB cards; `empty_cache()` before `generate()` retained/extended.
- **Multi-GPU Auto** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): If **max-VRAM** and **compute** heuristics pick the **same** GPU, **LLM** moves to the **best remaining** compute GPU so a second card is used; [`UI/widgets/gpu_policy_toggle.py`](UI/widgets/gpu_policy_toggle.py) + resource graph Monitor tooltip updated. **Tests**: [`tests/test_cuda_device_policy.py`](tests/test_cuda_device_policy.py).

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
- **Docs**: [`README.md`](README.md), [`docs/ui.md`](docs/ui.md) (composition, Run/Topics/Library/API/Characters/Theme, My PC), [`docs/hardware.md`](docs/hardware.md), [`docs/config.md`](docs/config.md) (GPU policy UI mapping), [`docs/models.md`](docs/models.md), [`docs/performance.md`](docs/performance.md).

### Multi-GPU: My PC, resource monitor, runtime policy
- **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): `GpuDevice`, `list_cuda_gpus()`, VRAM-max and heuristic compute pickers; `HardwareInfo` can summarize multiple GPUs.
- **Policy** ([`src/util/cuda_device_policy.py`](src/util/cuda_device_policy.py)): Auto vs single, `effective_vram_gb_for_kind`, `resolve_llm_cuda_device_index` / `resolve_diffusion_cuda_device_index`; optional **`AQUADUCT_CUDA_DEVICE`** override; `DevicePlan` includes reserved **`use_model_parallel_llm`** (currently always `False` — no automatic Accelerate multi-GPU LLM sharding; 4-bit stays single-GPU).
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `gpu_selection_mode`, `gpu_device_index`, `resource_graph_monitor_gpu_index` in `ui_settings.json`.
- **UI** (see also **Desktop UI: section cards…** above): **My PC** model **Fit** table + GPU policy persistence; **Resource graph** monitor combo + `sample_gpu_mem_pct()`; **Model** tab fit parity with effective VRAM + tab-switch refresh ([`UI/main_window.py`](UI/main_window.py)).
- **Runtime**: [`src/content/brain.py`](src/content/brain.py), [`src/util/diffusion_placement.py`](src/util/diffusion_placement.py), [`src/render/artist.py`](src/render/artist.py), [`src/render/clips.py`](src/render/clips.py), [`main.py`](main.py) / [`UI/workers.py`](UI/workers.py) pass resolved CUDA indices.
- **Docs**: [`README.md`](README.md), [`docs/hardware.md`](docs/hardware.md), [`docs/config.md`](docs/config.md), [`docs/ui.md`](docs/ui.md), [`docs/models.md`](docs/models.md), [`docs/performance.md`](docs/performance.md), [`docs/vram.md`](docs/vram.md). **Tests**: [`tests/test_cuda_device_policy.py`](tests/test_cuda_device_policy.py), [`tests/test_resource_sample.py`](tests/test_resource_sample.py).

### Photo mode + API: still images only (no MP4 / clips)
- **Pipeline** ([`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py)): **`run_once_api`** now branches on **`media_mode == "photo"`** after the script step: generates **API** stills via **`generate_still_png_bytes`**, optional layout / grid (`Picture` settings), writes **`final.png`**, and returns — **no** voice, **no** Replicate video clips, **no** slideshow MP4.
- **API preflight** ([`src/runtime/model_backend.py`](src/runtime/model_backend.py)): when **`media_mode` is `photo`**, only **LLM** + **Image** providers/keys are required (voice and video/Replicate rules for motion do not apply).

### Local LLM: prompt truncation (VRAM)
- **Brain** ([`src/content/brain.py`](src/content/brain.py)): local transformers `generate()` tokenizes the instruction prompt with **`truncation=True`** and a cap (default **4096**, or **`min(4096, tokenizer.model_max_length)`** when finite). Override with **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** (256–100000). Calls **`torch.cuda.empty_cache()`** before **`generate()`** when CUDA is available to reduce fragmentation-related OOM on tight GPUs.
- **Docs**: [`docs/config.md`](docs/config.md).

### Run guard: local models + API preflight before pipeline
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py)): **`local_hf_model_snapshot_errors()`** — in **Local** mode, requires on-disk Hub snapshots for the roles the pipeline loads (defaults match [`main.py`](main.py) `run_once`): **Photo** mode → Script (LLM) + Image; **Video** mode → Script + Image + Voice + Video (motion). Skipped in **API** mode (existing **`api_preflight_errors`** applies).
- **UI** ([`UI/main_window.py`](UI/main_window.py)): on failed strict preflight, **Run** / queued jobs / approved preview / approved storyboard open the **Model** tab and show a borderless **Download models before running** or **Configure API before running** dialog (other preflight failures use a generic title). Queueing while a job runs also runs preflight before enqueueing.

### Startup splash (desktop cold start)
- **UI** ([`UI/startup_splash.py`](UI/startup_splash.py), [`UI/app.py`](UI/app.py)): after **`QApplication`** starts, a frameless **splash** shows **Aquaduct**, a **progress bar** (determinate steps + **indeterminate** during blocking imports / `MainWindow()` init), and **elapsed seconds**. Set **`AQUADUCT_NO_SPLASH=1`** to disable. **`MainWindow`** is imported inside **`main()`** so the window can paint before the heaviest import work.
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden import **`UI.startup_splash`**.
- **Docs**: [`docs/ui.md`](docs/ui.md).

### Desktop UI: Photo / Video mode and smooth dialog chrome
- **Media mode** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): persisted **`media_mode`**: **`video`** (default) or **`photo`** in `ui_settings.json`. The title bar **Photo \| Video** toggle switches the pipeline output root ([`media_output_root()`](src/core/config.py)): **`.Aquaduct_data/videos`** vs **`.Aquaduct_data/pictures`**, tab visibility (e.g. **Picture** vs **Video** tab, Captions/Effects in video mode), and Library refresh targets.
- **Dialog chrome** ([`UI/title_bar_outline_button.py`](UI/title_bar_outline_button.py), [`UI/frameless_dialog.py`](UI/frameless_dialog.py), [`UI/tutorial_dialog.py`](UI/tutorial_dialog.py), [`UI/download_popup.py`](UI/download_popup.py), [`UI/install_deps_dialog.py`](UI/install_deps_dialog.py)): borderless dialogs, the Help tutorial (**Previous** / **Next** / **Close**), model download/import popups, and the install-dependencies footer use **`TitleBarOutlineButton`** with antialiased rounded strokes (same approach as the main window title bar), via **`styled_outline_button()`**. Legacy stylesheet **`QPushButton#closeBtn`** rules were removed from [`UI/theme.py`](UI/theme.py). **`FramelessDialog`** sets **`_frameless_close_button`** so the install-dependencies dialog can enable/disable the title **✕** while pip runs.
- **Docs**: [`README.md`](README.md), [`docs/ui.md`](docs/ui.md), [`docs/config.md`](docs/config.md).
- **Tests**: [`tests/test_title_bar_outline_button.py`](tests/test_title_bar_outline_button.py), [`tests/test_app_dirs.py`](tests/test_app_dirs.py) (`test_media_output_root_video_vs_photo`), [`tests/test_config_and_settings.py`](tests/test_config_and_settings.py) (`test_ui_settings_media_mode_roundtrip`), [`tests/test_import_smoke_api.py`](tests/test_import_smoke_api.py) (imports for `UI.frameless_dialog`, `UI.title_bar_outline_button`).

### Help / first-run tutorial
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): **`tutorial_completed`** in `ui_settings.json` — false until the user dismisses the first-run help.
- **UI** ([`UI/tutorial_dialog.py`](UI/tutorial_dialog.py), [`UI/main_window.py`](UI/main_window.py), [`UI/theme.py`](UI/theme.py)): title bar **?** next to **📈** opens a frameless **Help** dialog with a **topic list** (left) and **slide** pages (right) with **Previous** / **Next**; **Close** ends the session. **`QTimer`** (~1.8s) shows the same dialog once on first launch if `tutorial_completed` is false (after the optional HF token prompt). [`UI/main_window.py`](UI/main_window.py) **`_collect_settings_from_ui`** preserves **`tutorial_completed`**. **`TutorialDialog`** accepts **`start_topic_id`** / **`start_slide`** and **`go_to_topic()`** so callers can open on a specific topic/slide.
- **Help links in tooltips** ([`UI/tutorial_links.py`](UI/tutorial_links.py)): many tab hints use HTML tooltips with an **Open in Help →** link (`topic://…?slide=…`). A **`RichHelpTooltipFilter`** on **`QApplication`** shows a small **`QTextBrowser`** popup (native tooltips are not clickable) and opens Help at the right topic when the link is clicked. Wired on title bar **💾** / **📈** / **?**, Run, Topics, Video, Tasks, Library, Model, and Characters where hints map to tutorial topics.
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden imports **`UI.tutorial_dialog`**, **`UI.tutorial_links`**.
- **Docs / tests**: [`docs/ui.md`](docs/ui.md), [`docs/config.md`](docs/config.md), [`tests/test_config_and_settings.py`](tests/test_config_and_settings.py) (`test_ui_settings_tutorial_completed_roundtrip`), [`tests/test_import_smoke_api.py`](tests/test_import_smoke_api.py) (`test_import_ui_tutorial_links`).

### CPU parallelism (OpenMP, BLAS, PyTorch, Hub probes)
- **Runtime** ([`src/util/cpu_parallelism.py`](src/util/cpu_parallelism.py)): early **`configure_cpu_parallelism()`** sets **`OMP_NUM_THREADS`**, **`MKL_NUM_THREADS`**, **`OPENBLAS_NUM_THREADS`**, **`NUMEXPR_NUM_THREADS`**, **`VECLIB_MAXIMUM_THREADS`** when unset (default target **`min(32, os.cpu_count())`**; override with **`AQUADUCT_CPU_THREADS`**). This tunes **host CPU** threads for math libraries — not GPU multithreading. Called from [`main.py`](main.py), [`UI/ui_app.py`](UI/ui_app.py), and [`UI/app.py`](UI/app.py) before heavy imports.
- **PyTorch** ([`src/models/torch_dtypes.py`](src/models/torch_dtypes.py), [`src/content/brain.py`](src/content/brain.py)): after **`import torch`**, **`apply_torch_cpu_settings`** sets **`torch.set_num_threads`** from **`effective_cpu_thread_count()`** and **`torch.set_num_interop_threads`** from **`torch_interop_thread_count()`** — higher inter-op when **no CUDA/MPS** (more overlapping CPU-side ops), modest when an accelerator is present; optional override **`AQUADUCT_TORCH_INTEROP_THREADS`** (1–32).
- **UI** ([`UI/workers.py`](UI/workers.py)): **`ModelSizePingWorker`** probes Hugging Face repos with a **thread pool** (I/O-bound); **`ModelIntegrityVerifyWorker`** verifies multiple repos **in parallel** (capped for disk I/O).
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden import **`src.util.cpu_parallelism`**.
- **Docs / tests**: [`docs/performance.md`](docs/performance.md), [`docs/config.md`](docs/config.md), [`README.md`](README.md), [`tests/test_cpu_parallelism.py`](tests/test_cpu_parallelism.py).

### Library tab: browse past outputs
- **UI** ([`UI/tabs/library_tab.py`](UI/tabs/library_tab.py), [`UI/library_fs.py`](UI/library_fs.py), [`UI/main_window.py`](UI/main_window.py)): new **Library** tab lists **`videos/`** projects that contain **`final.mp4`** (title from `meta.json`, modified time, file size) and all **`runs/`** workspace folders (intermediate pipeline artifacts). Toolbar opens the **`videos/`** or **`runs/`** root; per-row actions open the project folder, **`assets/`**, or play **`final.mp4`**; double-click opens the folder. **Refresh** rescans disk; switching to the tab refreshes; pipeline **`_on_done`** refreshes after each run completes.
- **Packaging** ([`aquaduct-ui.spec`](aquaduct-ui.spec), [`build/build.ps1`](build/build.ps1)): hidden imports for **`UI.tabs.library_tab`**, **`UI.library_fs`**, **`UI.tab_sections`**.
- **Tests**: [`tests/test_library_fs.py`](tests/test_library_fs.py).

### Run / Video / Model tabs: section groups and spacing
- **UI** ([`UI/tab_sections.py`](UI/tab_sections.py)): shared **`section_title()`** and **`add_section_spacing()`** for consistent subsection labels and vertical gaps on the dark theme.
- **Run** ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py)): **Output**, **Script & content**, **Actions**.
- **Video** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py)): clearer breaks between platform template, **Output & timing**, **Quality / performance**, **Story pipeline (LLM)**, and **Advanced** (spacing replaces horizontal rules between major blocks).
- **Model** ([`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py)): spacing after the download/install toolbar before the stack; spacing before **Model files location**; shared titles for model list and storage.

### Run tab: N videos = N independent pipeline tasks
- **UI** ([`UI/main_window.py`](UI/main_window.py)): **Videos to generate** no longer uses a single **Batch pipeline (N videos)** worker. Setting **N > 1** appends **N−1** jobs to the FIFO queue and starts the first **`PipelineWorker`** immediately — each completion adds its own Tasks row and the next queued run starts ([`UI/workers.py`](UI/workers.py): removed **`PipelineBatchWorker`**).
- **Queue while busy**: one click with **N = 3** appends **three** separate queue entries (not one entry with quantity 3).
- **Tasks table**: each **FIFO-queued** pipeline job has its own row (**Queued pipeline run**, **Waiting in queue…**) under the active run so **`Tasks (n)`** matches visible pipeline work ([`UI/main_window.py`](UI/main_window.py) `_tasks_refresh`).
- **Docs / tests**: [`docs/ui.md`](docs/ui.md), [`tests/test_ui_main_window.py`](tests/test_ui_main_window.py), [`tests/test_pipeline_run_queue_contract.py`](tests/test_pipeline_run_queue_contract.py), [`UI/tabs/run_tab.py`](UI/tabs/run_tab.py) tooltip.

### Diffusion: automatic CPU offload (VRAM vs system RAM)
- **Placement** ([`src/util/diffusion_placement.py`](src/util/diffusion_placement.py)): shared **`place_diffusion_pipeline()`** for local **image** ([`src/render/artist.py`](src/render/artist.py)) and **video** ([`src/render/clips.py`](src/render/clips.py)) diffusers loads — **`enable_model_cpu_offload()`** / **`enable_sequential_cpu_offload()`** vs full **`cuda`** based on **detected GPU VRAM** and **available system RAM** (`psutil`), not OS disk swap.
- **Auto policy** (override with **`AQUADUCT_DIFFUSION_CPU_OFFLOAD`**: `auto` \| `off` \| `model` \| `sequential`; legacy **`AQUADUCT_DIFFUSION_SEQUENTIAL_CPU_OFFLOAD=1`** still forces sequential when unset/`auto`): favors full GPU when VRAM is ample and host RAM is free; uses **model** offload for mid VRAM (~8–12 GB); **sequential** when VRAM is tight or unknown; if **free RAM &lt; ~3 GB** but **VRAM ≥ ~8 GB**, prefers **full GPU** to avoid extra CPU staging.
- **Hardware** ([`src/models/hardware.py`](src/models/hardware.py)): **total system RAM** falls back to **`psutil`** when the Windows-specific probe is unavailable (Linux/macOS).
- **Tests**: [`tests/test_diffusion_placement.py`](tests/test_diffusion_placement.py).

### Pro mode: multi-scene video + image-to-video (SVD)
- **Pipeline** ([`main.py`](main.py)): when **Pro** is on, **slideshow off**, and the **Video** model id is **img2vid** (e.g. `stabilityai/stable-video-diffusion-img2vid-xt` or ids containing **`img2vid`**), the app **generates one keyframe per scene** with the **Image** model, then runs **img2vid** on those paths — same idea as motion mode without Pro. **Text-to-video** models (e.g. ZeroScope) still use **`init_images=None`**. Scene prompts honor **`video_format`**: **news** anchors with the headline; **cartoon** / **unhinged** omit the title prefix ([`_split_into_pro_scenes_from_script`](main.py)); [`src/runtime/pipeline_api.py`](src/runtime/pipeline_api.py) passes **`video_format`** consistently.
- **Preflight** ([`src/runtime/preflight.py`](src/runtime/preflight.py)): **no longer blocks** Pro + SVD; **slideshow + Pro + SVD** falls back to **still frames from the Image model** (the frame-stacking Pro path cannot drive SVD clip-by-clip).
- **UI** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py)): Pro checkbox label/tooltip describe **text-to-video** vs **image model → img2vid**.
- **Tests**: [`tests/test_pro_img2vid_mock_run.py`](tests/test_pro_img2vid_mock_run.py), [`tests/test_preflight.py`](tests/test_preflight.py).

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
- **Tests**: [`tests/test_firecrawl_crawler.py`](tests/test_firecrawl_crawler.py) (Discover vs pipeline RSS), [`tests/test_topic_discovery.py`](tests/test_topic_discovery.py), [`tests/test_topic_research_assets.py`](tests/test_topic_research_assets.py).

### Windows EXE build, tests, and operator docs
- **PyInstaller spec** ([`aquaduct-ui.spec`](aquaduct-ui.spec)): portable `SPECPATH` + `docs/*.md` glob (no machine-absolute paths); `pathex` set to repo root; explicit `hiddenimports` aligned with current packages (`src.speech.elevenlabs_tts`, `src.content.characters_store`, `UI.no_wheel_controls`, `UI.model_execution_toggle`, `UI.api_model_widgets`, tab modules, `src.runtime.pipeline_api`, `src.runtime.generation_facade`).
- **Build script** ([`build/build.ps1`](build/build.ps1)): same hidden-import belt-and-suspenders as the spec; **`-UseSpec`** to build via the spec; post-build **`scripts/frozen_smoke.py`** for UI and spec builds; **`$LASTEXITCODE`** check after PyInstaller.
- **Frozen import smoke** ([`UI/ui_app.py`](UI/ui_app.py), [`scripts/frozen_smoke.py`](scripts/frozen_smoke.py)): env **`AQUADUCT_IMPORT_SMOKE=1`** runs headless imports and exits before Qt when validating a built EXE.
- **Build docs** ([`build/README.md`](build/README.md)): verification checklist, `-debug` / `--debug`, `-UseSpec`, smoke commands, corrected module names in packaging notes.
- **Tests** ([`pytest.ini`](pytest.ini), [`tests/test_import_smoke_api.py`](tests/test_import_smoke_api.py)): documented **`qt`** / **`slow`** markers; import smoke for API pipeline modules and `UI.api_model_widgets`.
- **Docs**: new [`docs/building_windows_exe.md`](docs/building_windows_exe.md) (build/verify/troubleshoot) and [`docs/performance.md`](docs/performance.md) (import-time `cProfile` notes); cross-links in [`README.md`](README.md) (table of contents + **Docs**), [`docs/main.md`](docs/main.md), [`docs/ui.md`](docs/ui.md), [`docs/config.md`](docs/config.md), [`docs/api_generation.md`](docs/api_generation.md); test tier table in [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Desktop UI
- **Tasks tab badge** ([`UI/tabs/tasks_tab.py`](UI/tabs/tasks_tab.py), [`UI/main_window.py`](UI/main_window.py)): tab text shows **`Tasks (n)`** while pipeline/preview/storyboard work, queued runs, or TikTok/YouTube uploads are active (`n` is zero when idle). Docs: [`docs/ui.md`](docs/ui.md).
- **Run while busy** ([`UI/main_window.py`](UI/main_window.py)): removed disabling the **Run** button when a pipeline starts; **Run** is re-enabled immediately after the worker thread starts so additional clicks **enqueue** FIFO runs (matches docs: queue while a job is active).
- **Topics → Discover**: see **Topics tab: Discover, creative extraction, and topic research pack** above for crawler flags, Firecrawl-only creative Discover vs pipeline RSS fallback, UI copy, and saved research under `data/topic_research/`. Docs: [`docs/crawler.md`](docs/crawler.md), [`docs/ui.md`](docs/ui.md).
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
- **Docs**: [`docs/api_generation.md`](docs/api_generation.md); [`docs/config.md`](docs/config.md) (`AppSettings` API fields).
- **Tests**: [`tests/test_model_backend.py`](tests/test_model_backend.py), [`tests/test_api_generation.py`](tests/test_api_generation.py), [`tests/test_replicate_client.py`](tests/test_replicate_client.py), [`tests/test_brain_api.py`](tests/test_brain_api.py), [`tests/test_api_model_catalog.py`](tests/test_api_model_catalog.py), [`tests/test_generation_facade.py`](tests/test_generation_facade.py), [`tests/test_model_execution_toggle.py`](tests/test_model_execution_toggle.py), [`tests/test_ui_model_execution_mode.py`](tests/test_ui_model_execution_mode.py) (skips if PyQt6 absent), [`tests/test_preflight.py`](tests/test_preflight.py) (local explicit vs default), plus [`tests/test_ui_settings_api_models.py`](tests/test_ui_settings_api_models.py), [`tests/test_openai_client.py`](tests/test_openai_client.py), [`tests/test_story_context.py`](tests/test_story_context.py) (meme-forward Firecrawl queries for cartoon/unhinged), [`tests/test_firecrawl_crawler.py`](tests/test_firecrawl_crawler.py) / [`tests/test_crawler_seen_modes.py`](tests/test_crawler_seen_modes.py) (Discover headline vs creative modes).

### Automatic cast when no Character is selected
- **Fallback + LLM cast** ([`src/content/characters_store.py`](src/content/characters_store.py), [`src/content/brain.py`](src/content/brain.py)): format-aware default cast (e.g. news-style narrator vs multi-voice cartoon), optional **`generate_cast_from_storyline_llm`** aligned to the storyline, and ephemeral **`Character`** shaping for diffusion when no saved character is active. Cast JSON may be written to each video’s **`assets/generated_cast.json`** from the storyboard / pipeline path ([`UI/workers.py`](UI/workers.py), [`main.py`](main.py)).
- **Tests**: [`tests/test_generated_cast.py`](tests/test_generated_cast.py); [`tests/test_characters_store.py`](tests/test_characters_store.py) updated.

### UI copy, preflight, and progress: “scenes” (not “clips”)
- User-facing **Video** / **Model** tab labels, **preflight** errors, and **run progress** strings use **scene(s)** / **motion mode** instead of **clip(s)** / **clip mode** ([`UI/tabs/video_tab.py`](UI/tabs/video_tab.py), [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py), [`src/runtime/preflight.py`](src/runtime/preflight.py), [`main.py`](main.py)). Persisted setting keys (`clips_per_video`, `clip_seconds`, …) and asset folder names (`clips`, `pro_clips`) are unchanged for compatibility.
- **Docs** ([`README.md`](README.md), [`docs/ui.md`](docs/ui.md), [`docs/editor.md`](docs/editor.md), [`docs/config.md`](docs/config.md), [`docs/models.md`](docs/models.md), [`docs/main.md`](docs/main.md)) updated to match.

### Story pipeline: multi-stage script + web context + reference images
- **Video settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): new toggles under `VideoSettings`:
  - `story_multistage_enabled`: run format-specific multi-pass script refinement (beat structure, safety, length, clarity; comedy modes focus dialogue/pacing/punchline).
  - `story_web_context`: optional Firecrawl search/scrape digest for extra context (saved under `runs/.../assets/script_context/web_digest.md`).
  - `story_reference_images`: optionally download a few images from scraped pages and use the first as an **img2img** init for the first generated frame (when supported).
- **Pipeline wiring** ([`main.py`](main.py), [`UI/workers.py`](UI/workers.py)): context gathering + refinement run before storyboard/image generation; storyboard preview path uses cache-backed context.
- **Meme-forward web context (cartoon / unhinged)** ([`src/content/story_context.py`](src/content/story_context.py)): when **Gather web context** / **reference images** run, Firecrawl searches bias toward **memes, viral, templates**; two **supplement** searches merge extra results; up to **4** pages scraped and up to **5** reference images saved for diffusion img2img (vs 2 / 3 for other formats). [`UI/tabs/video_tab.py`](UI/tabs/video_tab.py) tooltips updated; tests: [`tests/test_story_context.py`](tests/test_story_context.py).
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
- **Tests**: [`tests/test_pro_mode_frames.py`](tests/test_pro_mode_frames.py); [`tests/test_preflight.py`](tests/test_preflight.py) and settings / preset tests extended for the rules above.

### Model tab: VRAM / size labels (encoding)
- UI strings for approximate VRAM and disk placeholders use **ASCII-safe** text in [`src/models/model_manager.py`](src/models/model_manager.py) and [`src/models/hardware.py`](src/models/hardware.py) (fixes mojibake like `Ôëê` / `ÔÇô` on Windows). [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py) paired-model size hint aligned.

### Run queue: Preview / Storyboard busy
- **Run** (and approve-run paths) enqueue when **`PipelineWorker`**, **`PreviewWorker`**, or **`StoryboardWorker`** is active via **`_pipeline_run_should_queue()`** ([`UI/main_window.py`](UI/main_window.py)). **`_try_start_next_queued_pipeline`** waits until none of those are busy. After preview/storyboard dialogs close (or fail/cancel), the next queued pipeline job can start.

### Characters tab: LLM auto presets
- **Preset** dropdown + **Generate with LLM** fills **name**, **identity**, **visual style**, **negatives**, and **use project default voice** from the script model using built-in archetypes ([`src/content/character_presets.py`](src/content/character_presets.py), [`generate_character_from_preset_llm`](src/content/brain.py), [`CharacterGenerateWorker`](UI/workers.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)). Optional one-line **extra notes** biases the run. Docs: [`docs/characters.md`](docs/characters.md).

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
- **`resolve_pretrained_load_path`** ([`src/models/model_manager.py`](src/models/model_manager.py)) no longer points `from_pretrained` at an **empty or stub** folder under `models/` (which caused extra Hub traffic). It requires the same **minimum on-disk size** as **`model_has_local_snapshot`**. If the project copy is missing or too small, it next uses **`snapshot_download(..., local_files_only=True)`** so a **full** snapshot already in the default Hugging Face cache (e.g. downloaded outside Aquaduct) is loaded by path instead of treating the repo id as a fresh remote pull. Docs: [`docs/models.md`](docs/models.md).

### Tests
- Removed **[`tests/test_torch_install.py`](tests/test_torch_install.py)** (fragile / slow environment-specific assertions).
- Added [`tests/test_character_presets.py`](tests/test_character_presets.py), [`tests/test_hf_access.py`](tests/test_hf_access.py).

### Video formats: topic sourcing + voice by mode
- **News** and **Explainer** now share the **same** headline search bias (AI / product releases) and the same short-form script defaults; Explainer no longer uses a separate “tutorial / science education” RSS query (`src/content/crawler.py`, `video_format_uses_news_style_sourcing()` in [`src/content/topics.py`](src/content/topics.py)).
- **Cartoon** headline queries bias toward **new animation / streaming / premiere / trailer / buzz**; brain prompts stress **not** a tutorial or how-to (`src/content/brain.py`).
- **Unhinged** queries bias toward **viral / meme / internet-culture** seeds; unhinged prompt copy notes trend satire (`src/content/crawler.py`, `src/content/brain.py`). Docs: [`docs/crawler.md`](docs/crawler.md).

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
- **`src/models/torch_dtypes.py`**: central `torch_float16()` for BitsAndBytes / `from_pretrained` dtypes. If `import torch` is a **broken or stub** install (no `torch.float16`), raises a clear `RuntimeError` pointing to `scripts/install_pytorch.py --with-rest` instead of `AttributeError: module 'torch' has no attribute 'float16'`. Used from [`src/content/brain.py`](src/content/brain.py), [`src/content/factcheck.py`](src/content/factcheck.py), [`src/render/artist.py`](src/render/artist.py), [`src/render/clips.py`](src/render/clips.py). Tests: [`tests/test_torch_dtypes.py`](tests/test_torch_dtypes.py).

### Model tab: download all voice models
- **Download ▾ → Download all voice models** queues Hugging Face snapshots for every curated TTS option (Kokoro, MMS-TTS, MeloTTS, Microsoft SpeechT5, Parler-TTS, XTTS, Bark, …), skipping repos already under `models/`. Implementation: [`UI/main_window.py`](UI/main_window.py) (`_download_all_voice_models`), [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py). Docs: [`docs/models.md`](docs/models.md), [`docs/ui.md`](docs/ui.md).

### Model tab: Auto-fit for this PC
- **Auto-fit for this PC** on the **Model** tab picks script / video / voice models from detected VRAM and RAM using `rank_models_for_auto_fit` in [`src/models/hardware.py`](src/models/hardware.py) (same rules as fit badges; SDXL Turbo is preferred over SD 1.5 when VRAM ≥ ~8 GB and Turbo is still OK). Skips disabled Hub rows; logs the selection and **saves settings**. Docs: [`docs/ui.md`](docs/ui.md). Tests: [`tests/test_auto_fit.py`](tests/test_auto_fit.py).

### Resource usage graph (fix)
- **Resource usage** (title bar 📈) sparklines crashed after the first second of data: `QBrush` was used for the area fill but not imported from `PyQt6.QtGui` ([`UI/resource_graph_dialog.py`](UI/resource_graph_dialog.py)).
- Timer updates (`_on_tick`) are wrapped in **try/except** so a bad sample tick does not tear down the main window.

### Terminal: activate venv (Windows)
- **[`scripts/setup_terminal_env.ps1`](scripts/setup_terminal_env.ps1)**: dot-source from the repo root (`. .\scripts\setup_terminal_env.ps1`) to **activate `.venv`** and `cd` to the project. Documents optional **`HF_TOKEN`** / Hub usage. See [`README.md`](README.md) and [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Voice models (download list)
- **Settings → Model → Voice** includes more Hugging Face TTS checkpoints for local snapshot download: **MMS-TTS English**, **MeloTTS English**, **SpeechT5**, **Parler-TTS mini v1**, and **Bark**, alongside existing **Kokoro 82M** and **coqui XTTS v2**. Same repos are listed in [`scripts/download_hf_models.py`](scripts/download_hf_models.py) `ALL_REPOS`. VRAM hints for **Bark** / **Parler** in [`src/models/hardware.py`](src/models/hardware.py). Docs: [`docs/models.md`](docs/models.md), [`docs/voice.md`](docs/voice.md), [`docs/model_youtube_demos.md`](docs/model_youtube_demos.md).

### Run tab: queue multiple pipeline jobs
- While a **pipeline** or **batch** run is active, clicking **Run** again **appends** another job to a FIFO queue (snapshot of settings + batch quantity at click time) instead of being ignored. Same for **Approve and run** (preview) and **approved storyboard render** when a pipeline is already running.
- When the current run **finishes** or **fails**, the next queued job starts after preflight (and FFmpeg readiness). **Stop** cancels the active run and **clears** any queued jobs, with a log line counting dropped items.
- Implementation: [`UI/main_window.py`](UI/main_window.py) (`_pipeline_run_queue`, `_try_start_next_queued_pipeline`, `_attach_and_start_pipeline_worker`). Docs: [`README.md`](README.md), [`docs/ui.md`](docs/ui.md). Tests: [`tests/test_ui_main_window.py`](tests/test_ui_main_window.py) (Qt), [`tests/test_pipeline_run_queue_contract.py`](tests/test_pipeline_run_queue_contract.py) (no Qt — queue payload shapes).

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
- **Tests**: existing UI tests unchanged; run `pytest tests/test_ui_workers.py tests/test_ui_download_pause.py tests/test_ui_main_window.py` (or full suite with `pytest -q`).

### Run tab: Custom video instructions (Preset vs Custom)
- **Content source** on **Run**: **Preset** keeps the existing flow (news cache + topic tags + personality). **Custom** uses multiline **video instructions** you write; the app does **not** pick headlines from the cache for that run. The script model runs twice: **expand** rough notes into a structured creative brief (plain text), then **generate** the same JSON `VideoPackage` the rest of the pipeline consumes (slower than Preset). Topic tags from the Topics tab still bias hashtags when relevant.
- **Settings** ([`src/core/config.py`](src/core/config.py), [`src/settings/ui_settings.py`](src/settings/ui_settings.py)): `run_content_mode` (`preset` | `custom`), `custom_video_instructions` (capped length `MAX_CUSTOM_VIDEO_INSTRUCTIONS`).
- **Orchestration** ([`main.py`](main.py)): Custom mode builds synthetic `sources` for metadata (`source: "custom"`), skips article fetch, calls [`src/content/brain.py`](src/content/brain.py) `expand_custom_video_instructions` then `generate_script(..., creative_brief=..., video_format=...)`. **Auto** personality uses instruction text in [`src/content/personality_auto.py`](src/content/personality_auto.py) `extra_scoring_text`. **Factcheck** `rewrite_with_uncertainty` is skipped when there is no article (Custom-only scripts).
- **UI** ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py), [`UI/main_window.py`](UI/main_window.py)): Preset/Custom radio + instructions editor; **Preview** / **Storyboard preview** / **Run** require non-empty instructions in Custom mode.
- **Workers** ([`UI/workers.py`](UI/workers.py)): `PreviewWorker` and `StoryboardWorker` mirror the same Custom vs Preset branching as `run_once`.
- **Tests**: [`tests/test_brain.py`](tests/test_brain.py) (creative-brief prompt path), [`tests/test_brain_expand.py`](tests/test_brain_expand.py) (`expand_custom_video_instructions`), [`tests/test_config_and_settings.py`](tests/test_config_and_settings.py) (settings roundtrip), [`tests/test_ui_workers.py`](tests/test_ui_workers.py) (`PreviewWorker` custom path skips news cache). [`tests/test_ui_download_pause.py`](tests/test_ui_download_pause.py) dummy download worker updated for `ModelDownloadWorker(..., remote_bytes_by_repo=...)`.

### Tasks: pipeline progress + pause/stop
- **Tasks** tab **Status** column shows **stage + percent** (e.g. `Pipeline: Writing script (LLM)… — 22%`) during runs, not only “Running…”. Emitted from [`main.py`](main.py) `run_once(..., on_progress=)` → [`UI/workers.py`](UI/workers.py) `PipelineWorker.progress` / batch remapped `PipelineBatchWorker.progress`; labels in [`UI/progress_tasks.py`](UI/progress_tasks.py) (`pipeline_run`, `pipeline_video`).
- **Pause** / **Resume** and **Stop** while a pipeline, batch run, Preview, or Storyboard job is active (cooperative cancel between steps via [`src/runtime/pipeline_control.py`](src/runtime/pipeline_control.py); `main.run_once` checkpoints). Stop also requests `QThread` interruption.
- **`tests/test_pipeline_control.py`**: unit tests for pause/cancel behavior.

### Model tab: integrity badges + result dialog
- After **Download ▾ → Verify checksums**, results are stored in [`data/model_integrity_status.json`](data/model_integrity_status.json) (gitignored) and shown on each model row: **✓ Verified**, **✗ Missing files**, **✗ Corrupt**, **✗ Missing & corrupt**, **⚠ Verify error**, or **✓ On disk** when snapshots exist but checksums were never run. Helpers: [`src/models/model_integrity_cache.py`](src/models/model_integrity_cache.py).
- Verification completion opens a **readable popup** (summary + “Show Details…” full log), not only the activity log ([`UI/main_window.py`](UI/main_window.py)).
- **`tests/test_model_integrity.py`**: integrity cache classification; [`tests/test_brain_expand.py`](tests/test_brain_expand.py) covers `expand_custom_field_text` with mocked generation.

### LLM “brain” on custom text fields
- **`UI/brain_expand.py`**: 🧠 button on the corner of supported fields runs [`src/content/brain.py`](src/content/brain.py) **`expand_custom_field_text`** in [`UI/workers.py`](UI/workers.py) **`TextExpandWorker`** (uses **Script model (LLM)** from the Model tab).
- Wired on **Characters** (identity, visual style, negatives), **Topics** tag input, and **Storyboard Preview** scene prompt (when the dialog has a main window parent).

### Characters tab layout
- Denser spacing, shorter list, horizontal Add/Duplicate/Delete row, capped text areas ([`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)).

### Characters + ElevenLabs TTS
- **Characters** tab: create, edit, and delete user-defined **characters** (name, identity, visual style, negative prompts, per-character voice options). Persisted locally as `data/characters.json` (gitignored).
- **Run** tab: **Character** dropdown; chosen character feeds **LLM script context** and optional **storyboard** character consistency ([docs/characters.md](docs/characters.md)).
- **API** tab: **ElevenLabs** — enable + API key (optional `ELEVENLABS_API_KEY` env). When enabled and a character has an **ElevenLabs voice** selected, **cloud TTS** is used (MP3 → WAV via FFmpeg); on failure or missing key, the pipeline falls back to Kokoro/pyttsx3 ([docs/elevenlabs.md](docs/elevenlabs.md)).
- Implementation: [`src/content/characters_store.py`](src/content/characters_store.py), [`src/speech/elevenlabs_tts.py`](src/speech/elevenlabs_tts.py), [`src/speech/voice.py`](src/speech/voice.py) `synthesize`, [`main.py`](main.py) run wiring, [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py), [`UI/workers.py`](UI/workers.py) async voice list refresh.
- **Tests**: [`tests/test_characters_store.py`](tests/test_characters_store.py), [`tests/test_elevenlabs_tts.py`](tests/test_elevenlabs_tts.py) (mocked HTTP); settings/preflight tests extended for new fields.

### Packaging (Windows one-file EXE)
- [`build/build.ps1`](build/build.ps1) and [`aquaduct-ui.spec`](aquaduct-ui.spec): extra `--hidden-import` / `collect_all` for HTTPS (`requests`, `urllib3`, `certifi`, `charset_normalizer`), `pyttsx3`, `src.speech.elevenlabs_tts`, `src.content.characters_store`, `UI.no_wheel_controls`, `UI.model_execution_toggle`, `UI.api_model_widgets`, runtime `src.runtime.pipeline_api` / `generation_facade`, and UI tab modules; bundle `docs/*.md` for UI builds (spec uses portable `SPECPATH` globs). Still bundles `imageio`/related metadata and submodules for `src` / `UI`; UI EXE supports **`-debug` / `--debug`** for a console. See [build/README.md](build/README.md) and [docs/building_windows_exe.md](docs/building_windows_exe.md).

### Fixes
- [`main.py`](main.py): removed a redundant inner `import ensure_ffmpeg` inside `run_once` that shadowed the top-level import and caused `UnboundLocalError` when FFmpeg was missing at startup.

### Tasks + TikTok
- **Tasks** tab: queued finished videos (`data/upload_tasks.json`), open/play, copy caption, manual “posted”, remove; auto-listed after each successful run.
- **API** tab: **TikTok** section (OAuth PKCE + local callback, inbox upload via Content Posting API). Optional **auto-start TikTok upload** when a render completes.
- See [docs/tiktok.md](docs/tiktok.md).

### Tasks + YouTube (Shorts / Data API v3)
- **Separate enable** from TikTok: **`youtube_enabled`** and its own OAuth client (default loopback port **8888**, vs TikTok **8765**).
- **API** tab: **YouTube** section — client ID/secret, redirect URI, default privacy, optional **#Shorts** in title/description, optional **auto-upload after render**.
- **Tasks** tab: **YouTube** status column, **Upload to YouTube**; uploads via resumable `videos.insert` (`src/platform/youtube_upload.py`, `UI/workers.py` `YouTubeUploadWorker`).
- See [docs/youtube.md](docs/youtube.md).

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
- **`tests/test_crawler_seen_modes.py`**: per-mode isolation, legacy migration, `clear_news_seen_cache_files`, `news_cache_mode_for_run` / `effective_topic_tags` coverage in config tests.
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
- Docs refreshed for UI (Tasks progress, Model integrity badges/dialog, **🧠** field expansion, **frameless dialogs**), **README**, [docs/ui.md](docs/ui.md), [docs/models.md](docs/models.md), [docs/characters.md](docs/characters.md), [docs/brain.md](docs/brain.md), [docs/config.md](docs/config.md), [docs/main.md](docs/main.md); branding palette behavior, models/skip semantics, **TikTok**, **YouTube**, **checksum verification**, **Characters**, **ElevenLabs**, **Preset vs Custom** run content, and **borderless alerts**.
- **`tests/test_personality_auto.py`** updated for rules-only auto pick.
- **`tests/test_upload_tasks.py`**, **`tests/test_tiktok_post.py`**, **`tests/test_model_integrity.py`**, **`tests/test_brain_expand.py`** (mocked LLM expand). UI tests need **`pip install -r requirements-dev.txt`** (pytest-qt + PyQt6 for `qtbot`).

## 0.1.0 — 2026-04-15
- Initial MVP scaffold: crawler → local script generation → local TTS + captions → SDXL Turbo images → micro-scene editor → per-video outputs under `videos/`.
