# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

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
- Docs refreshed for UI downloads, branding palette behavior, models/skip semantics, **TikTok**, **YouTube**, **checksum verification**, **Characters**, and **ElevenLabs**.
- **`tests/test_personality_auto.py`** updated for rules-only auto pick.
- **`tests/test_upload_tasks.py`**, **`tests/test_tiktok_post.py`**, **`tests/test_model_integrity.py`** for tasks/TikTok/verification coverage. UI tests need **`pip install -r requirements-dev.txt`** (pytest-qt + PyQt6 for `qtbot`).

## 0.1.0 — 2026-04-15
- Initial MVP scaffold: crawler → local script generation → local TTS + captions → SDXL Turbo images → micro-clip editor → per-video outputs under `videos/`.
