# Models + downloads

## Curated Hugging Face repositories
The canonical id list is defined in [`src/models/model_manager.py`](../../src/models/model_manager.py) (`model_options()`). It includes, among others:

| Kind | Examples |
|------|-----------|
| **Script (LLM)** | **Qwen3 14B Instruct** (curated default), **Fimbulvetr 11B v2** (prose / Solar), **Midnight Miqu 70B v1.5** (heavyweight), **DeepSeek-V3** (`deepseek-ai/DeepSeek-V3` — 671B MoE, complex plot / reasoning at scale) — see [`model_options()`](../../src/models/model_manager.py) |
| **Image** | **FLUX.1.1 [pro] ultra** (`black-forest-labs/FLUX.1.1-pro-ultra`), **FLUX.1 [dev]**, **FLUX.1 [schnell]**, **SD3.5** Large / Medium, **SD3 Turbo** — see [`model_options()`](../../src/models/model_manager.py) |
| **Video** | **Wan 2.2 T2V A14B** (`Wan-AI/Wan2.2-T2V-A14B-Diffusers`), **Mochi 1.5** (`genmo/mochi-1.5-final`), **CogVideoX 5B**, **HunyuanVideo**, **LTX-2** (`Lightricks/LTX-2` — 4K-class Shorts) — see [`model_options()`](../../src/models/model_manager.py) |
| **Voice** | Kokoro-82M, MOSS-VoiceGenerator |

### Quick comparison (text-to-video, rough guide)
At-a-glance for **planning VRAM** and **license vibe**; minimum VRAM depends on **quantization**, **diffusers** path, and **resolution** — treat as approximate.

| Model | Size | Minimum VRAM (typical, quantized / efficient path) | License | Vibe |
|-------|------|---------------------------------------------------|---------|------|
| **Wan 2.2** | ~14B | ~14 GB | Apache 2.0 (check release card) | Balanced & smart |
| **Mochi 1.5** | ~10B+ | ~12 GB+ | Apache 2.0 (check release card) | Longer default clips, less temporal jitter (vs 1.0) |
| **LTX-2** | 19B-class | 24 GB+ at 4K (tiling/ offload common) | [Community license](https://huggingface.co/Lightricks/LTX-2) | Native 4K AV T2V (optional **PyAV** / `av` for muxed export) |
| **CogVideoX 5B** | 5B | ~6 GB (quantized / tight setups) | Apache 2.0 | Efficient & stylized |
| **Hunyuan** (large) | Large | ~16 GB+ | Open-weight / custom terms (see [Tencent/HunyuanVideo](https://huggingface.co/Tencent/HunyuanVideo) card) | Frontier fidelity |

**Aquaduct local video slot** ([`model_options()`](../../src/models/model_manager.py), [`clips.py`](../../src/render/clips.py)) wires the table rows above: **Wan 2.2**, **Mochi 1.5**, **CogVideoX 5B**, **HunyuanVideo**, **LTX-2** (`LTX2Pipeline` + optional `encode_video` with audio when **PyAV** is installed: `pip install av`). SVD, ZeroScope, ModelScope, and **LTX-Video** remain supported if you type those Hub ids manually.

**CLI bulk download** (same ids, `./models` layout as the app): `python scripts/download_hf_models.py --all` from the repo root. The list matches [`scripts/download_hf_models.py`](../../scripts/download_hf_models.py) `ALL_REPOS` and the [embedded copy in `scripts/download_all_for_transfer.ps1`](../../scripts/download_all_for_transfer.ps1).

**Windows copy (optional):** if you use a second standalone downloader (for example `H:\AI Models\download_all_for_transfer.ps1` on a transfer drive), keep its embedded `ALL_REPOS` in lockstep with `scripts/download_hf_models.py` — it is the same full curated set as the app’s bulk download.

**Offsite bundle** (regenerates a standalone downloader from `model_options()`): [`Model-Downloads/generate_offsite_bundle.py`](../../Model-Downloads/generate_offsite_bundle.py) → see [Model-Downloads/README.md](../../Model-Downloads/README.md).

**FLUX.1.1 [pro] ultra and quantized / distilled weights:** The BFL id **`black-forest-labs/FLUX.1.1-pro-ultra`** is the curated **1.1 Pro Ultra** text-to-image checkpoint; the Hub may require **signing in** and **accepting** the org’s terms (unauthenticated API checks can return 401). For **other** official BFL quants, the same org publishes **FLUX.2**-family **fp8** / **NVFP4** checkpoints (e.g. `black-forest-labs/FLUX.2-dev-NVFP4`, `…/FLUX.2-klein-9b-fp8` — not interchangeable with 1.1, but often what people mean by “distilled/quant” on the Hub). Community **fp8** repacks and **ONNX** builds of **FLUX.1-dev** / **Schnell** are also findable; paste those repo ids in the **Model** field if you use them.

## Where models are used
- **Script model (LLM)**: [`src/content/brain.py`](../../src/content/brain.py) (local inference; 4-bit target when supported). **Default** Hub id is **Qwen/Qwen3-14B-Instruct** (Qwen3: strong for creative and multi-turn work; on capable stacks you can use non-“thinking” / chat settings for fast prose where the runtime supports it). The **Model** tab lists four **curated** script options; you can still paste any compatible `AutoModelForCausalLM` repo id.
- **Image model**: [`src/render/artist.py`](../../src/render/artist.py) (diffusers **text-to-image** for stills and keyframes; presets for **FLUX**, **SD3.5**, and user-typed SDXL/SD1.5 ids — see [Artist](../pipeline/artist.md))
- **Video model**: [`src/render/clips.py`](../../src/render/clips.py) (motion: text-to-video; curated **Wan 2.2** / **Mochi 1.5** / **CogVideoX 5B** / **HunyuanVideo** / **LTX-2** plus user-typed ids such as SVD, ZeroScope, or LTX-Video). **Pro** with slideshow off can use this slot for **multi-scene text-to-video**. **Motion mode** (slideshow off, Pro off) can pair Image for keyframes + Video for **scene** segments. CLIP-77-style truncation applies only to **CLIP text** stacks, not to **CogVideoX** / **Wan** / **Mochi** / **Hunyuan** / **LTX** long-text paths; **SVD** img2vid (if used) has tighter **frame / decode** caps on **≤12 GiB** cards (see [Performance](../pipeline/performance.md#diffusion-vram-vs-system-ram-cpu-offload)).
- **Voice model (TTS)**: [`src/speech/voice.py`](../../src/speech/voice.py) (Kokoro or MOSS-VoiceGenerator when installed, else `pyttsx3`). The **Model** tab lists **Kokoro-82M** and **MOSS-VoiceGenerator** for local snapshot download; you can still paste other Hub ids manually.
- **API execution mode** (`model_execution_mode: api`): script / image / optional video / voice are chosen from **Generation APIs** (OpenAI, Replicate, ElevenLabs) instead of the HF combos above; see [API generation](../integrations/api_generation.md) and [`src/runtime/pipeline_api.py`](../../src/runtime/pipeline_api.py).

## UI model selection
In the UI **Model** tab (when **Local models** is selected) you can pick and download models separately for:
- Script (LLM)
- Image (diffusion stills)
- Video (motion / Pro / scene pipeline)
- Voice (TTS)

**Auto-fit for this PC** sets all four from detected VRAM/RAM using `rank_models_for_auto_fit` in [`src/models/hardware.py`](../../src/models/hardware.py) (same heuristics as **My PC** fit badges), using **effective VRAM per model kind** from the **GPU policy** on the **My PC** tab (Auto vs Single — not “first GPU only” when multiple cards exist). It saves settings after applying. The same run also appends an **[Aquaduct][inference_profile]** log block (per-role **effective VRAM**, band, profile id, and key numbers) from [`format_inference_profile_report`](../../src/models/inference_profiles.py) — the full pipeline prints a similar report at local **`run_once`** start.

After models are chosen, **local** runs apply **inference profiles** (resolution, steps, T2V frames, LLM token caps) from [`src/models/inference_profiles.py`](../../src/models/inference_profiles.py) on top of each model’s baseline — see [VRAM inference profiles](inference_profiles.md).

For multi-GPU routing at runtime (which CUDA device loads the LLM vs diffusion) and **My PC** / **Model** fit markers, see [Hardware + model fit](hardware.md) and [`src/util/cuda_device_policy.py`](../../src/util/cuda_device_policy.py).

**Script model and UI “brain” features** (🧠 expand, **Characters → Generate with LLM**) resolve the repo id from the **Script (LLM)** dropdown’s **current selection** first, then saved settings — so they load the same weights as the visible combo without requiring **Save** first (`resolve_llm_model_id` in [`UI/brain_expand.py`](../../UI/brain_expand.py)).

Each option is labeled with a relative speed marker:
- `fastest` / `faster` / `slow`

## How downloads work
Downloads use Hugging Face Hub snapshot download into the **active** project models folder (same layout everywhere):
- `<models_dir>/<repo_as_dirname>/`

**Default** location is **`.Aquaduct_data/models/`** next to the repo. In the desktop app you can set **External** on the **Model** tab and choose another directory (saved as `models_storage_mode` / `models_external_path` in `ui_settings.json`); see [Config](config.md). The CLI `models` subcommands resolve the same folder from saved settings.

This is implemented in:
- [`src/models/model_manager.py`](../../src/models/model_manager.py)

### Why it looked like “downloading” when the model was “already there”
Aquaduct only treats a **project** copy under `.Aquaduct_data/models/` as usable when the folder has enough bytes on disk (same threshold as the Model tab). **`resolve_pretrained_load_path`** (used by the script LLM, diffusers, etc.):

1. Uses that **project** snapshot when it is complete enough.
2. Otherwise tries the **Hugging Face default cache** (e.g. `C:\Users\…\.cache\huggingface\hub\`) with **`local_files_only=True`** — if you downloaded the same repo with another tool, loads from there **without** re-fetching into the project folder.
3. Otherwise passes the **repo id** to `from_pretrained`, which may hit the Hub for missing files (and gated models need a token).

So weights might exist in the **global HF cache** while the Model tab still showed **Partial** because nothing large enough lived under **this app’s** `models/` folder. The UI label **\[29.9 GB • slow\]** is the remote size hint, not necessarily what is on disk.

Notes:
- **Gated models** (e.g. Meta Llama): accept the license on the model’s Hugging Face page, then paste a **read** token under **API** and **Save**. [`ensure_hf_token_in_env`](../../src/models/hf_access.py) copies the saved token into `HF_TOKEN` whenever the process env had none — including when **Hugging Face API** is toggled off (downloads still need auth). [`_generate_with_transformers`](../../src/content/brain.py) also refreshes the token from `ui_settings.json` before loading the tokenizer. Hub errors 401 / gated-repo are shortened for dialogs via [`humanize_hf_hub_error`](../../src/models/hf_access.py).
- **Bulk download scripts** (`python scripts/download_hf_models.py`, `download_all_for_transfer.ps1`, or a copy on a transfer drive) resolve auth from **`HF_TOKEN`** / **`HUGGINGFACEHUB_API_TOKEN`** (and optional embedded `HF_TOKEN` in generated scripts). If the log prints **HF token: set** but the Hub returns **401** / *Invalid username or password* / *Repository Not Found*, the string is often **invalid or expired** — create a new token at [Hugging Face access tokens](https://huggingface.co/settings/tokens) and use **`huggingface-cli whoami`** to verify. A later **unauthenticated** warning on a public repo can still appear when a bad token is ignored for anonymous access; fix the token for gated models and rate limits.
- **Download ▾ → Download all voice models** queues every curated TTS snapshot (**Kokoro**, **MOSS-VoiceGenerator**), skipping repos already present under `models/`. Same mechanism as **Download ALL models**, but voice-only (smaller total than full curated set).
- Downloads are **resumable** (`resume_download=True`) so re-running a download continues partial files.
- In the UI, downloads can be **cancelled** (closing the popup stops the worker). You can resume later.
- The UI treats a repo as **already installed** when `models/<repo>/` exists and has enough bytes on disk (not an empty or partial folder). **Download selected**, **download all selected**, and **download all** then **skip** that repo and move on—nothing is re-fetched unless you delete the folder or pick a different repo.
- Some video presets use **two** Hub repos (image + video). **Download all selected** queues **both** so both snapshots are present.

## Python packages (PyTorch, transformers, …)
Hub downloads above are **model weights only**. The **Python** stack (PyTorch, `transformers`, etc.) is installed separately: **`python scripts/install_pytorch.py --with-rest`** or, from the app, **Model → Install dependencies** (same steps; see [Dependencies](../../DEPENDENCIES.md), [Desktop UI](../ui/ui.md)).

## Portable downloaders (optional)

### From a full clone (uses curated list in code)
With the repo on the machine and `HF_TOKEN` in the environment (or `.env`):

```powershell
pip install huggingface_hub tqdm
python scripts/download_hf_models.py --all
```

`--all` pulls every id in **`ALL_REPOS`** (aligned with `model_options()`). Without `--all`, a small **minimal** three-repo set is used. Override output with `--out`. See [`scripts/download_hf_models.py`](../../scripts/download_hf_models.py).

### Offsite PC (standalone bundle, embedded token)
To download on **another computer** without the full app and copy folders back (USB, etc.), use **[`Model-Downloads/generate_offsite_bundle.py`](../../Model-Downloads/generate_offsite_bundle.py)** from the repo root — it writes **`Model-Downloads/offsite/`** (gitignored; may contain a **live Hub token**). See **[`Model-Downloads/README.md`](../../Model-Downloads/README.md)** for `pip install -r requirements-offsite.txt` and running `download_all_models.py`. Treat the generated folder like a secret; revoke the token if it leaks.

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

