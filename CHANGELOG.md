# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Characters tab: LLM auto presets
- **Preset** dropdown + **Generate with LLM** fills **name**, **identity**, **visual style**, **negatives**, and **use project default voice** from the script model using built-in archetypes ([`src/character_presets.py`](src/character_presets.py), [`generate_character_from_preset_llm`](src/brain.py), [`CharacterGenerateWorker`](UI/workers.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)). Optional one-line **extra notes** biases the run. Docs: [`docs/characters.md`](docs/characters.md).

### Brain / Model tab: same script LLM as the combo
- **`resolve_llm_model_id()`** ([`UI/brain_expand.py`](UI/brain_expand.py)) prefers the **Model** tab **`Script (LLM)`** combo’s **`currentData()`**, then saved `llm_model_id`, then the default from [`get_models()`](src/config.py). Character generation and **🧠** field expansion no longer use a stale saved id when the combo was changed but **Save** was not clicked — avoiding surprise Hub downloads for a different repo.

### Hugging Face: workers + gated-model errors
- **[`src/hf_access.py`](src/hf_access.py)**: **`ensure_hf_token_in_env`** applies the saved API token to **`HF_TOKEN`** / **`HUGGINGFACEHUB_API_TOKEN`** inside **`TextExpandWorker`** and **`CharacterGenerateWorker`** when the process env was empty (same rules as the main window: Hugging Face API enabled + token). **`humanize_hf_hub_error`** maps 401 / gated-repo failures to a short dialog instead of a full traceback.
- Workers receive **`hf_token`** / **`hf_api_enabled`** from settings ([`UI/workers.py`](UI/workers.py), [`UI/brain_expand.py`](UI/brain_expand.py), [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)).

### Editor / MoviePy: Pillow 10+ and RGBA compositing
- **[`src/pillow_compat.py`](src/pillow_compat.py)**: Pillow removed **`Image.ANTIALIAS`**; older MoviePy still references it in **`resize`** — compat shim runs before MoviePy import in [`src/editor.py`](src/editor.py).
- **CompositeVideoClip** could raise **`operands could not be broadcast`** when mixing **RGB** base frames with **RGBA** caption overlays — **`_ensure_rgba_np`** pads an opaque alpha channel on base image/video clips and watermarks before compositing ([`src/editor.py`](src/editor.py)).
- **`.gitignore`**: ignore MoviePy temp files (`*TEMP_MPY*.mp4`).

### Tests
- Removed **[`tests/test_torch_install.py`](tests/test_torch_install.py)** (fragile / slow environment-specific assertions).
- Added [`tests/test_character_presets.py`](tests/test_character_presets.py), [`tests/test_hf_access.py`](tests/test_hf_access.py).

### Video formats: topic sourcing + voice by mode
- **News** and **Explainer** now share the **same** headline search bias (AI / product releases) and the same short-form script defaults; Explainer no longer uses a separate “tutorial / science education” RSS query (`src/crawler.py`, `video_format_uses_news_style_sourcing()` in [`src/topics.py`](src/topics.py)).
- **Cartoon** headline queries bias toward **new animation / streaming / premiere / trailer / buzz**; brain prompts stress **not** a tutorial or how-to (`src/brain.py`).
- **Unhinged** queries bias toward **viral / meme / internet-culture** seeds; unhinged prompt copy notes trend satire (`src/crawler.py`, `src/brain.py`). Docs: [`docs/crawler.md`](docs/crawler.md).

### Key facts card: News & Explainer only
- The on-screen **Key facts** card (from article text) is **not** rendered for **Cartoon** or **Cartoon (unhinged)** pipeline modes — only **News** and **Explainer** (`video_format`). [`video_format_supports_facts_card()`](src/config.py); [`assemble_microclips_then_concat` / `assemble_generated_clips_then_concat`](src/editor.py) take `video_format=` from [`main.py`](main.py). **Captions** tab includes a short note; scene re-render loads `article.txt` when present and passes format from settings ([`UI/main_window.py`](UI/main_window.py)).

### Video tab: platform presets (tiles) + social templates
- **Platform template** at the top of **Video** uses **selectable tiles** (game-style preset cards): one tile per curated social profile (short-form vertical HD/720p, Instagram/Facebook square and 4:5, Pinterest 2:3, YouTube/LinkedIn 1080p, landscape 720p, etc.) plus **Custom** for full manual control. Definitions live in [`src/video_platform_presets.py`](src/video_platform_presets.py). Clicking a tile applies **resolution**, **FPS**, **micro-clip min/max**, **images per video**, **bitrate**, **clips per video**, and **seconds per clip**. The selection is stored as **`video.platform_preset_id`** in [`ui_settings.json`](src/ui_settings.py) and surfaced in [`UI/main_window.py`](UI/main_window.py) as **`_video_platform_preset_id`**. Editing any of those fields switches the UI to **Custom**.
- **Resolution** dropdown (formerly labeled “Video format”) lists all template sizes from the same module.

### Image generation: NSFW option + quality-regenerate fix
- **Allow NSFW image output** on **Video** ([`AppSettings.allow_nsfw`](src/config.py)): clears the diffusion **safety checker** / **feature extractor** after load so models such as SD 1.5 do not return black frames when the classifier flags content ([`src/artist.py`](src/artist.py)). Persisted in UI settings; passed through [`main.py`](main.py), [`UI/workers.py`](UI/workers.py), and regenerate flows in [`UI/main_window.py`](UI/main_window.py).
- **Quality retries** for slideshow/keyframes used to call `generate_images(..., max_images=1)`, which always wrote `img_001.png`, then [`apply_regenerated_image`](src/artist.py) deleted that source after copying—wiping **earlier** slides when regenerating a **later** index. Retries now use a **temporary output directory** before copying to the real path ([`main.py`](main.py), scene re-render in [`UI/main_window.py`](UI/main_window.py)).

### Model tab: Install dependencies (progress dialog)
- **Install dependencies** opens a frameless **Installing dependencies** dialog with **step labels** (PyTorch vs `requirements.txt`), a **progress bar** (**indeterminate** until pip prints tqdm-style `%` lines, then **0–100%** from parsed output), a **current action** line from `pip_line_hint` (Collecting / Downloading / Installing…), and a **scrolling log**. Close is disabled until the run finishes. Streaming uses [`src/torch_install.py`](src/torch_install.py): `run_subprocess_streaming` splits on `\r` and `\n` so same-line pip progress is visible; `pip install` invocations inject `--progress-bar on`; `pip_download_percent` maps lines to the bar. Implementation: [`UI/install_deps_dialog.py`](UI/install_deps_dialog.py).

### PyTorch dtype helper (LLM expand / transformers)
- **`src/torch_dtypes.py`**: central `torch_float16()` for BitsAndBytes / `from_pretrained` dtypes. If `import torch` is a **broken or stub** install (no `torch.float16`), raises a clear `RuntimeError` pointing to `scripts/install_pytorch.py --with-rest` instead of `AttributeError: module 'torch' has no attribute 'float16'`. Used from [`src/brain.py`](src/brain.py), [`src/factcheck.py`](src/factcheck.py), [`src/artist.py`](src/artist.py), [`src/clips.py`](src/clips.py). Tests: [`tests/test_torch_dtypes.py`](tests/test_torch_dtypes.py).

### Model tab: download all voice models
- **Download ▾ → Download all voice models** queues Hugging Face snapshots for every curated TTS option (Kokoro, MMS-TTS, MeloTTS, Microsoft SpeechT5, Parler-TTS, XTTS, Bark, …), skipping repos already under `models/`. Implementation: [`UI/main_window.py`](UI/main_window.py) (`_download_all_voice_models`), [`UI/tabs/settings_tab.py`](UI/tabs/settings_tab.py). Docs: [`docs/models.md`](docs/models.md), [`docs/ui.md`](docs/ui.md).

### Model tab: Auto-fit for this PC
- **Auto-fit for this PC** on the **Model** tab picks script / video / voice models from detected VRAM and RAM using `rank_models_for_auto_fit` in [`src/hardware.py`](src/hardware.py) (same rules as fit badges; SDXL Turbo is preferred over SD 1.5 when VRAM ≥ ~8 GB and Turbo is still OK). Skips disabled Hub rows; logs the selection and **saves settings**. Docs: [`docs/ui.md`](docs/ui.md). Tests: [`tests/test_auto_fit.py`](tests/test_auto_fit.py).

### Resource usage graph (fix)
- **Resource usage** (title bar 📈) sparklines crashed after the first second of data: `QBrush` was used for the area fill but not imported from `PyQt6.QtGui` ([`UI/resource_graph_dialog.py`](UI/resource_graph_dialog.py)).
- Timer updates (`_on_tick`) are wrapped in **try/except** so a bad sample tick does not tear down the main window.

### Terminal: activate venv (Windows)
- **[`scripts/setup_terminal_env.ps1`](scripts/setup_terminal_env.ps1)**: dot-source from the repo root (`. .\scripts\setup_terminal_env.ps1`) to **activate `.venv`** and `cd` to the project. Documents optional **`HF_TOKEN`** / Hub usage. See [`README.md`](README.md) and [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Voice models (download list)
- **Settings → Model → Voice** includes more Hugging Face TTS checkpoints for local snapshot download: **MMS-TTS English**, **MeloTTS English**, **SpeechT5**, **Parler-TTS mini v1**, and **Bark**, alongside existing **Kokoro 82M** and **coqui XTTS v2**. Same repos are listed in [`scripts/download_hf_models.py`](scripts/download_hf_models.py) `ALL_REPOS`. VRAM hints for **Bark** / **Parler** in [`src/hardware.py`](src/hardware.py). Docs: [`docs/models.md`](docs/models.md), [`docs/voice.md`](docs/voice.md), [`docs/model_youtube_demos.md`](docs/model_youtube_demos.md).

### Run tab: queue multiple pipeline jobs
- While a **pipeline** or **batch** run is active, clicking **Run** again **appends** another job to a FIFO queue (snapshot of settings + batch quantity at click time) instead of being ignored. Same for **Approve and run** (preview) and **approved storyboard render** when a pipeline is already running.
- When the current run **finishes** or **fails**, the next queued job starts after preflight (and FFmpeg readiness). **Stop** cancels the active run and **clears** any queued jobs, with a log line counting dropped items.
- Implementation: [`UI/main_window.py`](UI/main_window.py) (`_pipeline_run_queue`, `_try_start_next_queued_pipeline`, `_attach_and_start_pipeline_worker`). Docs: [`README.md`](README.md), [`docs/ui.md`](docs/ui.md). Tests: [`tests/test_ui_main_window.py`](tests/test_ui_main_window.py) (Qt), [`tests/test_pipeline_run_queue_contract.py`](tests/test_pipeline_run_queue_contract.py) (no Qt — queue payload shapes).

### Resource graph (title bar)
- Title bar **📈** between **💾 Save** and **✕**: opens a non-modal **Resource usage** window with sparkline graphs (this process CPU, RAM % of system, GPU VRAM % when CUDA is active), **1 second** refresh ([`src/resource_sample.py`](src/resource_sample.py), [`UI/resource_graph_dialog.py`](UI/resource_graph_dialog.py)). **`psutil`** is a runtime dependency.

### PyTorch install (auto CUDA / CPU)
- **`requirements.txt`**: single runtime list **without** `torch` (so CUDA wheels are not skipped). Consolidated former `requirements-base.txt` into this file.
- **[`src/torch_install.py`](src/torch_install.py)** + **[`scripts/install_pytorch.py`](scripts/install_pytorch.py)**: detect NVIDIA via `nvidia-smi` / WMI (Windows), install **`torch` / `torchvision` / `torchaudio`** from **CUDA 12.4** wheels when appropriate, else **CPU** wheels; **macOS** uses default PyPI. **`--with-rest`** runs `pip install -r requirements.txt` afterward. Replaces a CPU-only `torch` when a GPU is present (`pip uninstall` + reinstall).
- **Model tab** “Install dependencies” calls the same combined install ([`UI/main_window.py`](UI/main_window.py)). **[`build/build.ps1`](build/build.ps1)** and **[`scripts/setup_venv_one_by_one.ps1`](scripts/setup_venv_one_by_one.ps1)** use `install_pytorch.py --with-rest`. Docs: [`README.md`](README.md), [`DEPENDENCIES.md`](DEPENDENCIES.md).

### Video format: Cartoon (unhinged)
- **Pipeline mode** `video_format="unhinged"` (fourth option with News / Cartoon / Explainer): chaotic Gen‑Z–style cartoon comedy scripts, headline/query bias for comedy/absurdist animation topics (see [`src/crawler.py`](src/crawler.py)), and LLM steering via [`src/brain.py`](src/brain.py) (`_vf_hint`, dedicated unhinged prompt path).
- **TTS** ([`main.py`](main.py), [`src/voice.py`](src/voice.py)): with **local** pyttsx3 only, narration is split into beats (hook → segment narrations → CTA); each beat uses a **rotating** system voice (round-robin, max **12** distinct voices), segment WAVs are **concatenated** to `assets/voice.wav`, and word timestamps are **merged** in `captions.json`. If the active **character** turns off default voice (custom voice) or uses **ElevenLabs**, the pipeline keeps a **single** `synthesize()` pass for the full narration (no rotation).

### Frameless dialogs (match main window)
- **Alerts and modal popups** use a shared borderless shell ([`UI/frameless_dialog.py`](UI/frameless_dialog.py)): custom title bar, **✕** close button (`#closeBtn`), drag by title bar only, rounded panel via `QDialog#FramelessDialogShell` in [`UI/theme.py`](UI/theme.py).
- Replaces native **`QMessageBox`** across the app (main window, Characters, brain expand, etc.). **Hugging Face token** prompt, **Preview** / **Storyboard Preview** dialogs, and **Topics → Discover** pickers use **`FramelessDialog`** or helpers (`aquaduct_information`, `aquaduct_warning`, `aquaduct_question`, `aquaduct_message_with_details`, `show_hf_token_dialog`). **Native file pickers** (`QFileDialog`) unchanged.
- **Tests**: existing UI tests unchanged; run `pytest tests/test_ui_workers.py tests/test_ui_download_pause.py tests/test_ui_main_window.py` (or full suite with `pytest -q`).

### Run tab: Custom video instructions (Preset vs Custom)
- **Content source** on **Run**: **Preset** keeps the existing flow (news cache + topic tags + personality). **Custom** uses multiline **video instructions** you write; the app does **not** pick headlines from the cache for that run. The script model runs twice: **expand** rough notes into a structured creative brief (plain text), then **generate** the same JSON `VideoPackage` the rest of the pipeline consumes (slower than Preset). Topic tags from the Topics tab still bias hashtags when relevant.
- **Settings** ([`src/config.py`](src/config.py), [`src/ui_settings.py`](src/ui_settings.py)): `run_content_mode` (`preset` | `custom`), `custom_video_instructions` (capped length `MAX_CUSTOM_VIDEO_INSTRUCTIONS`).
- **Orchestration** ([`main.py`](main.py)): Custom mode builds synthetic `sources` for metadata (`source: "custom"`), skips article fetch, calls [`src/brain.py`](src/brain.py) `expand_custom_video_instructions` then `generate_script(..., creative_brief=..., video_format=...)`. **Auto** personality uses instruction text in [`src/personality_auto.py`](src/personality_auto.py) `extra_scoring_text`. **Factcheck** `rewrite_with_uncertainty` is skipped when there is no article (Custom-only scripts).
- **UI** ([`UI/tabs/run_tab.py`](UI/tabs/run_tab.py), [`UI/main_window.py`](UI/main_window.py)): Preset/Custom radio + instructions editor; **Preview** / **Storyboard preview** / **Run** require non-empty instructions in Custom mode.
- **Workers** ([`UI/workers.py`](UI/workers.py)): `PreviewWorker` and `StoryboardWorker` mirror the same Custom vs Preset branching as `run_once`.
- **Tests**: [`tests/test_brain.py`](tests/test_brain.py) (creative-brief prompt path), [`tests/test_brain_expand.py`](tests/test_brain_expand.py) (`expand_custom_video_instructions`), [`tests/test_config_and_settings.py`](tests/test_config_and_settings.py) (settings roundtrip), [`tests/test_ui_workers.py`](tests/test_ui_workers.py) (`PreviewWorker` custom path skips news cache). [`tests/test_ui_download_pause.py`](tests/test_ui_download_pause.py) dummy download worker updated for `ModelDownloadWorker(..., remote_bytes_by_repo=...)`.

### Tasks: pipeline progress + pause/stop
- **Tasks** tab **Status** column shows **stage + percent** (e.g. `Pipeline: Writing script (LLM)… — 22%`) during runs, not only “Running…”. Emitted from [`main.py`](main.py) `run_once(..., on_progress=)` → [`UI/workers.py`](UI/workers.py) `PipelineWorker.progress` / batch remapped `PipelineBatchWorker.progress`; labels in [`UI/progress_tasks.py`](UI/progress_tasks.py) (`pipeline_run`, `pipeline_video`).
- **Pause** / **Resume** and **Stop** while a pipeline, batch run, Preview, or Storyboard job is active (cooperative cancel between steps via [`src/pipeline_control.py`](src/pipeline_control.py); `main.run_once` checkpoints). Stop also requests `QThread` interruption.
- **`tests/test_pipeline_control.py`**: unit tests for pause/cancel behavior.

### Model tab: integrity badges + result dialog
- After **Download ▾ → Verify checksums**, results are stored in [`data/model_integrity_status.json`](data/model_integrity_status.json) (gitignored) and shown on each model row: **✓ Verified**, **✗ Missing files**, **✗ Corrupt**, **✗ Missing & corrupt**, **⚠ Verify error**, or **✓ On disk** when snapshots exist but checksums were never run. Helpers: [`src/model_integrity_cache.py`](src/model_integrity_cache.py).
- Verification completion opens a **readable popup** (summary + “Show Details…” full log), not only the activity log ([`UI/main_window.py`](UI/main_window.py)).
- **`tests/test_model_integrity.py`**: integrity cache classification; [`tests/test_brain_expand.py`](tests/test_brain_expand.py) covers `expand_custom_field_text` with mocked generation.

### LLM “brain” on custom text fields
- **`UI/brain_expand.py`**: 🧠 button on the corner of supported fields runs [`src/brain.py`](src/brain.py) **`expand_custom_field_text`** in [`UI/workers.py`](UI/workers.py) **`TextExpandWorker`** (uses **Script model (LLM)** from the Model tab).
- Wired on **Characters** (identity, visual style, negatives), **Topics** tag input, and **Storyboard Preview** scene prompt (when the dialog has a main window parent).

### Characters tab layout
- Denser spacing, shorter list, horizontal Add/Duplicate/Delete row, capped text areas ([`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py)).

### Characters + ElevenLabs TTS
- **Characters** tab: create, edit, and delete user-defined **characters** (name, identity, visual style, negative prompts, per-character voice options). Persisted locally as `data/characters.json` (gitignored).
- **Run** tab: **Character** dropdown; chosen character feeds **LLM script context** and optional **storyboard** character consistency ([docs/characters.md](docs/characters.md)).
- **API** tab: **ElevenLabs** — enable + API key (optional `ELEVENLABS_API_KEY` env). When enabled and a character has an **ElevenLabs voice** selected, **cloud TTS** is used (MP3 → WAV via FFmpeg); on failure or missing key, the pipeline falls back to Kokoro/pyttsx3 ([docs/elevenlabs.md](docs/elevenlabs.md)).
- Implementation: [`src/characters_store.py`](src/characters_store.py), [`src/elevenlabs_tts.py`](src/elevenlabs_tts.py), [`src/voice.py`](src/voice.py) `synthesize`, [`main.py`](main.py) run wiring, [`UI/tabs/characters_tab.py`](UI/tabs/characters_tab.py), [`UI/workers.py`](UI/workers.py) async voice list refresh.
- **Tests**: [`tests/test_characters_store.py`](tests/test_characters_store.py), [`tests/test_elevenlabs_tts.py`](tests/test_elevenlabs_tts.py) (mocked HTTP); settings/preflight tests extended for new fields.

### Packaging (Windows one-file EXE)
- [`build/build.ps1`](build/build.ps1) and [`aquaduct-ui.spec`](aquaduct-ui.spec): extra `--hidden-import` / `collect_all` for HTTPS (`requests`, `urllib3`, `certifi`, `charset_normalizer`), `pyttsx3`, `src.elevenlabs_tts`, `src.characters_store`, and UI tab modules; bundle `docs/*.md` for UI builds. Still bundles `imageio`/related metadata and submodules for `src` / `UI`; UI EXE supports **`-debug` / `--debug`** for a console. See [build/README.md](build/README.md).

### Fixes
- [`main.py`](main.py): removed a redundant inner `import ensure_ffmpeg` inside `run_once` that shadowed the top-level import and caused `UnboundLocalError` when FFmpeg was missing at startup.

### Tasks + TikTok
- **Tasks** tab: queued finished videos (`data/upload_tasks.json`), open/play, copy caption, manual “posted”, remove; auto-listed after each successful run.
- **API** tab: **TikTok** section (OAuth PKCE + local callback, inbox upload via Content Posting API). Optional **auto-start TikTok upload** when a render completes.
- See [docs/tiktok.md](docs/tiktok.md).

### Tasks + YouTube (Shorts / Data API v3)
- **Separate enable** from TikTok: **`youtube_enabled`** and its own OAuth client (default loopback port **8888**, vs TikTok **8765**).
- **API** tab: **YouTube** section — client ID/secret, redirect URI, default privacy, optional **#Shorts** in title/description, optional **auto-upload after render**.
- **Tasks** tab: **YouTube** status column, **Upload to YouTube**; uploads via resumable `videos.insert` (`src/youtube_upload.py`, `UI/workers.py` `YouTubeUploadWorker`).
- See [docs/youtube.md](docs/youtube.md).

### Model integrity (checksums)
- **Model** tab → **Download ▾**: **Verify checksums** for selected installed models or for **all** folders under `models/`.
- Uses `huggingface_hub.HfApi.verify_repo_checksums` (SHA-256 for LFS weights, git blob ids for small files); needs network + HF auth for gated repos.
- Implementation: `src/model_manager.py` (`verify_project_model_integrity`, `list_installed_repo_ids_from_disk`), `UI/workers.py` `ModelIntegrityVerifyWorker`.

### Topics and video format
- **Per-format topic lists**: `AppSettings.topic_tags_by_mode` stores tags separately for `news`, `cartoon`, and `explainer`. The active list for a run comes from `video_format` via `src/topics.py` (`effective_topic_tags()`). Legacy flat `topic_tags` in `ui_settings.json` is migrated into `topic_tags_by_mode["news"]` on load.
- **Run tab**: **Video format** combo (News / Cartoon / Explainer) chooses both the pipeline mode and which topic list applies; hint text explains the link to the Topics tab.
- **Topics tab**: **Mode** selector edits one list at a time; **Discover** (headline-based topic suggestions) uses the **selected mode’s** tag list and adds approved picks to that list (not News-only).

### News cache (dedupe)
- **Per-format seen files**: URL and title-history caches are split by format — `data/news_cache/seen_<mode>.json` and `seen_titles_<mode>.json` (for example `seen_news.json`, `seen_cartoon.json`). Legacy flat `seen.json` / `seen_titles.json` is read once to seed **news** when the per-mode file is missing.
- **Clear cache** (Video tab): removes legacy files and all `seen_*.json` / `seen_titles_*.json` in `data/news_cache/`. Implementation: `src/crawler.py` `clear_news_seen_cache_files()` (used by the desktop UI).

### Crawler / API
- Optional **Firecrawl** integration for search/scrape (`src/firecrawl_news.py`); configurable in the app **API** tab and env (`FIRECRAWL_API_KEY`).
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
- Initial MVP scaffold: crawler → local script generation → local TTS + captions → SDXL Turbo images → micro-clip editor → per-video outputs under `videos/`.
