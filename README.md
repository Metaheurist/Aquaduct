# Local AI News Factory (MVP)

This project builds a **fully local** “AI News Factory” that:
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
- `data/news_cache/seen.json`: URL dedupe cache
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
- **Run**: one-shot run + logs + open `videos/`
- **Topics**: add/remove free-text topic tags
- **Video**: output quality knobs (FPS, micro-clip timing, bitrate, images per video)
- **Quality**: toggles for “try LLM 4-bit” / “try SDXL Turbo”
- **Advanced**: background music picker + clear seen cache
- **Settings**: dependency check/install + model select/download (script/video/voice)
- **My PC**: hardware summary + model fit markers (VRAM-based heuristics)

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
- [Models + downloads](docs/models.md)
- [Hardware + model fit rules](docs/hardware.md)
- [FFmpeg auto-download](docs/ffmpeg.md)
- [VRAM / cleanup utilities](docs/vram.md)

## Notes
- First run will download models from Hugging Face (can be large).
- GPU memory is limited (8GB): the pipeline loads/unloads models between stages.

