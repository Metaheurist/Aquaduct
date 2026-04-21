# YouTube demos for curated models (reference)

Third-party tutorials and demos for models exposed in **Settings → Models**. These are **not** official Aquaduct endorsements—channels, titles, and availability change over time. Some videos cover a **family** of checkpoints (e.g. “Qwen 2.5” generally) when no exact match exists.

**Source of truth for IDs:** `src/models/model_manager.py` → `model_options()`.

---

## Script models (LLM)

| UI label (short) | Hugging Face repo | Example YouTube demos |
|------------------|-------------------|------------------------|
| Qwen3 14B (curated default) | `Qwen/Qwen3-14B` | [Model card (Hugging Face)](https://huggingface.co/Qwen/Qwen3-14B) |
| Fimbulvetr 11B v2 (prose / Solar) | `Sao10K/Fimbulvetr-11B-v2` | [Model card (Hugging Face)](https://huggingface.co/Sao10K/Fimbulvetr-11B-v2) |
| Midnight Miqu 70B v1.5 (heavyweight) | `sophosympatheia/Midnight-Miqu-70B-v1.5` | [Model card (Hugging Face)](https://huggingface.co/sophosympatheia/Midnight-Miqu-70B-v1.5) |
| DeepSeek-V3 (671B MoE) | `deepseek-ai/DeepSeek-V3` | [Model card (Hugging Face)](https://huggingface.co/deepseek-ai/DeepSeek-V3) |

---

## Video / image models

| UI label (short) | Hugging Face repo | Example YouTube demos |
|------------------|-------------------|------------------------|
| FLUX.1.1 [pro] ultra (curated) | `black-forest-labs/FLUX.1.1-pro-ultra` | [BFL: FLUX1.1 [pro] Ultra](https://blackforestlabs.ai/flux-1-1-ultra/) · [BFL on Hugging Face](https://huggingface.co/black-forest-labs) |
| SDXL Turbo (1-step images) | `stabilityai/sdxl-turbo` | [SDXL Turbo — demo & walkthrough](https://www.youtube.com/watch?v=DCULthT6whw) · [Real-time text-to-image](https://www.youtube.com/watch?v=63SD_DnoSuE) · [SDXL Turbo hands-on](https://www.youtube.com/watch?v=vOBi06l5ruY) |
| SD 1.5 (images, lightweight) | `runwayml/stable-diffusion-v1-5` | [Stable Diffusion demo and tutorial](https://www.youtube.com/watch?v=GtNhh-sgdjk) · [How to use SD v1.5 & download](https://www.youtube.com/watch?v=gWk8QyeGnm4) · [SD 1.5 custom models roundup](https://www.youtube.com/watch?v=G-oZn4H-aHQ) |
| SDXL Base 1.0 (images, higher quality) | `stabilityai/stable-diffusion-xl-base-1.0` | [SDXL 1.0 — let’s test it](https://www.youtube.com/watch?v=cp68gQ9BLxA) · [Install SDXL 1.0 base + refiner](https://www.youtube.com/watch?v=nLz9Hksq71I) · [SDXL 1.0 release / Stability](https://www.youtube.com/watch?v=JuE347R6MdQ) |
| SVD XT + SDXL Turbo keyframes (pair) | `stabilityai/stable-video-diffusion-img2vid-xt` + `stabilityai/sdxl-turbo` | **SVD:** [Stable Video Diffusion — img2vid XT](https://www.youtube.com/watch?v=12TOIY5y6JE) · [SVD XT 1.1 image2video](https://www.youtube.com/watch?v=3dH6Q6N-RT8) · [Image2video SVD tutorial](https://www.youtube.com/watch?v=HOVYu2UbgEE) · **SDXL Turbo:** links in SDXL Turbo row above |
| ZeroScope v2 576w | `cerspense/zeroscope_v2_576w` | [Zeroscope v2 — A1111 WebUI](https://www.youtube.com/watch?v=OCs7YnqB-JA) · [Zeroscope text2video overview](https://www.youtube.com/watch?v=zPnUhcQsvr0) · [Zeroscope Colab tutorial](https://www.youtube.com/watch?v=Tl8YwqPQ9q8) |

---

## Voice models (TTS)

| UI label (short) | Hugging Face repo | Example YouTube demos |
|------------------|-------------------|------------------------|
| Kokoro 82M | `hexgrad/Kokoro-82M` | [Kokoro-82M — open source TTS](https://www.youtube.com/watch?v=L7D-xLRS1oU) · [Kokoro local TTS + custom voices](https://www.youtube.com/watch?v=tl1wvZXlj0I) · [Kokoro TTS setup + API](https://www.youtube.com/watch?v=vf3Xa_WcsIg) |
| MOSS VoiceGenerator | `OpenMOSS-Team/MOSS-VoiceGenerator` | [Model card (HF)](https://huggingface.co/OpenMOSS-Team/MOSS-VoiceGenerator) |

---

## See also

- [Models + downloads](./models.md) — where files live and how downloads work  
- [Hugging Face Hub](https://huggingface.co/) — model cards and community spaces for live demos (not YouTube)
