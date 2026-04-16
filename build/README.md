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

# Desktop UI (recommended for the TikTok console)
.\build\build.ps1 -Clean -UI -OneFile
```

## Output
- `--onedir` (default): `dist\ai-news-factory\ai-news-factory.exe`
- `--onefile` (CLI): `dist\ai-news-factory.exe`
- `--onefile` + `-UI`: `dist\ai-news-factory-ui.exe`

## Runtime downloads
The EXE will still download models and FFmpeg on first run into:
- `.cache/` (relative to the working directory)

The build script also bundles `requirements.txt` and uses `--collect-submodules` for `src` (and `UI` for desktop builds) so PyInstaller picks up the full package tree plus common ML/media metadata (`--copy-metadata` / `--collect-all` where needed).

## Notes / common issues
- **UI console**: UI builds use `--noconsole` (no terminal window). To see tracebacks, run `dist\ai-news-factory-ui.exe -debug` or `--debug` (allocates a console on Windows).
- **Torch + CUDA packaging**: PyInstaller often works best when you build on the same machine you run on, with the same GPU drivers/CUDA runtime.
- **bitsandbytes on Windows**: If 4-bit LLM fails on some setups, the app falls back to a template script so the pipeline still runs.
- **PyInstaller + bitsandbytes**: You may see many `Library not found` warnings for CUDA DLLs (`cudart64_*.dll`, `cublas*.dll`, etc.). That is normal on a machine without the full CUDA toolkit in PATH; PyInstaller still bundles `bitsandbytes`, and at runtime CUDA comes from the NVIDIA driver/toolkit where installed.
- **PyInstaller + torch**: You may see a warning about `torch.utils.tensorboard` / missing `tensorboard`; it is optional for this app and can be ignored unless you use TensorBoard.

