# `main.py` — Orchestrator / CLI

## Purpose
**Aquaduct**’s orchestrator (`main.py`) runs the full pipeline:
1. Crawl news (deduped per `video_format`; see [Crawler](crawler.md)) — **skipped when `AppSettings.run_content_mode == "custom"`**; the run uses synthetic `sources` metadata and instructions from `custom_video_instructions` instead
2. Generate a structured script package (LLM or fallback); optional **character** context from settings ([Characters](characters.md)). In **custom** mode, `src/content/brain.py` first expands instructions (`expand_custom_video_instructions`), then `generate_script(..., creative_brief=..., video_format=...)`. Optional LLM factcheck rewrite applies when article text exists (preset runs with fetched text)
3. TTS + captions ([Voice](voice.md): Kokoro target, `pyttsx3` fallback, optional ElevenLabs when configured)
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

### Desktop UI (default)
With no `--once` and no `--cli`, `python main.py` launches the **Aquaduct** PyQt6 window. Use `python main.py --cli --once` (or `--cli` with the loop) for headless CLI-only runs.

