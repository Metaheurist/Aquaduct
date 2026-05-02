# VRAM inference profiles (local pipeline)

## Purpose
When **model execution** is **local**, Aquaduct maps **detected / effective GPU VRAM** to a small set of **bands** and applies a **per-model profile** for script (LLM), image (T2I), video (T2V), and voice. This keeps resolution, step counts, frame counts, and token budgets aligned with the same **GPU policy** (Auto vs Single) used by the **My PC** and **Model** tab **fit** badges.

Implementation: [`src/models/inference_profiles.py`](../../src/models/inference_profiles.py).

## Effective VRAM per role
[`src/util/cuda_device_policy.effective_vram_gb_for_kind`](../../src/util/cuda_device_policy.py) returns VRAM (GiB) for:

| Kind | Device used for fit / profiles |
|------|---------------------------------|
| `script` | LLM device from [`resolve_device_plan`](../../src/util/cuda_device_policy.py) |
| `image` | Diffusion (image) device |
| `video` | Diffusion (video) device |
| `voice` | Voice / TTS device |

With **Auto** and **two or more** GPUs, script and diffusion are **not** forced onto the same ordinal; effective VRAM for each **kind** is taken from the corresponding GPU, not “GPU 0 only.”

## Bands
Rough buckets (from `vram_gb_to_band`):

- `lt_8` — &lt; 8 GiB  
- `8_12` — 8–12 GiB  
- `12_16` — 12–16 GiB  
- `16_24` — 16–24 GiB  
- `24_40` — 24–40 GiB  
- `ge_40` — 40 GiB+  
- `unknown` — no usable CUDA list / missing reading → conservative profile  

## What changes per mode
- **Script**: caps **input** and **output** token budgets via `pick_script_profile` (with small per-repo tweaks for Qwen3, Miqu, Fimbulvetr, DeepSeek, etc.), merged in [`_generate_with_transformers`](../../src/content/brain.py) when `inference_settings` is passed. **`AQUADUCT_LLM_MAX_INPUT_TOKENS`** still wins when set; see [Config](config.md#local-llm-inference-vram).
- **Image**: merges **width**, **height**, **num_inference_steps**, and **guidance** from the profile on top of baselines in [`_diffusion_kw_for_model`](../../src/render/artist.py) / [`merge_t2i_from_settings`](../../src/models/inference_profiles.py) when `inference_settings` is passed to [`generate_images`](../../src/render/artist.py) (see [Artist](../pipeline/artist.md)).
- **Video**: merges kwargs after [`_video_pipe_kwargs`](../../src/render/clips.py); **LTX-2** enforces the pipeline **(num_frames − 1) % 8 == 0** rule in [`merge_t2v_from_settings`](../../src/models/inference_profiles.py). Cog / Mochi paths avoid inventing resolution where the pipeline defaults are used.
- **Voice**: profile placeholders for Kokoro / MOSS (reserved for future kwargs).

## Console and UI
- At the start of a local **`run_once`** (after preflight), the pipeline prints a multi-line report with prefix **`[Aquaduct][inference_profile]`** via `log_inference_profiles_for_run` (effective VRAM, band, profile id, **resolved quant mode**, and key numbers per role).
- **Model** tab → **Auto-fit for this PC** appends the same **inference profile** report to the app log after the auto-fit rank summary.

## Quant aware
Each per-role profile runs alongside the resolved **quantization mode** from [Quantization](quantization.md) (`script_quant_mode`, `image_quant_mode`, `video_quant_mode`, `voice_quant_mode`). The report now includes `quant=<mode>` so the log shows both the band-level profile and the actual dtype / 4-bit / cpu_offload path used for that role.

## Tests
[`tests/models/test_inference_profiles.py`](../../tests/models/test_inference_profiles.py) — band mapping, T2I merge, LTX-2 frame rule, report smoke.

## Troubleshooting: run stops during “Loading weights”
Frontier **text-to-video** checkpoints (for example **Wan 2.2 14B**) allocate a large contiguous GPU block during `diffusers` load. If the **video** row shows **`quant='bf16'`** (or **`fp16`**) and your **effective VRAM for video** is in the **8–12 GiB** range, loading can hit **CUDA out of memory**, or in rare cases the driver/process may exit without a clean Python traceback.

Automatic mitigation (runs [`retry_stage`](../../src/runtime/oom_retry.py) around diffusion-heavy steps): **before** loading, if **used VRAM / total** on the chosen CUDA device is at or above **`AQUADUCT_VRAM_PREEMPT_USED_FRAC`** (default **99%**) even after a cache flush, Aquaduct tries the same move as recovery — **strictly more VRAM** first, then an **equal‑VRAM** peer, then **one** quant step — so a near-full GPU can shift work to a bigger card without waiting for an OOM. After a Python **`CUDA out of memory`** (and similar allocator errors), it retries with the same ordering, then stepping the role’s **quant mode** down (`bf16 → fp16 → int8 → cpu_offload` for video). Frontier **video** stages allow extra downgrade steps (`max_quant_downgrades=8`). When a retry succeeds, the updated per‑role quant mode is saved into `ui_settings.json` so the next run starts from the working level.

Always-on **`[Aquaduct][run]`** stderr lines from [`pipeline_console`](../../debug/debug_log.py) record coarse stages (`workspace`, `script_llm`, `video_t2v_load`, …); **`AQUADUCT_DEBUG`** categories still drive verbose [`dprint`](../../debug/debug_log.py) output.

**Note:** On Windows a **native** GPU/driver fault may still exit Python with **`3221225477` (`0xC0000005` access violation)** — that is **not** catchable as a Python exception; use driver updates, lighter models, **`cpu_offload`**, or Event Viewer faulting-module hints.

Mitigations:

1. **Model** tab → **Video** → set quantization to **`cpu_offload`** (or another memory-saving mode your build supports), then Save — see [Quantization](quantization.md).
2. Choose a **lighter T2V repo** from the curated list, or switch **execution** to API mode if you use a hosted video provider.
3. On **multi-GPU** setups, confirm **My PC** → GPU policy assigns **video** to the card with the **most VRAM** (effective VRAM per role appears in the `[Aquaduct][inference_profile]` lines).
4. Avoid starting a second heavy download/load (e.g. HF **Loading weights**) at the same time as a run — competing loads reduce headroom.

5. **Observability during long HF loads:** periodic heartbeat lines (**`AQUADUCT_LOAD_HEARTBEAT_INTERVAL_S`**, optional stalled-load watchdog **`AQUADUCT_LOAD_FATAL_TIMEOUT_S`** / **`AQUADUCT_LOAD_TIMEOUT_S`**) mirror to the desktop **Resource usage** footer — see [Performance — Resource graph heartbeat](../pipeline/performance.md), [Crash resilience overview](../pipeline/crash-resilience.md).

Partial outputs for a dated folder under **`.Aquaduct_data`** (for example `runs/<timestamp>/` or project folders under `videos/`) may exist without **`final.mp4`** if the pipeline stopped before the editor stage. With **Resume partial pipeline** enabled, coarse **`assets/run_checkpoint.json`** milestones can shorten the **next** desktop run — see [Crash resilience](../pipeline/crash-resilience.md).

## Related docs
- [Config](config.md) — env overrides, GPU policy fields  
- [Models + downloads](models.md) — **Auto-fit** and curated ids  
- [Hardware + model fit](hardware.md) — `rate_model_fit_for_repo`  
- [Brain](../pipeline/brain.md) — local LLM path  
- [Quantization](quantization.md) — per-model quant modes, VRAM multipliers, fallbacks  
- [Crash resilience](../pipeline/crash-resilience.md) — checkpoints / resume / heartbeat  
