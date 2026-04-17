# Models + downloads

## Where models are used
- **Script model (LLM)**: `src/brain.py` (local inference; 4-bit target when supported)
- **Video/images model**: `src/artist.py` (diffusers text-to-image, SDXL Turbo default)
- **Voice model (TTS)**: `src/voice.py` (Kokoro hook + system TTS fallback). The **Model** tab lists extra Hugging Face TTS weights you can snapshot locally (Kokoro, MMS-TTS, MeloTTS, SpeechT5, Parler-TTS, XTTS, Bark, etc.); wiring a specific engine to inference is separate from download.

## UI model selection
In the UI **Model** tab you can pick and download models separately for:
- Script
- Video/images
- Voice

**Auto-fit for this PC** sets all three from detected VRAM/RAM using `rank_models_for_auto_fit` in `src/hardware.py` (same heuristics as **My PC** fit badges). It saves settings after applying.

Each option is labeled with a relative speed marker:
- `fastest` / `faster` / `slow`

## How downloads work
Downloads use Hugging Face Hub snapshot download into a project-local folder:
- `models/<repo_as_dirname>/`

This is implemented in:
- `src/model_manager.py`

Notes:
- Downloads are **resumable** (`resume_download=True`) so re-running a download continues partial files.
- In the UI, downloads can be **cancelled** (closing the popup stops the worker). You can resume later.
- The UI treats a repo as **already installed** when `models/<repo>/` exists and has enough bytes on disk (not an empty or partial folder). **Download selected**, **download all selected**, and **download all** then **skip** that repo and move on—nothing is re-fetched unless you delete the folder or pick a different repo.
- Some video presets use **two** Hub repos (image + video). **Download all selected** queues **both** so both snapshots are present.

## Portable downloader (optional)
For machines without running the full app, you can snapshot the same repos into `./models`:

```powershell
pip install huggingface_hub tqdm
python scripts/download_hf_models.py
```

See `scripts/download_hf_models.py` for `--out`, tokens, and repo lists.

## Model overrides
Selected model repo IDs are persisted in `ui_settings.json` and passed into the pipeline through:
- `AppSettings.llm_model_id`
- `AppSettings.image_model_id`
- `AppSettings.voice_model_id`

If an override is blank, the pipeline falls back to `src/config.py:get_models()`.

## Tokens / gated models
Most public repos download without a token.

If a repo is **gated** (common for some Llama checkpoints), you’ll need a Hugging Face access token via `HF_TOKEN` / login.

## Verifying local snapshots (checksums)
The desktop **Model** tab → **Download ▾** includes **Verify checksums**:
- **Selected models (on disk)** — script / image / voice choices that already have a folder under `models/`
- **All folders in models/** — discover `owner__name` directories and verify each

Verification calls Hugging Face Hub (`huggingface_hub.HfApi.verify_repo_checksums` against the **main** tree): LFS weight files are checked with **SHA-256**; smaller files use the git **blob** id. **Missing** files and **hash mismatches** usually mean an incomplete or corrupted download (delete the folder and download again). Needs **internet**; gated repos need a token (same as downloads).

Helpers live in `src/model_manager.py` (`verify_project_model_integrity`, `list_installed_repo_ids_from_disk`, `project_dirname_to_repo_id`). The UI runs checks in a background thread (`ModelIntegrityVerifyWorker` in `UI/workers.py`); large models can take several minutes.

## Integrity status in the UI (badges)
After verification, per-repo outcomes are merged into `data/model_integrity_status.json` (see `src/model_integrity_cache.py`). The **Model** tab uses that file to label each dropdown row (script / video / voice), so you can see **Verified** vs **Missing** / **Corrupt** without re-running the full scan. Clear **Clear data** removes the cache file alongside other local state.

