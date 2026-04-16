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
  - **Personality** (preset or Auto) and optional **Character** (see Characters tab) for script + storyboard consistency
  - Live pipeline / preview / storyboard progress is shown as the **top row** on the **Tasks** tab (no progress bar on Run)
  - Open `videos/` folder
  - Save settings
- **Topics**
  - **Mode** combo matches video formats; each mode has its own tag list (stored in `ui_settings.json` under `topic_tags_by_mode`)
  - Add/remove tags for the **selected mode** only
  - **Discover**: fetches headline-based topic suggestions using the **current “Edit tags for”** mode’s tag list; approved items are added to that mode’s list
- **Tasks**
  - Lists successful renders (`data/upload_tasks.json`): open folder, play `final.mp4`, copy caption from `meta.json` / `hashtags.txt`, mark posted manually, **Upload to TikTok** (inbox) and/or **Upload to YouTube** when the **API** tab is configured (separate toggles); optional auto-uploads per platform after each render
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
- **Characters**
  - Create, edit, and delete **characters** (name, identity, visual style, negative prompts, voice overrides). Stored in `data/characters.json` (local; not committed).
  - Optional **ElevenLabs voice** picker when **API → ElevenLabs** is enabled and a key is set ([ElevenLabs](elevenlabs.md), [Characters](characters.md)).
- **API**
  - Hugging Face token (optional; helps Hub size checks and gated downloads) + optional **Firecrawl**
  - **ElevenLabs** (optional): enable + API key for cloud TTS when a character selects an ElevenLabs voice — see [ElevenLabs](elevenlabs.md)
  - **TikTok**: client key/secret, redirect URI + OAuth port, publishing mode (inbox vs direct; inbox is supported for upload), optional **auto-upload after each render** — see [TikTok upload](tiktok.md)
  - **YouTube**: separate enable; OAuth client ID/secret, redirect + port (default **8888**), default visibility, optional **#Shorts** tagging, optional **auto-upload after render** — see [YouTube upload](youtube.md)
- **Model** (tab label; model downloads + dependencies)
  - **Download ▾** menu: download the currently selected model(s), **download all selected** (script + image/video + voice choices in one queue), **download all models** (full curated list), **verify checksums** for installed snapshots (selected or all under `models/`), plus **check Python dependencies** / **install dependencies** from `requirements.txt`.
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

