# Models + downloads

## Curated Hugging Face repositories
The canonical id list is defined in [`src/models/model_manager.py`](../src/models/model_manager.py) (`model_options()`). It includes, among others:

| Kind | Examples |
|------|-----------|
| **Script (LLM)** | Qwen2.5 1.5B/3B/7B, Phi-3.5 Mini, Llama 3.2 3B / 3.1 8B, Mistral 7B |
| **Image** | SDXL Turbo, SD 1.5, SDXL Base, **FLUX.1 Schnell**, **Stable Diffusion 3 Medium**, **FLUX.1-dev** |
| **Video** | SVD XT / base, ZeroScope 576w / 448×256, ModelScope T2V, **CogVideoX 2B/5B**, **LTX-Video**, **HunyuanVideo** |
| **Voice** | Kokoro, MMS-TTS, MeloTTS, SpeechT5, Parler-TTS, XTTS, Bark |

**CLI bulk download** (same ids, `./models` layout as the app): `python scripts/download_hf_models.py --all` from the repo root.

**Offsite bundle** (regenerates a standalone downloader from `model_options()`): [`Model-Downloads/generate_offsite_bundle.py`](../Model-Downloads/generate_offsite_bundle.py) → see [Model-Downloads/README.md](../Model-Downloads/README.md).

## Where models are used
- **Script model (LLM)**: [`src/content/brain.py`](../src/content/brain.py) (local inference; 4-bit target when supported)
- **Image model**: [`src/render/artist.py`](../src/render/artist.py) (diffusers **text-to-image** for stills and keyframes; presets for SDXL-class, **FLUX**, and **SD3** — see [Artist](artist.md))
- **Video model**: [`src/render/clips.py`](../src/render/clips.py) (motion: text-to-video / image-to-video; frontier T2V uses dedicated diffusers pipelines for CogVideoX / LTX / Hunyuan). **Pro** with slideshow off uses this slot for **multi-scene text-to-video** (e.g. ZeroScope or the options above). **Motion mode** (slideshow off, Pro off) uses Image for keyframes + Video to animate **scene** segments. Legacy **slideshow + Pro** may still use this slot for ZeroScope→frame extract or a T2I id for per-frame stills. Prompts for CLIP-based stacks are **truncated to 77 tokens** where applicable; **SVD** img2vid uses tighter **frame / decode** caps on **≤12 GiB** cards (see [Performance](performance.md#diffusion-vram-vs-system-ram-cpu-offload)).
- **Voice model (TTS)**: [`src/speech/voice.py`](../src/speech/voice.py) (Kokoro hook + system TTS fallback). The **Model** tab lists extra Hugging Face TTS weights you can snapshot locally (Kokoro, MMS-TTS, MeloTTS, SpeechT5, Parler-TTS, XTTS, Bark, etc.); wiring a specific engine to inference is separate from download.
- **API execution mode** (`model_execution_mode: api`): script / image / optional video / voice are chosen from **Generation APIs** (OpenAI, Replicate, ElevenLabs) instead of the HF combos above; see [API generation](api_generation.md) and [`src/runtime/pipeline_api.py`](../src/runtime/pipeline_api.py).

## UI model selection
In the UI **Model** tab (when **Local models** is selected) you can pick and download models separately for:
- Script (LLM)
- Image (diffusion stills)
- Video (motion / Pro / scene pipeline)
- Voice (TTS)

**Auto-fit for this PC** sets all four from detected VRAM/RAM using `rank_models_for_auto_fit` in [`src/models/hardware.py`](../src/models/hardware.py) (same heuristics as **My PC** fit badges), using **effective VRAM per model kind** from the **GPU policy** on the **My PC** tab (Auto vs Single — not “first GPU only” when multiple cards exist). It saves settings after applying.

For multi-GPU routing at runtime (which CUDA device loads the LLM vs diffusion) and **My PC** / **Model** fit markers, see [Hardware + model fit](hardware.md) and [`src/util/cuda_device_policy.py`](../src/util/cuda_device_policy.py).

**Script model and UI “brain” features** (🧠 expand, **Characters → Generate with LLM**) resolve the repo id from the **Script (LLM)** dropdown’s **current selection** first, then saved settings — so they load the same weights as the visible combo without requiring **Save** first (`resolve_llm_model_id` in [`UI/brain_expand.py`](../UI/brain_expand.py)).

Each option is labeled with a relative speed marker:
- `fastest` / `faster` / `slow`

## How downloads work
Downloads use Hugging Face Hub snapshot download into the **active** project models folder (same layout everywhere):
- `<models_dir>/<repo_as_dirname>/`

**Default** location is **`.Aquaduct_data/models/`** next to the repo. In the desktop app you can set **External** on the **Model** tab and choose another directory (saved as `models_storage_mode` / `models_external_path` in `ui_settings.json`); see [Config](config.md). The CLI `models` subcommands resolve the same folder from saved settings.

This is implemented in:
- [`src/models/model_manager.py`](../src/models/model_manager.py)

### Why it looked like “downloading” when the model was “already there”
Aquaduct only treats a **project** copy under `.Aquaduct_data/models/` as usable when the folder has enough bytes on disk (same threshold as the Model tab). **`resolve_pretrained_load_path`** (used by the script LLM, diffusers, etc.):

1. Uses that **project** snapshot when it is complete enough.
2. Otherwise tries the **Hugging Face default cache** (e.g. `C:\Users\…\.cache\huggingface\hub\`) with **`local_files_only=True`** — if you downloaded the same repo with another tool, loads from there **without** re-fetching into the project folder.
3. Otherwise passes the **repo id** to `from_pretrained`, which may hit the Hub for missing files (and gated models need a token).

So weights might exist in the **global HF cache** while the Model tab still showed **Partial** because nothing large enough lived under **this app’s** `models/` folder. The UI label **\[29.9 GB • slow\]** is the remote size hint, not necessarily what is on disk.

Notes:
- **Gated models** (e.g. Meta Llama): accept the license on the model’s Hugging Face page, then paste a **read** token under **API** and **Save**. [`ensure_hf_token_in_env`](../src/models/hf_access.py) copies the saved token into `HF_TOKEN` whenever the process env had none — including when **Hugging Face API** is toggled off (downloads still need auth). [`_generate_with_transformers`](../src/content/brain.py) also refreshes the token from `ui_settings.json` before loading the tokenizer. Hub errors 401 / gated-repo are shortened for dialogs via [`humanize_hf_hub_error`](../src/models/hf_access.py).
- **Download ▾ → Download all voice models** queues every curated TTS snapshot (including Microsoft **SpeechT5** / **MMS-TTS**, Kokoro, MeloTTS, Parler, XTTS, Bark, …), skipping repos already present under `models/`. Same mechanism as **Download ALL models**, but voice-only (smaller total than full curated set).
- Downloads are **resumable** (`resume_download=True`) so re-running a download continues partial files.
- In the UI, downloads can be **cancelled** (closing the popup stops the worker). You can resume later.
- The UI treats a repo as **already installed** when `models/<repo>/` exists and has enough bytes on disk (not an empty or partial folder). **Download selected**, **download all selected**, and **download all** then **skip** that repo and move on—nothing is re-fetched unless you delete the folder or pick a different repo.
- Some video presets use **two** Hub repos (image + video). **Download all selected** queues **both** so both snapshots are present.

## Python packages (PyTorch, transformers, …)
Hub downloads above are **model weights only**. The **Python** stack (PyTorch, `transformers`, etc.) is installed separately: **`python scripts/install_pytorch.py --with-rest`** or, from the app, **Model → Install dependencies** (same steps; see [Dependencies](../DEPENDENCIES.md), [Desktop UI](ui.md)).

## Portable downloaders (optional)

### From a full clone (uses curated list in code)
With the repo on the machine and `HF_TOKEN` in the environment (or `.env`):

```powershell
pip install huggingface_hub tqdm
python scripts/download_hf_models.py --all
```

`--all` pulls every id in **`ALL_REPOS`** (aligned with `model_options()`). Without `--all`, a small **minimal** three-repo set is used. Override output with `--out`. See [`scripts/download_hf_models.py`](../scripts/download_hf_models.py).

### Offsite PC (standalone bundle, embedded token)
To download on **another computer** without the full app and copy folders back (USB, etc.), use **[`Model-Downloads/generate_offsite_bundle.py`](../Model-Downloads/generate_offsite_bundle.py)** from the repo root — it writes **`Model-Downloads/offsite/`** (gitignored; may contain a **live Hub token**). See **[`Model-Downloads/README.md`](../Model-Downloads/README.md)** for `pip install -r requirements-offsite.txt` and running `download_all_models.py`. Treat the generated folder like a secret; revoke the token if it leaks.

## Model overrides
Selected model repo IDs are persisted in `ui_settings.json` and passed into the pipeline through:
- `AppSettings.llm_model_id`
- `AppSettings.image_model_id`
- `AppSettings.voice_model_id`

If an override is blank, the pipeline falls back to `src/core/config.py:get_models()`.

## Tokens / gated models
Most public repos download without a token.

If a repo is **gated** (common for some Llama checkpoints), you’ll need a Hugging Face access token via `HF_TOKEN` / login.

## Verifying local snapshots (checksums)
The desktop **Model** tab → **Download ▾** includes **Verify checksums**:
- **Selected models (on disk)** — script / image / voice choices that already have a folder under `models/`
- **All folders in models/** — discover `owner__name` directories and verify each

Verification calls Hugging Face Hub (`huggingface_hub.HfApi.verify_repo_checksums` against the **main** tree): LFS weight files are checked with **SHA-256**; smaller files use the git **blob** id. **Missing** files and **hash mismatches** usually mean an incomplete or corrupted download (delete the folder and download again). Needs **internet**; gated repos need a token (same as downloads).

Helpers live in `src/models/model_manager.py` (`verify_project_model_integrity`, `list_installed_repo_ids_from_disk`, `project_dirname_to_repo_id`). The UI runs checks in a background thread (`ModelIntegrityVerifyWorker` in `UI/workers.py`); large models can take several minutes.

## Integrity status in the UI (badges)
After verification, per-repo outcomes are merged into `data/model_integrity_status.json` (see `src/models/model_integrity_cache.py`). The **Model** tab uses that file to label each dropdown row (script / image / video / voice), so you can see **Verified** vs **Missing** / **Corrupt** without re-running the full scan. Clear **Clear data** removes the cache file alongside other local state.

