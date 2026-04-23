# API execution mode

## Overview

When **Model execution** is set to **API** (Model tab or persisted in `ui_settings.json`), the desktop pipeline uses **HTTP providers** for script (LLM), image stills, optional **Pro** text-to-video (**Kling AI** is the default *motion* option in the UI, with Magic Hour and Replicate as alternatives), and voice (OpenAI TTS, **Inworld**, or **ElevenLabs** when enabled) — instead of loading local Hugging Face diffusion / causal LM weights for those roles.

**FFmpeg** and MoviePy assembly still run locally for mux, captions, and music/SFX where enabled.

### Recommended provider defaults (UI catalog)

The per-role **Provider** / **Model** dropdowns list optional “recommended” entries first; approximate free-tier notes are in the label (see each vendor for current limits):

| Role | Suggested entry | Env keys (see table below) | Notes |
|------|-----------------|-----------------------------|--------|
| **LLM** | Google AI Studio (Gemini) | `GEMINI_API_KEY` or `GOOGLE_API_KEY` (fallback: saved / `OPENAI_API_KEY`) | OpenAI-compatible chat at Google’s `…/v1beta/openai` — large context, generous free daily quota. |
| **Image** | SiliconFlow | `SILICONFLOW_API_KEY` (fallback: saved bearer) | OpenAI-shaped `POST …/v1/images/generations` — Flux, SD3-class models (see catalog slugs). |
| **Video (Pro / motion)** | **Kling AI** (recommended) | `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` (optional `KLING_API_BASE` — default `https://api-singapore.klingai.com`) | Official **Open Platform** text-to-video: HS256 **JWT** auth, `POST /v1/videos/text2video` + poll. Free tier is often on the order of **~66 credits / 24h** (resets on a daily window) — enough for roughly **six high-quality ~5s** clips per day; confirm in the [Kling developer console](https://kling.ai/dev). **Alternatives (UI):** **Pika** (Pika.art) is listed in product comparisons as **~30 credits / month** for lighter monthly use. **Magic Hour** and **Replicate** remain available in the same Video row. |
| **Voice** | Inworld | `INWORLD_API_KEY` (fallback: saved bearer) | `POST https://api.inworld.ai/tts/v1/voice` — set **Voice / speaker id** in the UI (e.g. `Sarah`). **Alternatives:** OpenAI `tts-1` / `tts-1-hd`, or ElevenLabs (API tab) when enabled. |

Implementation: [`src/settings/api_model_catalog.py`](../../src/settings/api_model_catalog.py) (metadata), [`src/platform/openai_client.py`](../../src/platform/openai_client.py) (LLM + DALL·E / SiliconFlow image client; Gemini base URL without an extra `/v1`), [`src/runtime/api_generation.py`](../../src/runtime/api_generation.py), [`src/platform/kling_client.py`](../../src/platform/kling_client.py) (Kling JWT + text-to-video + poll), [`src/platform/magichour_client.py`](../../src/platform/magichour_client.py), [`src/speech/inworld_tts.py`](../../src/speech/inworld_tts.py), [`src/runtime/pipeline_api.py`](../../src/runtime/pipeline_api.py), [`src/runtime/model_backend.py`](../../src/runtime/model_backend.py) (keys + preflight for Pro + Kling, Magic Hour, or Replicate).

## Environment variables (env wins over saved keys)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI Chat, Images, TTS; also used as fallback bearer for several compatible providers if their own env key is unset |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible API root when **LLM** base URL in the UI is empty (default host otherwise follows the selected LLM provider; see below) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Google AI Studio / Gemini (OpenAI-compatible script LLM when **Provider** = Google AI Studio) |
| `SILICONFLOW_API_KEY` | SiliconFlow image `images/generations` (when **Image** = SiliconFlow) |
| `KLING_ACCESS_KEY` / `KLING_SECRET_KEY` (aliases: `KLINGAI_*`) | Kling text-to-video (JWT, both required) |
| `KLING_API_BASE` | Optional Kling API origin override (default Singapore host above) |
| `MAGIC_HOUR_API_KEY` (or `MAGICHOUR_API_KEY`) | Magic Hour Pro text-to-video |
| `INWORLD_API_KEY` | Inworld TTS (when **Voice** = Inworld) |
| `REPLICATE_API_TOKEN` or `REPLICATE_API_KEY` | Replicate image / video predictions |
| `SILICONFLOW_BASE_URL` | Optional override; default `https://api.siliconflow.com` for SiliconFlow image |

Saved keys live in **Generation APIs** on the API tab (`api_openai_key`, `api_replicate_token` in `AppSettings`). The **OpenAI / LLM API key** field is the saved bearer for OpenAI, SiliconFlow, Inworld, and other compatible script/image/voice fallbacks when a provider-specific env variable is not set. **Kling** and **Magic Hour** use **environment variables only** for API credentials (Kling: access + secret for JWT); there are no extra saved fields for those two.

### Script LLM providers (OpenAI Chat Completions–compatible)

On the **Model** (API mode) and **API** tabs, the **LLM** row can use **OpenAI** or another host that speaks the same **`/v1/chat/completions`** JSON shape. Each provider picks a **default base URL** when the **Base URL** field is left empty; you can override with **Base URL** or `OPENAI_BASE_URL`.

| Provider | Typical env key (checked before `OPENAI_API_KEY`) | Notes |
|----------|-----------------------------------------------------|--------|
| OpenAI | `OPENAI_API_KEY` | DALL·E stills, OpenAI TTS, chat. |
| Google AI Studio (Gemini) | `GEMINI_API_KEY`, `GOOGLE_API_KEY` | OpenAI chat protocol; default base URL set from catalog. |
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

| Feature | Local | API (cloud providers) |
|---------|------|------------------------|
| Script | HF transformers | OpenAI-compatible chat → `VideoPackage` (OpenAI, **Gemini** via Google AI Studio, Groq, …) |
| Stills / slideshow | Local diffusion | OpenAI DALL·E, **SiliconFlow** (OpenAI `images` API), or **Replicate** image model/version id |
| Voice | Kokoro / pyttsx3 / ElevenLabs | **Inworld** TTS, OpenAI `tts-1` / `tts-1-hd`, or ElevenLabs (API tab) when enabled |
| Pro text-to-video | Local T2V / ZeroScope, etc. | **Kling** (default in UI; JWT + official API), or **Magic Hour**, or **Replicate** (version id) — MP4 clips |
| Motion (no slideshow) | Image + clip models | **Not supported** — use slideshow or Pro + Magic Hour or Replicate |

## Security

- API keys are stored in `ui_settings.json` unless you rely on environment variables.
- Do not commit real keys. Logs must not print `Authorization` headers (use redacted debug helpers).

## Characters tab (API mode)

- **Generate with LLM** uses the configured **LLM** API (OpenAI chat JSON) via [`generate_character_from_preset_openai`](../../src/content/brain_api.py); no local transformers load.
- **Generate portrait** uses the **Image** API path ([`generate_still_png_bytes`](../../src/runtime/api_generation.py)) — OpenAI DALL·E, SiliconFlow, or Replicate — matching slideshow stills. Save settings after configuring **Generation APIs**.

## Configuration

`model_execution_mode` is stored with other app settings (see [config.md](../reference/config.md)). Build and verify the desktop EXE: [building_windows_exe.md](../build/building_windows_exe.md).

## Script routing (`GenerationFacade`)

[`get_generation_facade`](../../src/runtime/generation_facade.py) returns a **local** implementation (Hugging Face script LLM via [`generate_script`](../../src/content/brain.py)) or an **API** implementation (OpenAI chat JSON via [`generate_script_openai`](../../src/content/brain_api.py)) based on `model_execution_mode`. [`main.run_once`](../../main.py) and [`run_once_api`](../../src/runtime/pipeline_api.py) both use this for the script package step so local and API paths stay aligned.

## Reliability

OpenAI, Replicate, Magic Hour, and other HTTP clients in this path use a small **retry with backoff** on transient status codes (for example 429, 502) where implemented before surfacing an error.

## Related UI

- **Model** tab: Local | API toggle; local HF controls are hidden in API mode.
- **API** tab: **Generation APIs** block (same fields gathered on Save as the Model tab routing).

## See also

- [API mode review checklist](../review/api_mode_checklist.md) — step-by-step QA runbook for verifying API-mode runs end to end.
