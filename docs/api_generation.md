# API execution mode

## Overview

When **Model execution** is set to **API** (Model tab or persisted in `ui_settings.json`), the desktop pipeline uses **HTTP providers** for script (LLM), image stills, optional Replicate video (Pro), and optional OpenAI TTS or ElevenLabs — instead of loading local Hugging Face diffusion / causal LM weights for those roles.

**FFmpeg** and MoviePy assembly still run locally for mux, captions, and music/SFX where enabled.

## Environment variables (env wins over saved keys)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI Chat, Images, TTS |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible API root (default `https://api.openai.com/v1`) |
| `REPLICATE_API_TOKEN` or `REPLICATE_API_KEY` | Replicate predictions |

Saved keys live in **Generation APIs** on the API tab (`api_openai_key`, `api_replicate_token` in `AppSettings`).

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

## Related UI

- **Model** tab: Local | API toggle; local HF controls are hidden in API mode.
- **API** tab: **Generation APIs** block (same fields gathered on Save as the Model tab routing).
