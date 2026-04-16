# Models + downloads

## Where models are used
- **Script model (LLM)**: `src/brain.py` (local inference; 4-bit target when supported)
- **Video/images model**: `src/artist.py` (diffusers text-to-image, SDXL Turbo default)
- **Voice model (TTS)**: `src/voice.py` (Kokoro target; offline fallback)

## UI model selection
In the UI **Settings** tab you can pick and download models separately for:
- Script
- Video/images
- Voice

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

