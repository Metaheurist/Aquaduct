# Per-model quantization controls

## Purpose
Aquaduct exposes a per-row **quantization** dropdown on the **Settings → Model** tab so the user can pick how each local model is loaded:

- **Script** (LLM)
- **Image** (T2I diffusion)
- **Video** (T2V / I2V diffusion)
- **Voice** (TTS, MOSS / Kokoro)

The selection is persisted in [`AppSettings`](config.md#local-llm-inference-vram) as `script_quant_mode`, `image_quant_mode`, `video_quant_mode`, `voice_quant_mode` and feeds the loaders, the **VRAM** label, the **fit** badge, and the **Auto-fit for this PC** ranking. Implementation lives in [`src/models/quantization.py`](../../src/models/quantization.py).

## Modes
| Mode | Meaning |
|------|---------|
| `auto` | choose the highest-quality mode that fits the **effective per-role VRAM** ([`effective_vram_gb_for_kind`](../../src/util/cuda_device_policy.py)) |
| `bf16` | bf16 dtype (best on Ampere+ / Hopper) |
| `fp16` | fp16 dtype (broadly supported) |
| `int8` | 8-bit weight quant where the backend supports it (`bitsandbytes` for LLMs / MOSS, experimental in `diffusers`) |
| `nf4_4bit` | 4-bit NF4 (`BitsAndBytesConfig`) — LLM rows only |
| `cpu_offload` | route the pipeline to **CPU** / model-CPU-offload — diffusion rows and voice (MOSS) |

`supported_quant_modes(role, repo_id)` enumerates the modes available per row (LLMs include `nf4_4bit`; diffusion / voice rows include `cpu_offload`). Unsupported modes are listed disabled with a tooltip explaining the limitation (e.g. Kokoro accepts `auto` only).

## GPU policy aware
`auto` resolution and the VRAM label both use the **effective VRAM per role** that the rest of the app uses for fit badges and inference profiles:

- [`src.util.cuda_device_policy.effective_vram_gb_for_kind`](../../src/util/cuda_device_policy.py) (kind ∈ `script | image | video | voice`)
- or [`src.models.inference_profiles.resolve_effective_vram_gb`](../../src/models/inference_profiles.py)

This respects [`AppSettings.gpu_selection_mode`](config.md):

- **`auto`**: LLM and diffusion can land on different GPUs (compute-preferred vs max-VRAM).
- **`single`**: every role uses the pinned `gpu_device_index`.

When the user switches GPU policy, the **quant dropdown’s `Auto`**, the predicted VRAM range, the **fit** badge, and **Auto-fit** all update consistently.

## VRAM prediction
`predict_vram_gb(role, repo_id, base_low_gb, base_high_gb, mode)` applies a coarse multiplier to the base hint produced by [`vram_requirement_hint`](../../src/models/hardware.py):

- **LLM**: `nf4_4bit ≈ 0.30–0.40 × fp16`, `int8 ≈ 0.55–0.65 × fp16`, `bf16 / fp16` ≈ 1.0
- **Diffusion**: `cpu_offload` widens the band (activations dominate), `int8` ≈ 0.7–0.8 × fp16 (experimental)
- **Voice**: similar handling for MOSS; Kokoro reports the stable hint

The Settings UI shows the result as e.g. `~7-9 GB · NF4 4-bit` with a tooltip naming the multiplier and any experimental fallback behavior.

## Auto-fit
[`AutoFitRanked`](../../src/models/hardware.py) carries the resolved quant per row: `script_quant_modes / image_quant_modes / video_quant_modes / voice_quant_modes` aligned to the ranked `*_repo_ids`. `rank_models_for_auto_fit` calls `pick_auto_mode(role, repo_id, vram_gb)` so:

- low-VRAM hosts pick memory-saving modes (`nf4_4bit`, `cpu_offload`),
- high-VRAM hosts prefer `bf16` / `fp16`,
- the dropdowns in **Auto-fit for this PC** are populated **alongside** the picked repo.

## Runtime loaders and fallbacks
All loaders accept the resolved mode and **fall back gracefully** with a status message if the selected stack doesn’t support it:

- **LLM** ([`src/content/brain.py`](../../src/content/brain.py)) — `load_causal_lm_from_pretrained(..., quant_mode=...)`. Tries `BitsAndBytesConfig` (4-bit NF4 / int8) or fp16 / bf16 dtype, falls back to fp16 / CPU.
- **Image** ([`src/render/artist.py`](../../src/render/artist.py)) — `_load_auto_t2i_pipeline` / `_load_auto_i2i_pipeline` choose a dtype from the mode and optionally try a `diffusers` `BitsAndBytesConfig` when the installed stack exposes it; failures fall back to the stable dtype path.
- **Video** ([`src/render/clips.py`](../../src/render/clips.py)) — `_load_text_to_video_pipeline` resolves dtype; experimental int8 / 4-bit currently falls back to fp16 (backend support varies by pipeline).
- **Voice** ([`src/speech/tts_kokoro_moss.py`](../../src/speech/tts_kokoro_moss.py)) — MOSS attempts `BitsAndBytesConfig` for int8 / nf4 and routes `cpu_offload` to CPU; Kokoro accepts the parameter for symmetry but uses its stable path.
- **Diffusion placement** ([`src/util/diffusion_placement.py`](../../src/util/diffusion_placement.py)) — `place_diffusion_pipeline(..., force_offload="model")` is forced when `quant_mode == "cpu_offload"`. **Device** selection still goes through [`resolve_diffusion_cuda_device_index`](../../src/util/cuda_device_policy.py) and [`resolve_llm_cuda_device_index`](../../src/util/cuda_device_policy.py).

## Persistence and migration
Settings load goes through [`src/settings/ui_settings.py`](../../src/settings/ui_settings.py):

- Unknown / aliased strings (`"4bit"` → `"nf4_4bit"`, `"int_8"` → `"int8"`, etc.) are normalized to the canonical mode.
- Legacy `try_llm_4bit=True` (no explicit `script_quant_mode`) migrates to `script_quant_mode="nf4_4bit"`.

CLI partial settings ([`src/cli/settings_merge.py`](../../src/cli/settings_merge.py)) accept the new keys when present.

## Inference profile log
`format_inference_profile_report` includes `quant=<mode>` per role next to the band and profile label, so each `[Aquaduct][inference_profile]` line records both **what** profile was selected and **how** the model was loaded.

## Tests
- [`tests/models/test_quantization_policy.py`](../../tests/models/test_quantization_policy.py) — labels, role-supported modes, settings normalization, VRAM multipliers, hint parsing, `pick_auto_mode` thresholds.
- [`tests/models/test_quant_loader_chain.py`](../../tests/models/test_quant_loader_chain.py) — mocked LLM `BitsAndBytesConfig` selection per `quant_mode`, CPU fallback.
- [`tests/models/test_auto_fit.py`](../../tests/models/test_auto_fit.py) — Auto-fit picks both repo and quant for low / high VRAM hosts.
- [`tests/ui/test_ui_settings_quantization.py`](../../tests/ui/test_ui_settings_quantization.py) — save / load roundtrip, `try_llm_4bit` migration, alias / unknown-mode handling.

## Risk controls
Experimental quantization is **opt-in and capability-checked**. `optimum-quanto`, `torchao`, and other backend-specific quant packages are **not** required. If a chosen mode is unsupported for a model / backend, Aquaduct logs a warning and falls back to the nearest stable mode rather than failing the run.

## Related docs
- [Config](config.md) — `*_quant_mode` fields, GPU policy
- [Hardware + model fit](hardware.md) — `vram_requirement_hint` and fit badges
- [VRAM inference profiles](inference_profiles.md) — bands, profile selection
- [Models + downloads](models.md) — curated repos
- [Settings tab](../ui/ui.md) — UI placement of dropdowns and Auto-fit
- [Brain](../pipeline/brain.md), [Artist](../pipeline/artist.md) — loader paths
