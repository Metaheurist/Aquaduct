# YouTube demos for curated models (reference)

Third-party tutorials and demos for models exposed in **Settings → Models**. These are **not** official Aquaduct endorsements—channels, titles, and availability change over time. Some videos cover a **family** of checkpoints (e.g. “Qwen 2.5” generally) when no exact match exists.

**Source of truth for IDs:** `src/model_manager.py` → `model_options()`.

---

## Script models (LLM)

| UI label (short) | Hugging Face repo | Example YouTube demos |
|------------------|-------------------|------------------------|
| Qwen2.5 1.5B Instruct (very small) | `Qwen/Qwen2.5-1.5B-Instruct` | [Qwen2 1.5B LLM — install locally and test](https://www.youtube.com/watch?v=pY-q6ewixok) · [Qwen-2.5 & Coder (fully tested)](https://www.youtube.com/watch?v=tdLZxwq0Jrg) |
| Qwen2.5 3B Instruct | `Qwen/Qwen2.5-3B-Instruct` | [Qwen2.5 — install and test locally (family)](https://www.youtube.com/watch?v=x97BWsrmjpU) · [Qwen2.5-Coder — local setup](https://www.youtube.com/watch?v=lN_0PTMvbvM) |
| Phi-3.5 Mini Instruct | `microsoft/Phi-3.5-mini-instruct` | [Phi-3.5 Mini Instruct — installed and tested locally](https://www.youtube.com/watch?v=uIcyGDOJoA0) · [Phi-3.5 Mini realtime voice assistant (Colab)](https://www.youtube.com/watch?v=E-BJM2sGbFc) |
| Llama 3.2 3B Instruct | `meta-llama/Llama-3.2-3B-Instruct` | [Llama 3.2 3B Instruct — install locally](https://www.youtube.com/watch?v=xTgyrC-HZ7o) · [LLaMA 3.2 is here (overview)](https://www.youtube.com/watch?v=nUeIjs3THNM) |
| Mistral 7B Instruct v0.3 | `mistralai/Mistral-7B-Instruct-v0.3` | [Mistral-7B-Instruct v0.3 — install and test](https://www.youtube.com/watch?v=ZXsGMyn-jJ0) · [Mistral-7B-Instruct v0.3 — review](https://www.youtube.com/watch?v=MlzCSRnYYF4) · [Mistral-AI playlist (fine-tuning, tools)](https://www.youtube.com/playlist?list=PLVEEucA9MYhMD4lZRYZrQORojyioYN-Ue) |
| Qwen2.5 7B Instruct | `Qwen/Qwen2.5-7B-Instruct` | [Qwen2.5 7B Instruct — install and test locally](https://www.youtube.com/watch?v=2td5NYqIfOk) · [Qwen 2.5 Coder 7B tested](https://www.youtube.com/watch?v=x5hFKYjqmcE) |
| Llama 3.1 8B Instruct | `meta-llama/Meta-Llama-3.1-8B-Instruct` | [Run Llama 3.1 8B (several ways)](https://www.youtube.com/watch?v=QpGVF_kElQY) · [Install Llama 3.1 8B in minutes (Ollama)](https://www.youtube.com/watch?v=1ghNIb41f3Q) |

---

## Video / image models

| UI label (short) | Hugging Face repo | Example YouTube demos |
|------------------|-------------------|------------------------|
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
| MMS-TTS English (Meta, lightweight) | `facebook/mms-tts-eng` | [Model card (HF)](https://huggingface.co/facebook/mms-tts-eng) |
| MeloTTS English | `myshell-ai/MeloTTS-English` | [Model card (HF)](https://huggingface.co/myshell-ai/MeloTTS-English) |
| SpeechT5 TTS (Microsoft) | `microsoft/speecht5_tts` | [Model card (HF)](https://huggingface.co/microsoft/speecht5_tts) |
| Parler-TTS mini v1 (expressive) | `parler-tts/parler-tts-mini-v1` | [Parler-TTS — Hugging Face intro](https://www.youtube.com/watch?v=VQrT1iZ6_nc) · [Model card (HF)](https://huggingface.co/parler-tts/parler-tts-mini-v1) |
| coqui XTTS v2 | `coqui/XTTS-v2` | [Coqui XTTS on Windows — local cloning](https://www.youtube.com/watch?v=HJB17HW4M9o) · [XTTS2 — clone voices](https://www.youtube.com/watch?v=pNTTTwap12Y) · [AI voice clone with Colab + XTTSv2](https://www.youtube.com/watch?v=CgDs8WL5YSE) |
| Bark (high quality, very large) | `suno/bark` | [Bark — AI research walkthrough](https://www.youtube.com/watch?v=qWoX5HmWTO0) · [Model card (HF)](https://huggingface.co/suno/bark) |

---

## See also

- [Models + downloads](./models.md) — where files live and how downloads work  
- [Hugging Face Hub](https://huggingface.co/) — model cards and community spaces for live demos (not YouTube)
