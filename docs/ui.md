# Desktop UI (PyQt6)

## Layout
- Package: [`UI/`](../UI/) (theme, workers, main window, `tabs/` per screen)
- Launcher script: [`UI/ui_app.py`](../UI/ui_app.py) (same as `python -m UI`)

## Purpose
Provide a desktop control panel for the factory with a **TikTok-style dark theme** and tabbed settings.

## How to run

```powershell
python -m UI
```

Or:

```powershell
python UI/ui_app.py
```

## Tabs
- **Run**
  - One-shot run button
  - Live log output
  - Open `videos/` folder
  - Save settings
- **Topics**
  - Add/remove free-text topic tags (stored in `ui_settings.json`)
- **Video**
  - Images per video
  - FPS
  - Micro-clip min/max seconds
  - Bitrate preset (low/med/high)
  - Export intermediate micro-clips toggle
- **Quality**
  - Prefer GPU toggle (advisory)
  - Try 4-bit LLM toggle (advisory; pipeline falls back if unavailable)
  - Try SDXL Turbo toggle (advisory; pipeline falls back if unavailable)
- **Advanced**
  - Background music picker
  - Clear `data/news_cache/seen.json`
- **Settings**
  - Dependency check (import test)
  - Dependency install (runs `pip install -r requirements.txt`)
  - Model selection + download buttons
- **My PC**
  - Hardware summary (CPU/RAM/GPU/VRAM, best-effort)
  - Minimum requirements guidance
  - Per-model fit markers based on simple VRAM rules

## Settings persistence
Saved to:
- `ui_settings.json` (repo root)

## Theme
Applied via a global Qt stylesheet (QSS) with:
- near-black backgrounds
- cyan accent `#25F4EE`
- pink/red accent `#FE2C55`

