# Build Windows EXE (PyInstaller)

This folder contains the scripts to build a Windows executable for the project.

## Build

From the repo root:

```powershell
.\build\build.ps1 -Clean
```

## Build the desktop UI EXE

```powershell
.\build\build.ps1 -Clean -UI
```

### One-file EXE (optional)
```powershell
# CLI (main.py)
.\build\build.ps1 -Clean -OneFile

# Desktop UI (recommended — Aquaduct window)
.\build\build.ps1 -Clean -UI -OneFile
```

## Output
- `--onedir` (default): `dist\aquaduct\aquaduct.exe`
- `--onefile` (CLI): `dist\aquaduct.exe`
- `--onefile` + `-UI`: `dist\aquaduct-ui.exe`

## Runtime downloads
The EXE will still download models and FFmpeg on first run into:
- `.cache/` (relative to the working directory)

The build script also bundles `requirements.txt`, optional `docs/*.md` (UI builds), and uses `--collect-submodules` for `src` (and `UI` for desktop builds) so PyInstaller picks up the full package tree plus common ML/media metadata (`--copy-metadata` / `--collect-all` where needed). Extra hidden imports cover **HTTPS** (`requests`, `urllib3`, `certifi`, `charset_normalizer` for ElevenLabs / APIs), **local TTS** (`pyttsx3`), and modules such as **`src.elevenlabs_tts`** / **`src.characters_store`** that static analysis can miss in `--onefile` mode.

## Notes / common issues
- **UI dialogs**: The desktop app uses borderless modal dialogs (`UI/frameless_dialog.py`); `collect_submodules('UI')` in the spec includes them. If you add a new top-level `UI/*.py` module, prefer imports from the main window chain or extend the spec’s hidden imports.
- **UI console**: UI builds use `--noconsole` (no terminal window). To see tracebacks, run `dist\aquaduct-ui.exe -debug` or `--debug` (allocates a console on Windows).
- **Torch + CUDA packaging**: PyInstaller often works best when you build on the same machine you run on, with the same GPU drivers/CUDA runtime.
- **bitsandbytes on Windows**: If 4-bit LLM fails on some setups, the app falls back to a template script so the pipeline still runs.
- **PyInstaller + bitsandbytes**: You may see many `Library not found` warnings for CUDA DLLs (`cudart64_*.dll`, `cublas*.dll`, etc.). That is normal on a machine without the full CUDA toolkit in PATH; PyInstaller still bundles `bitsandbytes`, and at runtime CUDA comes from the NVIDIA driver/toolkit where installed.
- **PyInstaller + torch**: You may see a warning about `torch.utils.tensorboard` / missing `tensorboard`; it is optional for this app and can be ignored unless you use TensorBoard.
- **ElevenLabs / HTTPS**: If the frozen app fails to reach the API with SSL errors, verify `certifi` is bundled (the script uses `--collect-all certifi`). Stay on a current `pyinstaller` from `requirements-dev.txt` (installed before building).

