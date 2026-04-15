# `main.py` — Orchestrator / CLI

## Purpose
Runs the full pipeline:
1. Crawl news (deduped)
2. Generate a structured script package (LLM or fallback)
3. TTS + captions
4. Images
5. Edit micro-clips + final MP4
6. Write per-video outputs under `videos/<safe_video_title>/`

It also exposes a `run_once(settings: AppSettings)` function that the desktop UI calls.

## Commands

### Run once (recommended for testing)
```powershell
python main.py --once
```

### Run continuously (every 4 hours)
```powershell
python main.py
```

### Change interval
```powershell
python main.py --interval-hours 2
```

### Add background music
```powershell
python main.py --once --music "D:\path\to\music.mp3"
```

