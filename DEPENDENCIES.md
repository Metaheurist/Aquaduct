# Dependencies

This project is designed to run locally on Windows with an NVIDIA GPU (8GB VRAM).

## Python
- **Python**: 3.11+
- **Virtualenv**: recommended (`python -m venv .venv`)
- **Windows shell**: after `cd` to the repo, you can dot-source [`scripts/setup_terminal_env.ps1`](scripts/setup_terminal_env.ps1) (`. .\scripts\setup_terminal_env.ps1`) to activate `.venv` and set the working directory; optional **`HF_TOKEN`** / **`HUGGINGFACEHUB_API_TOKEN`** for gated Hugging Face models (or use **Settings → API** in the UI).

### System-wide install (optional; Windows)
Use this only if you want packages in a **global** Python instead of `.venv`.

- **Avoid Python 3.14 as the default target** for PyTorch: `torchaudio` (and sometimes full CUDA stacks) may have **no wheels** yet. Prefer **Python 3.11 or 3.12** (e.g. `C:\Program Files\Python312\python.exe` if installed).
- From the repo root, using **Python 3.12** explicitly:

```powershell
cd C:\path\to\Aquaduct
& "C:\Program Files\Python312\python.exe" scripts\install_pytorch.py --with-rest
```

- To target a specific interpreter regardless of how you invoked the script:

```powershell
python scripts\install_pytorch.py --with-rest --python "C:\Program Files\Python312\python.exe"
```

- If `Program Files` is not writable, pip may use **per-user** site-packages (`Defaulting to user installation`); add `%APPDATA%\Python\Python312\Scripts` to **PATH** if `pip`/`python` scripts are not found.
- Running the app: `& "C:\Program Files\Python312\python.exe" main.py` or `python -m UI` with that same interpreter.

### Install PyTorch in both `.venv` and a global Python (Windows)
Use **one** command that runs the installer for each interpreter (PyTorch + CUDA/CPU detection runs per target):

```powershell
cd C:\path\to\Aquaduct
python scripts\install_pytorch.py --with-rest `
  --python ".\.venv\Scripts\python.exe" `
  --python "C:\Program Files\Python312\python.exe"
```

Or run the helper (defaults global to Python 3.12 under Program Files; skips venv if missing):

```powershell
.\scripts\install_pytorch_venv_and_global.ps1
```

By default the helper streams to the console **and** appends to **`logs/install-pytorch.log`** (under the repo; the folder is gitignored). Console-only:

```powershell
.\scripts\install_pytorch_venv_and_global.ps1 -NoLog
```

A different log path (relative paths resolve under the repo root):

```powershell
.\scripts\install_pytorch_venv_and_global.ps1 -LogFile logs\custom-install.log
```

PyTorch-only (no `requirements.txt`) for both: add `-PyTorchOnly` to the `.ps1`, or omit `--with-rest` when calling `install_pytorch.py` directly.

## Desktop UI (optional)
- **PyQt6**: only required when using the graphical control panel (`python -m UI`). The headless `main.py` pipeline does not need it.

## Development / tests + build
- **`requirements-dev.txt`**: **pytest** stack plus **PyInstaller** (for `build/build.ps1`). **`pytest-qt`** is for `@pytest.mark.qt` tests (desktop UI). Core tests run without PyQt; full UI test runs need PyQt6 and pytest-qt. Pipeline **run-queue** payload shapes: [`tests/test_pipeline_run_queue_contract.py`](tests/test_pipeline_run_queue_contract.py) (no Qt); main-window queue behavior: [`tests/test_ui_main_window.py`](tests/test_ui_main_window.py).

## Core runtime libraries
- **requests / beautifulsoup4 / lxml**: scraping (Google News RSS + MarkTechPost fallback). Optional **Firecrawl** HTTP APIs when enabled in the app (API key via UI or `FIRECRAWL_API_KEY`). Optional **ElevenLabs** TTS when enabled (API key via UI or `ELEVENLABS_API_KEY`).
- **torch** / **torchvision** / **torchaudio**: install these **first** via [`scripts/install_pytorch.py`](scripts/install_pytorch.py) — it picks **CUDA 12.4** wheels when `nvidia-smi` (or WMI on Windows) sees an NVIDIA GPU, **CPU** wheels otherwise, and default **PyPI** builds on **macOS**. Then install the rest with `python scripts/install_pytorch.py --with-rest` or `pip install -r requirements.txt` (runtime deps live in one file; **`torch` is not listed** so CUDA wheels are not skipped).
- **Desktop UI**: **Model → Install dependencies** runs the same PyTorch-then-`requirements.txt` flow in a modal dialog ([`UI/install_deps_dialog.py`](UI/install_deps_dialog.py)) with streamed pip output. The bar is **indeterminate** until pip emits tqdm-style lines with a **`%`**, then shows **determinate 0–100%** ([`src/torch_install.py`](src/torch_install.py): `run_subprocess_streaming`, `pip_download_percent`, `--progress-bar on` injection). If pip stays quiet (large wheels, older pip), the bar may remain indeterminate; the log and status line still update when lines appear.
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

