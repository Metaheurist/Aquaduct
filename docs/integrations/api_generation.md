# API execution mode

## Overview

When **Model execution** is set to **API** (Model tab or persisted in `ui_settings.json`), the desktop pipeline uses **HTTP providers** for script (LLM), image stills, optional Replicate video (Pro), and optional OpenAI TTS or ElevenLabs — instead of loading local Hugging Face diffusion / causal LM weights for those roles.

**FFmpeg** and MoviePy assembly still run locally for mux, captions, and music/SFX where enabled.

## Environment variables (env wins over saved keys)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI Chat, Images, TTS; also used as fallback bearer for compatible LLM hosts if their env key is unset |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible API root when **LLM** base URL in the UI is empty (default host otherwise follows the selected LLM provider; see below) |
| `REPLICATE_API_TOKEN` or `REPLICATE_API_KEY` | Replicate predictions |

Saved keys live in **Generation APIs** on the API tab (`api_openai_key`, `api_replicate_token` in `AppSettings`). The **OpenAI / LLM API key** field is the saved bearer for OpenAI and for OpenAI-compatible script providers unless a provider-specific env variable is set.

### Script LLM providers (OpenAI Chat Completions–compatible)

On the **Model** (API mode) and **API** tabs, the **LLM** row can use **OpenAI** or another host that speaks the same **`/v1/chat/completions`** JSON shape. Each provider picks a **default base URL** when the **Base URL** field is left empty; you can override with **Base URL** or `OPENAI_BASE_URL`.

| Provider | Typical env key (checked before `OPENAI_API_KEY`) | Notes |
|----------|-----------------------------------------------------|--------|
| OpenAI | `OPENAI_API_KEY` | Images, TTS, and DALL·E still require OpenAI (or Replicate / ElevenLabs for image & voice as configured). |
| Groq | `GROQ_API_KEY` | Fast inference; script JSON mode depends on model support. |
| Together AI | `TOGETHER_API_KEY` | |
| Mistral AI | `MISTRAL_API_KEY` | |
| OpenRouter | `OPENROUTER_API_KEY` | Model id is often `vendor/model` (e.g. `openai/gpt-4o-mini`). |
| DeepSeek | `DEEPSEEK_API_KEY` | |
| xAI (Grok) | `XAI_API_KEY` | |
| Fireworks AI | `FIREWORKS_API_KEY` | |
| Cerebras | `CEREBRAS_API_KEY` | |
| Nebius AI Studio | `NEBIUS_API_KEY` | |

Catalog and suggested model ids: [`src/settings/api_model_catalog.py`](../../src/settings/api_model_catalog.py).

## Capability matrix

| Feature | Local | API (OpenAI-first) | API + Replicate |
|---------|------|--------------------|-----------------|
| Script | HF transformers | OpenAI chat JSON → `VideoPackage` | Same |
| Stills / slideshow | Local diffusion | OpenAI DALL·E or Replicate image | Replicate flux / SDXL |
| Voice | Kokoro / pyttsx3 / ElevenLabs | OpenAI `tts-1` or ElevenLabs | Same |
| Pro text-to-video | ZeroScope local | **Replicate** MP4 clips | Same |
| Motion (no slideshow) | Image + clip models | **Not supported** — use slideshow or Pro + Replicate |

## Security

- API keys are stored in `ui_settings.json` unless you rely on environment variables.
- Do not commit real keys. Logs must not print `Authorization` headers (use redacted debug helpers).

## Characters tab (API mode)

- **Generate with LLM** uses the configured **LLM** API (OpenAI chat JSON) via [`generate_character_from_preset_openai`](../../src/content/brain_api.py); no local transformers load.
- **Generate portrait** uses the **Image** API path ([`generate_still_png_bytes`](../../src/runtime/api_generation.py)) — OpenAI DALL·E or Replicate — matching slideshow stills. Save settings after configuring **Generation APIs**.

## Configuration

`model_execution_mode` is stored with other app settings (see [config.md](../reference/config.md)). Build and verify the desktop EXE: [building_windows_exe.md](../build/building_windows_exe.md).

## Script routing (`GenerationFacade`)

[`get_generation_facade`](../../src/runtime/generation_facade.py) returns a **local** implementation (Hugging Face script LLM via [`generate_script`](../../src/content/brain.py)) or an **API** implementation (OpenAI chat JSON via [`generate_script_openai`](../../src/content/brain_api.py)) based on `model_execution_mode`. [`main.run_once`](../../main.py) and [`run_once_api`](../../src/runtime/pipeline_api.py) both use this for the script package step so local and API paths stay aligned.

## Reliability

OpenAI and Replicate **create-prediction** HTTP calls use a small **retry with backoff** on transient status codes (for example 429, 502) before surfacing an error.

## Related UI

- **Model** tab: Local | API toggle; local HF controls are hidden in API mode.
- **API** tab: **Generation APIs** block (same fields gathered on Save as the Model tab routing).
