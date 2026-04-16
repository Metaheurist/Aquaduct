# Desktop UI (PyQt6)

## Layout
- Package: [`UI/`](../UI/) (theme, workers, main window, `tabs/` per screen)
- Launcher script: [`UI/ui_app.py`](../UI/ui_app.py) (same as `python -m UI`)

## Purpose
Provide a desktop control panel for **Aquaduct** with a **TikTok-style dark theme** and tabbed settings.

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
  - **Video format** (News / Cartoon / Explainer): together with Topics, selects which tag list the pipeline uses (`video_format` + `topic_tags_by_mode`)
  - Open `videos/` folder
  - Save settings
- **Topics**
  - **Mode** combo matches video formats; each mode has its own tag list (stored in `ui_settings.json` under `topic_tags_by_mode`)
  - Add/remove tags for the **selected mode** only
  - **Discover**: fetches headline-based topic suggestions using the **News** tag list; enabled when the Topics mode is News
- **Video**
  - Images per video
  - Video format presets (resolution/aspect)
  - Clip mode vs slideshow mode
  - FPS
  - Micro-clip min/max seconds
  - Bitrate preset (low/med/high)
  - Export intermediate micro-clips toggle
  - Delete generated images after run (save storage)
- Quality/performance and advanced controls live under **Video**:
  - Prefer GPU toggle (advisory)
  - Try 4-bit LLM toggle (advisory; pipeline falls back if unavailable)
  - Try SDXL Turbo toggle (advisory; pipeline falls back if unavailable)
  - Background music picker
  - Clear news URL/title cache: removes legacy `seen.json` / `seen_titles.json` and all `seen_*.json` / `seen_titles_*.json` under `data/news_cache/`
- **Branding**
  - Optional full-theme palette overrides (presets or custom hex + color picker). Changing the **Palette** dropdown updates the hex swatches and fields for that preset (Custom unlocks per-row overrides).
  - Optional logo watermark on generated videos
- **API**
  - Optional **Firecrawl** toggle and API key (or `FIRECRAWL_API_KEY` in the environment) for richer news search and article scrape when configured
- **Settings**
  - **Download ▾** menu: download the currently selected model(s), **download all selected** (script + image/video + voice choices in one queue), **download all models** (full curated list), plus **check Python dependencies** / **install dependencies** from `requirements.txt`.
  - Model dropdowns show local install status and Hub probe hints; downloads **skip** repos that already have a valid snapshot under `models/` and continue with the rest.
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
- default cyan accent `#25F4EE`
- default pink/red accent `#FE2C55`
- optional palette overrides configured in the Branding tab

