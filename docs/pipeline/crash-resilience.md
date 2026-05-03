# Crash resilience and recovery (checkpoints, OOM ladders, watchdogs)

Guide to features that improve **recovery** after interruptions, **`CUDA out of memory`**, flaky dependencies, or long **Hub / diffusers** loads. Implementations span [`main.py`](../../main.py), [`src/runtime/`](../../src/runtime/), [`src/content/brain.py`](../../src/content/brain.py), and UI wiring in [`UI/main_window.py`](../../UI/main_window.py).

See also:

- [Performance — CPU offload, heartbeat, checkpoints](performance.md)
- [Config — VRAM watchdog, LLM token cap, diffusion env](../reference/config.md)
- [VRAM utilities](../reference/vram.md)
- [Inference profiles — troubleshooting stalled loads](../reference/inference_profiles.md)
- [Quantization — automatic downgrade after failure](../reference/quantization.md)
- [Hardware — lighter video checkpoint button](../reference/hardware.md)
- [Desktop UI — Resume, Models, Resource graph](../ui/ui.md)

## Checkpoints and partial resume

When **Resume partial pipeline** is enabled (**Video** tab → persists as `resume_partial_pipeline` under video settings in `ui_settings.json`), the orchestrator writes **coarse** milestone files:

| Artifact | Role |
|---------|------|
| `videos/<project>/assets/run_checkpoint.json` | JSON with `fingerprint` (script/image/video/voice ids + media mode) and `stages` — completed stage ids. |
| `videos/<project>/assets/pipeline_script_package.json` | Serialized script package ([`VideoPackage`](../../src/content/brain.py)); used to **skip script LLM** on resume when the checkpoint and JSON match the current fingerprint. |

Related helpers: [`src/runtime/run_checkpoint.py`](../../src/runtime/run_checkpoint.py) (`save_script_package`, `load_script_package`, `mark_stage_complete`, `merge_checkpoint_into_project`, `find_latest_resumable_video_project`). Staging runs under `runs/<id>/assets` can merge checkpoints into the final project assets folder once the destination is known.

**Startup resume dialog** (desktop): when a **resumable** incomplete folder exists under **`videos/`** (no `final.mp4`, fingerprint match, incomplete stages — see `find_latest_resumable_video_project`), the app may prompt to **resume**, **decline**, or discard the checkpoint (**Help** on the prompt). **`resume_partial_project_directory`** on `AppSettings` holds the ephemeral choice during a session; it is **not** written to disk ([`strip_ephemeral_save_keys`](../../src/settings/ui_settings.py)).

Stages are granular enough to reuse **voice** / **cast** artifacts when checkpoints align; **`done`** clears resume targeting after a finished encode.

## Long model loads — heartbeat and Resource graph footer

Synchronous **`from_pretrained`** (transformers / diffusers) blocks the worker thread for a long time. A background heartbeat logs progress and exposes the **latest line** for the Resource usage dialog footer ([`src/runtime/load_heartbeat.py`](../../src/runtime/load_heartbeat.py), [`diffusion_load_watch`](../../src/runtime/load_heartbeat.py)).

| Environment variable | Meaning |
|----------------------|---------|
| `AQUADUCT_LOAD_HEARTBEAT_INTERVAL_S` | Seconds between heartbeat lines (minimum **10**; default **30**). |
| `AQUADUCT_LOAD_FATAL_TIMEOUT_S` **or** `AQUADUCT_LOAD_TIMEOUT_S` | Optional **fatal watchdog** elapsed seconds (> **0**). Emits stalled-load diagnostics; **does not cancel** the in-flight Hugging Face load safely on all platforms. |

Details: [performance.md — Resource graph](performance.md).

## Host RAM heuristic before heavy loads

[`analyze_stage_memory_budget`](../../src/runtime/memory_budget_preflight.py) compares **approximate Hub snapshot size** (from **`hf_model_sizes.json`**) vs **available host RAM**. Matches become **preflight warnings**; **catastrophic** gaps (default: **video** models with very large snapshot estimates vs very little free RAM — e.g. **Wan** on a ~21 GiB free host) produce **preflight errors** so the run does not proceed to a load that often ends in a **silent Windows OOM kill**.

| Variable | Default | Role |
|----------|---------|------|
| `AQUADUCT_MEMORY_PREFLIGHT` | **on** (`1`) | `0` / `false` / `off` — skip warnings **and** fatal host-RAM gates for this heuristic. |
| `AQUADUCT_HOST_RAM_PREFLIGHT_FACTOR` | **2.0** | Multiply cached model GiB estimate (buffer / mmap spikes). |
| `AQUADUCT_HOST_RAM_FLOOR_GIB` | **5.0** | Floor (GiB) combined with scaled snapshot for threshold. |
| `AQUADUCT_MEMORY_PREFLIGHT_FAIL` | unset | `1`/`on` — treat **every** RAM shortfall warning as a **hard** preflight error. |
| `AQUADUCT_MEMORY_PREFLIGHT_FAIL_ROLES` | **`video`** | Comma roles eligible for catastrophic blocking; **empty** disables auto-block (warnings only). |
| `AQUADUCT_MEMORY_SEVERE_SHORTFALL_FRAC` | **0.35** | If free RAM `<` this × heuristic threshold, catastrophic path can fire. |

Full table: [Config — stage memory budget](../reference/config.md#stage-memory-budget-host-ram-heuristic).

## LLM holder (fewer reloads across steps)

[`src/content/llm_session.py`](../../src/content/llm_session.py) exposes **`new_llm_holder`** / **`dispose_llm_holder`**. When the desktop pipeline passes a shared **`llm_holder`** into brain functions, **`_infer_text_with_optional_holder`** reuses tokenizer + causal LM weights across **custom brief expansion**, **script JSON**, refinement, cast, etc., instead of load/dispose each time ([`brain.py`](../../src/content/brain.py)).

## Voice — retry ladder and offline sentinel

Local voice synthesis wrapped in **`retry_stage`** ([`src/runtime/oom_retry.py`](../../src/runtime/oom_retry.py)) can step through failures: **MOSS → Kokoro** (and curated mappings in [`variant_fallback`](../../src/runtime/variant_fallback.py)). The Hub id **`aquaduct/system-tts-pyttsx3`** acts as a **pyttsx3-only** sentinel for systems without GPU-capable MOSS/Kokoro. **ElevenLabs** cloud path stays separate (no transformer-style retry ladder).

See [voice.md](voice.md) for product-level TTS behavior.

## Quantization downgrade and recovery ladder

Per-role **`auto`** quant plus **`auto_quant_downgrade_on_failure`** (default **on** — **Model** tab checkbox) feeds [`retry_stage`](../../src/runtime/oom_retry.py): OOM / load failures step down quantization, then cooperate with **`resource_ladder`** (resolution / frames where applicable), **`variant_fallback`** (smaller Hub checkpoint with user-facing confirmation flow where wired), and optional **CPU-last-resort** paths. Dependency/setup errors (**tiktoken**, **triton**, **xformers**, etc.) are classified so they **skip** pointless quant-burn loops.

CUDA allocator: at process start **`main`** sets **`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:128`** and **`HF_HUB_ENABLE_HF_TRANSFER=0`** (see [CHANGELOG](../../CHANGELOG.md)).

## Hugging Face token preflight

[`preflight_check`](../../src/runtime/preflight.py) emits **non-blocking** guidance when **no** `HF_TOKEN` / Hugging Face token is configured:

- Stronger wording when configured model ids include **gated / frontier** repos.
- Generic “slower downloads / rate limits” hint otherwise.


