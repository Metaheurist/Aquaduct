# Dependencies

This project is designed to run locally on Windows with an NVIDIA GPU (8GB VRAM).

## Python
- **Python**: 3.11+
- **Virtualenv**: recommended (`python -m venv .venv`)

## Core runtime libraries
- **requests / beautifulsoup4 / lxml**: scraping (Google News RSS + MarkTechPost fallback)
- **torch**: GPU compute for LLM and diffusion (when available)
- **transformers / accelerate / bitsandbytes**: local LLM inference (4-bit where supported)
- **diffusers / safetensors**: SDXL Turbo image generation
- **huggingface_hub**: “zero-touch” model download on first run

## Media
- **moviepy**: video editing/assembly
- **FFmpeg**: required by MoviePy for encoding; downloaded automatically into `.cache/ffmpeg/`
- **Pillow**: caption rendering and image fallback generation
- **numpy**: caption frame / image processing

## Audio
- **soundfile**: robust WAV writing/reading
- **pyttsx3**: offline fallback TTS (Windows SAPI) when Kokoro is not available

## Notes on Windows + 4-bit LLM
`bitsandbytes` support can be brittle on native Windows depending on the build and CUDA setup. This MVP includes a **fallback script template** if the LLM cannot be loaded, so the pipeline can still produce videos end-to-end.

