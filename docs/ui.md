# Desktop UI (PyQt6)

## Layout
- Package: [`UI/`](../UI/) (theme, workers, main window, `tabs/` per screen)
- **Title bar** (frameless window): drag by the title row; **💾** saves settings; **📈** opens a live **resource usage** graph (this process CPU / RAM / GPU VRAM when CUDA is on, 1s updates); **✕** closes the app.
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
  - **Run** button: starts the pipeline (or a **batch** of N videos from the quantity spin). If a pipeline is **already running**, another click **queues** another run (FIFO). Each queued job stores **settings + quantity** (or preview/storyboard payloads) from when you clicked. **Stop** cancels the current job and **drops** the queue. While a run is active, **Run** stays enabled so you can enqueue more jobs.
  - **Content source**: **Preset (news cache + topics)** uses the deduped headline cache and per-format topic tags (same as before). **Custom (your instructions)** uses a multiline text box: the script LLM **expands** your notes into a creative brief, then **writes** the structured `VideoPackage` (two LLM passes — slower than Preset). Custom mode does **not** pick headlines from the cache; topic tags still bias hashtags when relevant. Instructions are stored in settings (`run_content_mode`, `custom_video_instructions`; length capped). Run / Preview / Storyboard preview require non-empty instructions when Custom is selected.
  - **Video format** (News / Cartoon / Explainer / **Cartoon (unhinged)**): together with Topics, selects which tag list the pipeline uses (`video_format` + `topic_tags_by_mode`). **Cartoon (unhinged)** favors chaotic comedy/absurdist animation headlines and rotating **local** pyttsx3 voices per script beat; if a character uses **ElevenLabs** (or a custom non-default voice), the app uses one voice for the whole track.
  - **Personality** (preset or Auto) and optional **Character** (see Characters tab) for script + storyboard consistency
  - Live pipeline / preview / storyboard progress is shown as the **top row** on the **Tasks** tab; the **Status** column shows **stage + percent** (e.g. script, voice, images, encode) for runs, not only “Running…”
  - Open `videos/` folder
  - Save settings
- **Topics**
  - **Mode** combo matches video formats; each mode has its own tag list (stored in `ui_settings.json` under `topic_tags_by_mode`)
  - Add/remove tags for the **selected mode** only; the tag line includes an optional **🧠** control to expand/improve text with the local **Script (LLM)** model ([`UI/brain_expand.py`](../UI/brain_expand.py))
  - **Discover**: fetches headline-based topic suggestions using the **current “Edit tags for”** mode’s tag list; approved items are added to that mode’s list
- **Tasks**
  - Lists successful renders (`data/upload_tasks.json`): open folder, play `final.mp4`, copy caption from `meta.json` / `hashtags.txt`, mark posted manually, **Upload to TikTok** (inbox) and/or **Upload to YouTube** when the **API** tab is configured (separate toggles); optional auto-uploads per platform after each render
  - While a **pipeline run**, **batch run**, **Preview**, or **Storyboard preview** is active (top row), **Pause** / **Resume** waits between major steps (`src/pipeline_control.py`); **Stop** cancels at the next checkpoint (does not interrupt mid–GPU generation). For an active **pipeline** (or batch), **Stop** also **clears** any extra runs you queued with **Run** while the previous job was still going.
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
  - Create, edit, and delete **characters** (name, identity, visual style, negative prompts, voice overrides). Stored in `data/characters.json` (local; not committed). Multi-line fields can use the **🧠** control to expand/improve text with the **Script (LLM)** model ([brain](brain.md), [`UI/brain_expand.py`](../UI/brain_expand.py)).
  - Optional **ElevenLabs voice** picker when **API → ElevenLabs** is enabled and a key is set ([ElevenLabs](elevenlabs.md), [Characters](characters.md)).
- **API**
  - Hugging Face token (optional; helps Hub size checks and gated downloads) + optional **Firecrawl**
  - **ElevenLabs** (optional): enable + API key for cloud TTS when a character selects an ElevenLabs voice — see [ElevenLabs](elevenlabs.md)
  - **TikTok**: client key/secret, redirect URI + OAuth port, publishing mode (inbox vs direct; inbox is supported for upload), optional **auto-upload after each render** — see [TikTok upload](tiktok.md)
  - **YouTube**: separate enable; OAuth client ID/secret, redirect + port (default **8888**), default visibility, optional **#Shorts** tagging, optional **auto-upload after render** — see [YouTube upload](youtube.md)
- **Model** (tab label; model downloads + dependencies)
  - **Auto-fit for this PC**: re-detects GPU/RAM and sets script, video, and voice dropdowns using the same VRAM heuristics as the fit badges (`src/hardware.py` → `rank_models_for_auto_fit`). Skips grayed-out Hub entries; logs the chosen combo and **saves settings** (same as **💾 Save**).
  - **Download ▾** menu: download the currently selected model(s), **download all selected** (script + image/video + voice choices in one queue), **download all models** (full curated list), **verify checksums** for installed snapshots (selected or all under `models/`), plus **check Python dependencies** / **install dependencies** — runs `scripts/install_pytorch.py` (CUDA vs CPU PyTorch) then `pip install -r requirements.txt`.
  - Each model row shows a short **status badge**: **✓ On disk** (size-based), **✓ Verified** (after a good checksum run), or problem states such as **✗ Missing files** / **✗ Corrupt** / **⚠ Verify error**. Results persist in `data/model_integrity_status.json`. Verification also opens a **summary dialog** with expandable details ([models](models.md)).
  - Model dropdowns show local install status and Hub probe hints; downloads **skip** repos that already have a valid snapshot under `models/` and continue with the rest.
- **My PC**
  - Hardware summary (CPU/RAM/GPU/VRAM, best-effort)
  - Minimum requirements guidance
  - Per-model fit markers based on simple VRAM rules

## Settings persistence
Saved to:
- `ui_settings.json` (repo root; marked **hidden** on Windows and macOS after each save so it stays out of casual folder browsing)

## Theme
Applied via a global Qt stylesheet (QSS) with:
- near-black backgrounds
- default cyan accent `#25F4EE`
- default pink/red accent `#FE2C55`
- optional palette overrides configured in the Branding tab

## Dialogs and alerts
- The main window is **frameless** with a custom title bar and **✕** (see [`UI/main_window.py`](../UI/main_window.py)). **Modal alerts**, confirmations, the **Hugging Face token** prompt, **Preview** / **Storyboard Preview** windows, **Topics → Discover** approval dialogs, and the **model integrity** summary use the same pattern via [`UI/frameless_dialog.py`](../UI/frameless_dialog.py): **`FramelessDialog`** (title + ✕, drag the title bar to move) and helpers such as **`aquaduct_information`** / **`aquaduct_warning`** / **`aquaduct_question`**. Styling includes `QDialog#FramelessDialogShell` in [`UI/theme.py`](../theme.py) (rounded card border).
- **Download progress** already used a similar borderless popup ([`UI/download_popup.py`](../download_popup.py)).
- **System file/folder pickers** (`QFileDialog`) remain the OS native dialogs.

