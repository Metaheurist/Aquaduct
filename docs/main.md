# `main.py` — Orchestrator / CLI

## Purpose
**Aquaduct**’s orchestrator (`main.py`) runs the full pipeline:
1. Crawl news (deduped per `video_format`; see [Crawler](crawler.md)) — **skipped when `AppSettings.run_content_mode == "custom"`**; the run uses synthetic `sources` metadata and instructions from `custom_video_instructions` instead
2. Generate a structured script package (LLM or fallback); optional **character** context from settings ([Characters](characters.md)). In **custom** mode, `src/content/brain.py` first expands instructions (`expand_custom_video_instructions`), then `generate_script(..., creative_brief=..., video_format=...)`. Optional LLM factcheck rewrite applies when article text exists (preset runs with fetched text)
3. TTS + captions ([Voice](voice.md): Kokoro target, `pyttsx3` fallback, optional ElevenLabs when configured)
4. Images
5. Edit micro-scenes (slideshow) or concatenate motion / Pro **scene** segments + final MP4
6. Write per-video outputs under `videos/<safe_video_title>/`

It also exposes a `run_once(settings: AppSettings)` function that the desktop UI calls.

For **Cartoon** and **Cartoon (unhinged)** preset runs, when **Gather web context** and/or **Download reference images** is enabled on the Video tab, `run_once` prepends the latest **Topics → Discover** research digest from **`data/topic_research/<mode>/`** into the Firecrawl `build_script_context` `extra_markdown` bundle (same helper as storyboard preview in [`UI/workers.py`](../UI/workers.py)); see [Crawler](crawler.md).

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

### Structured headless CLI (subcommands)
For cloud / SSH / automation, use subcommands that share **`ui_settings.json`** with the desktop app: `run`, `preflight`, `config`, `models`, `tasks`, `version`. The watch loop reloads settings from disk each iteration (same as saving in the UI). See **[CLI reference](cli.md)** (`python main.py help`).

## Performance

Import-time and cold-start notes (including `main`, `pipeline_api`, and `UI.app` profiling) are summarized in [performance.md](performance.md). Packaging verification for frozen builds: [building_windows_exe.md](building_windows_exe.md).

