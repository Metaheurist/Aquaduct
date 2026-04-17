# Aquaduct (MVP)

This project builds **Aquaduct**, a **fully local** tool that:
- scrapes AI tool news (no paid APIs)
- writes a short vertical video script locally (LLM in 4-bit when possible)
- generates images locally (SDXL Turbo, FP16)
- generates voice locally (Kokoro-82M target; with safe fallback if unavailable)
- assembles a **9:16** MP4 as **few-second micro-clips** with word-by-word captions

## Table of contents
- [Starter guide](#starter-guide)
- [Project layout](#project-layout)
- [Outputs](#outputs)
- [Desktop UI (PyQt6)](#desktop-ui-pyqt6)
- [Build Windows EXE](#build-windows-exe)
- [Docs](#docs)
- [Changelog](CHANGELOG.md)
- [Dependencies](DEPENDENCIES.md)

## Starter guide

### 1) Install

```powershell
cd d:\Aquaduct
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Tests

```powershell
pip install -r requirements.txt -r requirements-dev.txt
pytest -q -m "not qt"
```

Run **all** tests (including `@pytest.mark.qt` UI tests; needs PyQt6 + pytest-qt):

```powershell
pytest -q
```

If a Qt-related test crashes with an access violation on some Windows/Python builds, run the headless subset above; core pipeline tests are in the non-`qt` set.

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
pip install -r requirements.txt
python main.py --once
```

## Project layout
- `main.py`: one-shot run (`--once`) or infinite loop (default)
- `src/`: pipeline modules
- `UI/`: PyQt6 desktop UI package (TikTok-style theme; tabs under `UI/tabs/`; launcher `UI/ui_app.py`)
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
- `videos/<safe_video_title>/assets/` (voice, captions, images, micro-clips)

Intermediate artifacts land in:
- `runs/<run_id>/...`

## Desktop UI (PyQt6)
Run:

```powershell
python -m UI
```

Tabs:
- **Run**: one-shot run + **Preset** (news cache + topics) vs **Custom** (your instructions, two LLM passes) + **video format** (News / Cartoon / Explainer) + **Personality** + optional **Character** + open `videos/`
- **Topics**: topic tags **per format** (mode selector); optional **🧠** expand on the tag line (local LLM); **Discover** biases headlines on the selected format’s tag list and adds picks to that list
- **Characters**: create/edit **characters** (identity, visuals, voice); optional **🧠** expand on multi-line fields; optional **ElevenLabs** voice when API is enabled
- **Tasks**: finished videos queue; live **stage + %** on the active row; **Pause** / **Stop** for long jobs; open/play, copy caption; **TikTok** and **YouTube** uploads when enabled (separate API toggles)
- **Video**: output + quality knobs (format presets, FPS, micro-clip timing, bitrate, slideshow/clip mode, performance toggles, music, cache utilities)
- **API**: Hugging Face token (optional), **Firecrawl** toggle and key, **ElevenLabs** (optional cloud TTS), **TikTok** OAuth + upload settings, **YouTube** OAuth + upload settings (independent enables)
- **Branding**: theme palette overrides (presets sync hex rows) + logo watermark
- **Model**: Download menu (including **verify checksums** + result dialog); **Verified / Missing / Corrupt** badges after checks; dependency check/install; model select/download (script/video/voice); skips repos already under `models/`
- **My PC**: hardware summary + model fit markers (VRAM-based heuristics)

Optional: pre-download HF snapshots without the UI — `python scripts/download_hf_models.py` (see [Models + downloads](docs/models.md)).

## Build Windows EXE
- Build docs: [`build/README.md`](build/README.md)
- Build script: `build/build.ps1`

Example:

```powershell
.\build\build.ps1 -Clean
```

## Docs
- [Crawler](docs/crawler.md)
- [Brain (LLM scripting)](docs/brain.md)
- [Voice (TTS + captions)](docs/voice.md)
- [Artist (images)](docs/artist.md)
- [Editor (micro-clips + captions)](docs/editor.md)
- [Main loop / CLI](docs/main.md)
- [Config](docs/config.md)
- [Desktop UI](docs/ui.md)
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

