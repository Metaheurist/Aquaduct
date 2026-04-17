# Dependencies

This project is designed to run locally on Windows with an NVIDIA GPU (8GB VRAM).

## Python
- **Python**: 3.11+
- **Virtualenv**: recommended (`python -m venv .venv`)

## Desktop UI (optional)
- **PyQt6**: only required when using the graphical control panel (`python -m UI`). The headless `main.py` pipeline does not need it.

## Development / tests + build
- **`requirements-dev.txt`**: **pytest** stack plus **PyInstaller** (for `build/build.ps1`). **`pytest-qt`** is for `@pytest.mark.qt` tests (desktop UI). Core tests run without PyQt; full UI test runs need PyQt6 and pytest-qt. Pipeline **run-queue** payload shapes: [`tests/test_pipeline_run_queue_contract.py`](tests/test_pipeline_run_queue_contract.py) (no Qt); main-window queue behavior: [`tests/test_ui_main_window.py`](tests/test_ui_main_window.py).

## Core runtime libraries
- **requests / beautifulsoup4 / lxml**: scraping (Google News RSS + MarkTechPost fallback). Optional **Firecrawl** HTTP APIs when enabled in the app (API key via UI or `FIRECRAWL_API_KEY`). Optional **ElevenLabs** TTS when enabled (API key via UI or `ELEVENLABS_API_KEY`).
- **torch** / **torchvision** / **torchaudio**: install these **first** via [`scripts/install_pytorch.py`](scripts/install_pytorch.py) — it picks **CUDA 12.4** wheels when `nvidia-smi` (or WMI on Windows) sees an NVIDIA GPU, **CPU** wheels otherwise, and default **PyPI** builds on **macOS**. Then install the rest with `python scripts/install_pytorch.py --with-rest` or `pip install -r requirements.txt` (runtime deps live in one file; **`torch` is not listed** so CUDA wheels are not skipped).
- **transformers / accelerate / bitsandbytes**: local LLM inference (4-bit where supported)
- **diffusers / safetensors**: SDXL Turbo image generation
- **huggingface_hub**: “zero-touch” model download on first run; also used by the desktop **verify checksums** action (compare local `models/` snapshots to the Hub)

## Media
- **moviepy**: video editing/assembly
- **FFmpeg**: required by MoviePy for encoding; downloaded automatically into `.cache/ffmpeg/`
- **Pillow**: caption rendering and image fallback generation
- **numpy**: caption frame / image processing

## Audio
- **soundfile**: robust WAV writing/reading
- **pyttsx3**: offline fallback TTS (Windows SAPI) when Kokoro is not available
- **certifi** (via `requests`): HTTPS trust store for ElevenLabs and other HTTP clients; PyInstaller builds should bundle it (see `build/build.ps1`)

## Notes on Windows + 4-bit LLM
`bitsandbytes` support can be brittle on native Windows depending on the build and CUDA setup. This MVP includes a **fallback script template** if the LLM cannot be loaded, so the pipeline can still produce videos end-to-end.

