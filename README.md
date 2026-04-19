# Aquaduct (MVP)

This project builds **Aquaduct**, a **local-first** tool (with optional **API execution mode** for OpenAI / Replicate script, images, and cloud video — see [docs/api_generation.md](docs/api_generation.md)) that:
- scrapes AI tool news (no paid APIs)
- writes a short vertical video script locally (LLM in 4-bit when possible)
- generates images locally (SDXL Turbo, FP16)
- generates voice locally (Kokoro-82M target; with safe fallback if unavailable)
- assembles a **9:16** MP4 as **few-second micro-scenes** (slideshow) or **scene**-based motion / Pro video, with word-by-word captions

## Table of contents
- [Starter guide](#starter-guide)
- [Project layout](#project-layout)
- [Outputs](#outputs)
- [Desktop UI (PyQt6)](#desktop-ui-pyqt6)
- [Build Windows EXE](#build-windows-exe)
- [Build & verify (operator)](docs/building_windows_exe.md)
- [Performance notes](docs/performance.md)
- [Docs](#docs)
- [Changelog](CHANGELOG.md)
- [Dependencies](DEPENDENCIES.md)

## Starter guide

### 1) Install

PyTorch is installed **before** the rest of the stack so pip can use **CUDA wheels** when an NVIDIA GPU is detected (otherwise CPU wheels; macOS uses PyPI).

```powershell
cd d:\Aquaduct
python -m venv .venv
.\.venv\Scripts\activate
python scripts/install_pytorch.py --with-rest
```

Optional — activate **and** `cd` to the repo in one step (PowerShell):

```powershell
cd d:\Aquaduct
. .\scripts\setup_terminal_env.ps1
```

### Tests

```powershell
pip install -r requirements.txt -r requirements-dev.txt
pytest -q -m "not qt"
```

(`torch` / CUDA wheels: use `python scripts/install_pytorch.py --with-rest` before or as documented in `requirements.txt`.)

`tests/test_pipeline_run_queue_contract.py` exercises pipeline **run-queue** payload shapes (no Qt; runs under `pytest -m "not qt"`). Queue behavior on the main window is in `tests/test_ui_main_window.py` (needs PyQt6 + pytest-qt from `requirements-dev.txt`). API / packaging import smoke: `tests/test_import_smoke_api.py`.

Run **Qt-only** UI tests:

```powershell
pytest -q -m qt
```

Run **all** tests (including `@pytest.mark.qt` UI tests; needs PyQt6 + pytest-qt):

```powershell
pytest -q
```

If a Qt-related test crashes with an access violation on some Windows/Python builds, run the headless subset above; core pipeline tests are in the non-`qt` set. For a short table of tiers, see **Test tiers** in [`DEPENDENCIES.md`](DEPENDENCIES.md).

### 2) Run once (recommended for first test)

```powershell
python main.py --once
```

### 2b) Run the desktop UI

```powershell
python -m UI
```

(Alternative: `python UI/ui_app.py`)

### 3) Run continuously (every 4 hours)

```powershell
python main.py
```

### 4) Optional: add background music

```powershell
python main.py --once --music "D:\path\to\music.mp3"
```

## Quickstart (Windows, Python 3.11+)

```powershell
cd d:\Aquaduct
python -m venv .venv
.\.venv\Scripts\activate
python scripts/install_pytorch.py --with-rest
python main.py --once
```

Same folder, optional: `. .\scripts\setup_terminal_env.ps1` after `cd` to activate `.venv` (see [`scripts/setup_terminal_env.ps1`](scripts/setup_terminal_env.ps1)).

## Project layout
- `main.py`: one-shot run (`--once`) or infinite loop (default); `python main.py <subcommand>` for [headless CLI](docs/cli.md)
- `src/`: pipeline modules
- `UI/`: PyQt6 desktop UI package (TikTok-style theme; tabs under `UI/tabs/`; launcher `UI/ui_app.py`)
- `Model-Downloads/`: generator + README for **offsite** model download bundles (generated `offsite/` output is gitignored — see [Model-Downloads/README.md](Model-Downloads/README.md))
- `data/upload_tasks.json`: local queue for finished renders (Tasks tab); gitignored
- `data/characters.json`: Character Builder profiles (Tasks/Run); gitignored
- `data/news_cache/`: URL + title dedupe caches (`seen_<mode>.json`, `seen_titles_<mode>.json`; legacy `seen.json` may still appear until cleared or migrated)
- `runs/`: intermediate working folders per run
- `videos/`: final per-video folders

## Outputs
Outputs land in:
- `videos/<safe_video_title>/final.mp4`
- `videos/<safe_video_title>/script.txt`
- `videos/<safe_video_title>/hashtags.txt`
- `videos/<safe_video_title>/meta.json`
- `videos/<safe_video_title>/assets/` (voice, captions, images, intermediate scene MP4s when enabled, etc.)

Intermediate artifacts land in:
- `runs/<run_id>/...`

## Desktop UI (PyQt6)
Run:

```powershell
python -m UI
```

Alerts, confirmations, and most modal dialogs are **borderless** with a custom **✕** (same look as the main window); native **file/folder** pickers stay OS-standard.

Tabs:
- **Run**: set **Videos to generate** to queue **that many independent full runs** (each produces one video); **click Run while a job is running** to **queue** more runs (FIFO; settings snapshotted per click). **Stop** clears the queue. **Preset** (news cache + topics) vs **Custom** (your instructions, two LLM passes) + **video format** (News / Cartoon / Explainer / Cartoon unhinged) + **Personality** + optional **Character** + open `videos/`
- **Topics**: topic tags **per format** (mode selector); optional **🧠** expand on the tag line (local LLM); **Discover** suggests tags from Firecrawl results (**Cartoon** / **Unhinged**: memes/jokes/story pages + saved pack under `data/topic_research/`; **News** / **Explainer**: headline-style). Approved picks are added to that format’s list ([UI](docs/ui.md), [Crawler](docs/crawler.md))
- **Characters**: create/edit **characters** (identity, visuals, voice); optional **🧠** expand on multi-line fields; optional **ElevenLabs** voice when API is enabled
- **Tasks**: finished videos queue; live **stage + %** on the active row; **Pause** / **Stop** for long jobs; open/play, copy caption; **TikTok** and **YouTube** uploads when enabled (separate API toggles)
- **Library**: browse **`videos/`** folders with **`final.mp4`** (open folder, **`assets/`**, play) and **`runs/`** workspaces (intermediate files); refresh or open the **`videos/`** / **`runs/`** roots
- **Video**: **platform template tiles** (social presets + Custom), **resolution**, FPS, micro-scene timing, bitrate, slideshow vs **motion (scene) mode**, optional **NSFW allow** for diffusion, performance toggles, music, cache utilities
- **API**: Hugging Face token (optional), **Firecrawl** toggle and key, **ElevenLabs** (optional cloud TTS), **TikTok** OAuth + upload settings, **YouTube** OAuth + upload settings (independent enables)
- **Branding**: theme palette overrides (presets sync hex rows) + logo watermark
- **Model**: **Local \| API** toggle; **Model files location** (**Default** \| **External** folder for Hub snapshots); Download menu (including **verify checksums** + result dialog); **Verified / Missing / Corrupt** badges after checks; **Install dependencies** (modal: live pip log + progress bar with **%** when pip reports it); dependency check; model select/download (script/video/voice); skips repos already present on disk under the active models folder
- **My PC**: hardware summary + model fit markers (VRAM-based heuristics)

Optional: pre-download HF snapshots without the UI — `python scripts/download_hf_models.py` (see [Models + downloads](docs/models.md)).

## Build Windows EXE
- Build script: [`build/build.ps1`](build/build.ps1) (canonical onedir/onefile flags + post-build smoke)
- Portable spec: [`aquaduct-ui.spec`](aquaduct-ui.spec) (optional: `.\build\build.ps1 -Clean -UI -UseSpec`)
- Operator guide: [`docs/building_windows_exe.md`](docs/building_windows_exe.md)
- Build reference: [`build/README.md`](build/README.md)

Example:

```powershell
.\build\build.ps1 -Clean
```

## Docs
- [Headless CLI](docs/cli.md) (`run`, `preflight`, `config`, `models`, `tasks`, `version`)
- [API execution mode](docs/api_generation.md)
- [Build & verify Windows EXE](docs/building_windows_exe.md)
- [Performance (import / cold start)](docs/performance.md)
- [Crawler](docs/crawler.md)
- [Brain (LLM scripting)](docs/brain.md)
- [Voice (TTS + captions)](docs/voice.md)
- [Artist (images)](docs/artist.md)
- [Editor (micro-scenes + captions)](docs/editor.md)
- [Main loop / CLI](docs/main.md)
- [Config](docs/config.md)
- [Desktop UI](docs/ui.md) (includes **Video** platform preset tiles and NSFW toggle)
- [Branding (theme + watermark)](docs/branding.md)
- [Models + downloads](docs/models.md)
- [Hardware + model fit rules](docs/hardware.md)
- [FFmpeg auto-download](docs/ffmpeg.md)
- [VRAM / cleanup utilities](docs/vram.md)
- [TikTok upload (Tasks + API)](docs/tiktok.md)
- [YouTube upload (Tasks + API)](docs/youtube.md)
- [Characters (Character Builder)](docs/characters.md)
- [ElevenLabs TTS (optional)](docs/elevenlabs.md)

## Notes
- First run will download models from Hugging Face (can be large).
- GPU memory is limited (8GB): the pipeline loads/unloads models between stages.

