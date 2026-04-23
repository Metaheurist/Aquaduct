# Model inventory (local + API)

Curated **local** models come from `model_options()`; **API** providers from `api_model_catalog.PROVIDERS` and `default_models_for_provider`.

**Tiers** (`[Pro]`, `[Standard]`, `[Lite]`) are defined in `src/models/model_tiers.py`.

**Local VRAM** is the **heuristic** label from `vram_requirement_hint()` in `src/models/hardware.py` (quantization, offload, and settings change real needs). **API** rows use the provider’s cloud—**no local GPU** for that step.

---

## Local (Hugging Face) — `Model` tab, execution: Local

| Role | `repo_id` | Tier | Size hint (UI) | Speed | Typical GPU / RAM (heuristic) |
|------|-----------|------|----------------|-------|----------------------------------|
| script | `meta-llama/Llama-3.1-8B-Instruct` | Lite | 8B | fastest | ~ 3-8 GB VRAM |
| script | `Qwen/Qwen2.5-7B-Instruct` | Lite | 7B | fastest | ~ 3-8 GB VRAM |
| script | `Qwen/Qwen3-14B` | Standard | 14B | fastest | ~ 12-20 GB VRAM (14B, 4-bit target) |
| script | `Sao10K/Fimbulvetr-11B-v2` | Lite | 11B | faster | ~ 10-16 GB VRAM (11B) |
| script | `deepseek-ai/DeepSeek-V3` | Pro | 671B MoE | slow | ~ 40-64+ GB GPU or multi-GPU (671B MoE; ~37B active/token); ~685B on disk, large RAM if offloading |
| script | `sophosympatheia/Midnight-Miqu-70B-v1.5` | Pro | 70B | slow | ~ 40+ GB VRAM (70B, 4-bit target) |
| image | `black-forest-labs/FLUX.1.1-pro-ultra` | Pro | ~12-20GB | faster | ~ 12-20 GB VRAM (1.1 [pro] ultra; Hub access may be required) |
| image | `black-forest-labs/FLUX.1-dev` | Pro | ~16-24GB | slow | ~ 16-24 GB VRAM |
| image | `black-forest-labs/FLUX.1-schnell` | Lite | ~12-16GB | faster | ~ 12-16 GB VRAM |
| image | `stabilityai/stable-diffusion-3.5-large` | Pro | ~14-20GB | slow | ~ 14-20 GB VRAM |
| image | `stabilityai/stable-diffusion-3.5-medium` | Standard | ~10-14GB | faster | ~ 10-14 GB VRAM |
| image | `stabilityai/stable-diffusion-3.5-large-turbo` | Lite | ~8-12GB | fastest | ~ 8-12 GB VRAM |
| video | `Wan-AI/Wan2.2-T2V-A14B-Diffusers` | Standard | ~12-16GB | faster | ~ 12-16 GB VRAM |
| video | `genmo/mochi-1.5-final` | Standard | ~10-14GB | faster | ~ 10-14 GB VRAM |
| video | `THUDM/CogVideoX-5b` | Lite | ~6-10GB | fastest | ~ 6-10 GB VRAM |
| video | `Tencent/HunyuanVideo` | Pro | ~16-24GB+ | slow | ~ 16-24+ GB VRAM |
| video | `Lightricks/LTX-2` | Pro | ~24-40GB+ | slow | ~ 24-40+ GB VRAM at 4K-class settings (LTX-2; lower res/CPU offload may fit less) |
| voice | `hexgrad/Kokoro-82M` | Lite | 82M | fastest | CPU OK |
| voice | `OpenMOSS-Team/MOSS-VoiceGenerator` | Pro | ~2.1B | slow | ~ 8-12 GB+ VRAM (2B instruction TTS); CPU possible but very slow |

---

## API — `Model` + `API` tab, execution: API

One row per **provider + role + default model** from `default_models_for_provider`. Custom model ids and Replicate version strings are also supported in the UI.

| Provider | Role | `model` id | Tier | Local GPU for this step | Env keys (first listed) |
|----------|------|------------|------|--------------------------|------------------------|
| Google AI Studio (Gemini) — large context, ~1.5k req/day (free) | llm | `gemini-2.5-flash` | Standard | **No** | GEMINI_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY |
| Google AI Studio (Gemini) — large context, ~1.5k req/day (free) | llm | `gemini-2.5-pro` | Pro | **No** | GEMINI_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY |
| Google AI Studio (Gemini) — large context, ~1.5k req/day (free) | llm | `gemini-2.0-flash` | Standard | **No** | GEMINI_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY |
| SiliconFlow (Flux, SD3, …) — daily free credits | image | `black-forest-labs/FLUX.1-schnell` | Lite | **No** | SILICONFLOW_API_KEY, OPENAI_API_KEY |
| SiliconFlow (Flux, SD3, …) — daily free credits | image | `stabilityai/stable-diffusion-3-5-large` | Pro | **No** | SILICONFLOW_API_KEY, OPENAI_API_KEY |
| Kling AI (motion) — ~66 credits/day (24h reset), ≈6×5s HQ; alt: Pika ~30 cr/mo | video | `kling-v3` | Pro | **No** | KLING_ACCESS_KEY, KLING_SECRET_KEY |
| Kling AI (motion) — ~66 credits/day (24h reset), ≈6×5s HQ; alt: Pika ~30 cr/mo | video | `kling-v2-6` | Standard | **No** | KLING_ACCESS_KEY, KLING_SECRET_KEY |
| Kling AI (motion) — ~66 credits/day (24h reset), ≈6×5s HQ; alt: Pika ~30 cr/mo | video | `kling-v2-master` | Pro | **No** | KLING_ACCESS_KEY, KLING_SECRET_KEY |
| Kling AI (motion) — ~66 credits/day (24h reset), ≈6×5s HQ; alt: Pika ~30 cr/mo | video | `kling-v2-5-turbo` | Standard | **No** | KLING_ACCESS_KEY, KLING_SECRET_KEY |
| Magic Hour — generative video API, ~100 credits/day (free) | video | `default` | Pro | **No** | MAGIC_HOUR_API_KEY, MAGICHOUR_API_KEY |
| Magic Hour — generative video API, ~100 credits/day (free) | video | `ltx-2` | Pro | **No** | MAGIC_HOUR_API_KEY, MAGICHOUR_API_KEY |
| Magic Hour — generative video API, ~100 credits/day (free) | video | `wan-2.2` | Pro | **No** | MAGIC_HOUR_API_KEY, MAGICHOUR_API_KEY |
| Magic Hour — generative video API, ~100 credits/day (free) | video | `seedance` | Pro | **No** | MAGIC_HOUR_API_KEY, MAGICHOUR_API_KEY |
| Magic Hour — generative video API, ~100 credits/day (free) | video | `kling-3.0` | Pro | **No** | MAGIC_HOUR_API_KEY, MAGICHOUR_API_KEY |
| Magic Hour — generative video API, ~100 credits/day (free) | video | `kling-1.6` | Standard | **No** | MAGIC_HOUR_API_KEY, MAGICHOUR_API_KEY |
| Inworld — low-latency TTS (free tier) | voice | `inworld-tts-1.5-max` | Pro | **No** | INWORLD_API_KEY, OPENAI_API_KEY |
| Inworld — low-latency TTS (free tier) | voice | `inworld-tts-1.5-mini` | Lite | **No** | INWORLD_API_KEY, OPENAI_API_KEY |
| OpenAI | llm | `gpt-4o-mini` | Lite | **No** | OPENAI_API_KEY |
| OpenAI | llm | `gpt-4o` | Pro | **No** | OPENAI_API_KEY |
| OpenAI | image | `dall-e-3` | Pro | **No** | OPENAI_API_KEY |
| OpenAI | image | `dall-e-2` | Lite | **No** | OPENAI_API_KEY |
| OpenAI | video | `gpt-4o-mini` | Lite | **No** | OPENAI_API_KEY |
| OpenAI | video | `gpt-4o` | Pro | **No** | OPENAI_API_KEY |
| OpenAI | video | `dall-e-3` | Pro | **No** | OPENAI_API_KEY |
| OpenAI | video | `dall-e-2` | Lite | **No** | OPENAI_API_KEY |
| OpenAI | video | `tts-1` | Lite | **No** | OPENAI_API_KEY |
| OpenAI | video | `tts-1-hd` | Pro | **No** | OPENAI_API_KEY |
| OpenAI | voice | `tts-1` | Lite | **No** | OPENAI_API_KEY |
| OpenAI | voice | `tts-1-hd` | Pro | **No** | OPENAI_API_KEY |
| Groq | llm | `llama-3.3-70b-versatile` | Pro | **No** | GROQ_API_KEY, OPENAI_API_KEY |
| Groq | llm | `llama-3.1-8b-instant` | Lite | **No** | GROQ_API_KEY, OPENAI_API_KEY |
| Groq | llm | `qwen/qwen3-32b` | Pro | **No** | GROQ_API_KEY, OPENAI_API_KEY |
| Together AI | llm | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Pro | **No** | TOGETHER_API_KEY, OPENAI_API_KEY |
| Together AI | llm | `Qwen/Qwen3-32B` | Pro | **No** | TOGETHER_API_KEY, OPENAI_API_KEY |
| Mistral AI | llm | `mistral-small-latest` | Standard | **No** | MISTRAL_API_KEY, OPENAI_API_KEY |
| Mistral AI | llm | `mistral-large-latest` | Pro | **No** | MISTRAL_API_KEY, OPENAI_API_KEY |
| Mistral AI | llm | `open-mistral-nemo` | Standard | **No** | MISTRAL_API_KEY, OPENAI_API_KEY |
| OpenRouter | llm | `openai/gpt-4o-mini` | Lite | **No** | OPENROUTER_API_KEY, OPENAI_API_KEY |
| OpenRouter | llm | `anthropic/claude-sonnet-4.5` | Pro | **No** | OPENROUTER_API_KEY, OPENAI_API_KEY |
| OpenRouter | llm | `google/gemini-2.5-flash` | Lite | **No** | OPENROUTER_API_KEY, OPENAI_API_KEY |
| DeepSeek | llm | `deepseek-chat` | Standard | **No** | DEEPSEEK_API_KEY, OPENAI_API_KEY |
| DeepSeek | llm | `deepseek-reasoner` | Pro | **No** | DEEPSEEK_API_KEY, OPENAI_API_KEY |
| xAI (Grok) | llm | `grok-3-latest` | Pro | **No** | XAI_API_KEY, OPENAI_API_KEY |
| xAI (Grok) | llm | `grok-2-latest` | Pro | **No** | XAI_API_KEY, OPENAI_API_KEY |
| xAI (Grok) | llm | `grok-2-vision-latest` | Pro | **No** | XAI_API_KEY, OPENAI_API_KEY |
| Fireworks AI | llm | `accounts/fireworks/models/llama-v3p3-70b-instruct` | Pro | **No** | FIREWORKS_API_KEY, OPENAI_API_KEY |
| Fireworks AI | llm | `accounts/fireworks/models/qwen3-32b` | Pro | **No** | FIREWORKS_API_KEY, OPENAI_API_KEY |
| Cerebras | llm | `llama3.1-8b` | Lite | **No** | CEREBRAS_API_KEY, OPENAI_API_KEY |
| Cerebras | llm | `llama-3.3-70b` | Pro | **No** | CEREBRAS_API_KEY, OPENAI_API_KEY |
| Nebius AI Studio | llm | `meta-llama/Meta-Llama-3.3-70B-Instruct` | Pro | **No** | NEBIUS_API_KEY, OPENAI_API_KEY |
| Nebius AI Studio | llm | `Qwen/Qwen3-32B-Instruct` | Pro | **No** | NEBIUS_API_KEY, OPENAI_API_KEY |
| Replicate | image | `black-forest-labs/flux-schnell` | Lite | **No** | REPLICATE_API_TOKEN, REPLICATE_API_KEY |
| Replicate | image | `black-forest-labs/flux-1.1-pro` | Standard | **No** | REPLICATE_API_TOKEN, REPLICATE_API_KEY |
| Replicate | video | `black-forest-labs/flux-schnell` | Lite | **No** | REPLICATE_API_TOKEN, REPLICATE_API_KEY |
| Replicate | video | `black-forest-labs/flux-1.1-pro` | Standard | **No** | REPLICATE_API_TOKEN, REPLICATE_API_KEY |
| ElevenLabs | voice | `eleven_multilingual_v2` | Pro | **No** | ELEVENLABS_API_KEY |
| ElevenLabs | voice | `eleven_turbo_v2_5` | Standard | **No** | ELEVENLABS_API_KEY |

### Notes

- **OpenAI `video` role:** `default_models_for_provider` falls back to the provider’s full `model_slugs` tuple, so the Video row may list chat/image/TTS ids—use a real Pro text-to-video id from the provider’s docs, or choose **Kling / Magic Hour / Replicate** for motion.
- **Regenerate:** `python scripts/gen_model_inventory_md.py` from the repo root.
