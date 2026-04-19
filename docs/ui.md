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
  - **Video format** (News / Cartoon / Explainer / **Cartoon (unhinged)**): together with Topics, selects which tag list the pipeline uses (`video_format` + `topic_tags_by_mode`). **News** and **Explainer** share the same AI/product headline sourcing and news-style script shape. **Cartoon** pulls newest animation/streaming buzz (not tutorial framing). **Unhinged** pulls internet-trend / viral-style seeds for satire. **Cartoon (unhinged)** favors chaotic comedy/absurdist animation; it rotates **local** pyttsx3 voices per script beat, and if a character uses **ElevenLabs** (or a custom non-default voice), the app uses one voice for the whole track.
  - **Personality** (preset or Auto) and optional **Character** (see Characters tab) for script + storyboard consistency
  - Live pipeline / preview / storyboard progress is shown as the **top row** on the **Tasks** tab; the **Status** column shows **stage + percent** (e.g. script, voice, images, encode) for runs, not only “Running…”
  - Open `videos/` folder
  - Save settings
- **Topics**
  - **Mode** combo matches video formats; each mode has its own tag list (stored in `ui_settings.json` under `topic_tags_by_mode`)
  - Add/remove tags for the **selected mode** only; the tag line includes an optional **🧠** control to expand/improve text with the local **Script (LLM)** model ([`UI/brain_expand.py`](../UI/brain_expand.py))
  - **Discover**: fetches headline-based topic suggestions using the **current “Edit tags for”** mode’s tag list; approved items are added to that mode’s list
- **Tasks**
  - **Run controls** (refresh list, pause between steps, stop) sit **above** the task table, directly under the short intro text; **Selected task** actions (**Open folder**, **Play video**, uploads, etc.) stay **below** the table.
  - Lists successful renders (`data/upload_tasks.json`): open folder, play `final.mp4`, copy caption from `meta.json` / `hashtags.txt`, mark posted manually, **Upload to TikTok** (inbox) and/or **Upload to YouTube** when the **API** tab is configured (separate toggles); optional auto-uploads per platform after each render
  - While a **pipeline run**, **batch run**, **Preview**, or **Storyboard preview** is active (top row), **Pause** / **Resume** waits between major steps ([`src/runtime/pipeline_control.py`](../src/runtime/pipeline_control.py)); **Stop** cancels at the next checkpoint (does not interrupt mid–GPU generation). For an active **pipeline** (or batch), **Stop** also **clears** any extra runs you queued with **Run** while the previous job was still going.
- **Video**
  - **Platform template** (top): **tiles** (like graphics presets in a game) — one card per social profile (e.g. short-form vertical, Instagram square/portrait, Pinterest, YouTube/LinkedIn landscape) plus **Pro — vertical 60 fps** plus **Custom**. Clicking a tile applies resolution, FPS, micro-scene timing, images per video, bitrate, motion-mode scene timings (`clips_per_video` / `clip_seconds`), and pro fields when applicable. Changing any of those controls switches to **Custom**. Stored as `video.platform_preset_id` in settings; definitions in [`src/settings/video_platform_presets.py`](../src/settings/video_platform_presets.py).
  - **Resolution** (dropdown of width×height presets used by the templates)
  - Images per video (hidden when **Pro mode** is on)
  - **Pro mode** + **Pro scene length (seconds)**: in the desktop UI, Pro **turns slideshow off** and runs **text-to-video** from the **Video** model (e.g. ZeroScope): the script becomes one or more scene prompts, segments are generated and concatenated; narration is aligned to the combined segment length. If you force **slideshow + Pro** via edited settings, the older **one still per output frame** path still exists (round(length × FPS) frames; preflight warns on large counts).
  - Slideshow mode vs **motion mode** (generate images and stitch vs **scene**-based video pipeline when slideshow is off)
  - FPS
  - Micro-scene min/max seconds (slideshow timing)
  - Bitrate preset (low/med/high)
  - Export intermediate micro-scenes toggle
  - Delete generated images after run (save storage)
  - **Allow NSFW image output** (optional): disables the diffusion safety checker for image generation so flagged frames are not replaced with black slides — use only where appropriate; you are responsible for platform rules (`AppSettings.allow_nsfw`)
- Quality/performance and advanced controls live under **Video**:
  - Prefer GPU toggle (advisory)
  - High quality topic selection, fetch article text, prompt conditioning (no model-specific toggles here; script/image behavior is chosen on the **Model** tab)
  - **Story pipeline (LLM)** (optional): **Multi-stage script review** runs extra local LLM passes after the first draft (beat structure, safety, length, clarity for News/Explainer; dialogue, pacing, punchlines for Cartoon/Unhinged). **Gather web context** uses **Firecrawl** (API tab) to search/scrape a short digest saved under the run folder and fed into script generation. **Download reference images** pulls a few images from scraped pages and uses the first as an **img2img** init for the first generated frame when the image model supports it (SDXL-style paths). These options add latency and API usage when Firecrawl is involved.
  - Background music picker
  - Clear news URL/title cache: removes legacy `seen.json` / `seen_titles.json` and all `seen_*.json` / `seen_titles_*.json` under `data/news_cache/`
- **Captions**
  - Word-by-word captions and optional **Key facts** card. The facts card is **drawn only** when **Video format** (Run tab) is **News** or **Explainer**; **Cartoon** and **Cartoon (unhinged)** runs skip it regardless of the Captions toggle ([`video_format_supports_facts_card`](../src/core/config.py)).
- **Branding**
  - Optional full-theme palette overrides (presets or custom hex + color picker). Changing the **Palette** dropdown updates the hex swatches and fields for that preset (Custom unlocks per-row overrides).
  - Optional logo watermark on generated videos
- **Characters**
  - Create, edit, and delete **characters** (name, identity, visual style, negative prompts, voice overrides). Stored in `data/characters.json` (local; not committed). **Preset** + **Generate with LLM** fills fields from built-in archetypes using the **Model** tab script model ([Characters](characters.md), [brain](brain.md)).
  - Multi-line fields can use the **🧠** control to expand/improve text with the **Script (LLM)** model — same repo id as the **Model** tab combo ([`resolve_llm_model_id`](../UI/brain_expand.py), [Models](models.md)).
  - Optional **ElevenLabs voice** picker when **API → ElevenLabs** is enabled and a key is set ([ElevenLabs](elevenlabs.md), [Characters](characters.md)).
- **API**
  - **Generation APIs** (first block): **OpenAI** / **Replicate** / **ElevenLabs** routing for **API execution mode** — script, image, video (Pro), and voice providers + models; shared with the **Model** tab when that tab is in **API** mode (one panel is reparented). See [API generation](api_generation.md).
  - Hugging Face token (optional; helps Hub size checks and gated downloads) + optional **Firecrawl**
  - **ElevenLabs** (optional): enable + API key for cloud TTS when a character selects an ElevenLabs voice — see [ElevenLabs](elevenlabs.md)
  - **TikTok**: client key/secret, redirect URI + OAuth port, publishing mode (inbox vs direct; inbox is supported for upload), optional **auto-upload after each render** — see [TikTok upload](tiktok.md)
  - **YouTube**: separate enable; OAuth client ID/secret, redirect + port (default **8888**), default visibility, optional **#Shorts** tagging, optional **auto-upload after render** — see [YouTube upload](youtube.md)
- **Model** (tab label; model downloads + dependencies)
  - **Local** vs **API** (top-right segmented toggle): **Local** keeps Hugging Face–backed combos, downloads, verify, and **Auto-fit**. **API** hides those local controls and shows the same **Generation APIs** panel as the **API** tab (keys + per-role provider/model) inside a **scroll area** so fields are not vertically crushed; the window also grows a bit in API mode. Persisted as `model_execution_mode` + `api_models` in `ui_settings.json` ([API generation](api_generation.md)).
  - **Script (LLM)** combo drives pipeline scripts, **🧠** field expansion, and **Characters → Generate with LLM** — the **current** selection is used even if you have not clicked **Save** yet ([`resolve_llm_model_id`](../UI/brain_expand.py), [Models](models.md)).
  - **Image** = text-to-image (slideshow stills, SVD keyframes). **Video** = motion models (ZeroScope, Stable Video Diffusion). **Pro** mode uses the **Video** slot for **text-to-video** (multi-scene from script when slideshow is off); SVD / img2vid-only repos are blocked for Pro in preflight. A legacy **slideshow + Pro** path can still use a T2I id from the Video slot for per-frame stills if both toggles are on in saved settings.
  - **Auto-fit for this PC**: re-detects GPU/RAM and sets script, image, video, and voice dropdowns using the same VRAM heuristics as the fit badges ([`src/models/hardware.py`](../src/models/hardware.py) → `rank_models_for_auto_fit`). Skips grayed-out Hub entries; logs the chosen combo and **saves settings** (same as **💾 Save**).
  - **Download ▾** menu: download the currently selected model by role (**script** / **image** / **video** / **voice**); **download all voice models** (every curated TTS Hub repo—Kokoro, Microsoft MMS/SpeechT5, MeloTTS, Parler, XTTS, Bark, …); **download all selected** (script + image + video + voice in one queue); **download all models** (full curated list); **verify checksums** for installed snapshots (selected or all under `models/`); plus **check Python dependencies** / **install dependencies** — **install** opens a **progress dialog** with live pip output, parsed “current package” hints (`pip_line_hint` in [`src/models/torch_install.py`](../src/models/torch_install.py)), and a **progress bar** that stays **indeterminate** until pip prints a line with a **download percentage** (then shows **0–100%**). Same underlying install as `scripts/install_pytorch.py` + `requirements.txt` ([`UI/install_deps_dialog.py`](../UI/install_deps_dialog.py)).
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

