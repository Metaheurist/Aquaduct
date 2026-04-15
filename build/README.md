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
.\build\build.ps1 -Clean -OneFile
```

## Output
- `--onedir` (default): `dist\ai-news-factory\ai-news-factory.exe`
- `--onefile`: `dist\ai-news-factory.exe`

## Runtime downloads
The EXE will still download models and FFmpeg on first run into:
- `.cache/` (relative to the working directory)

## Notes / common issues
- **Torch + CUDA packaging**: PyInstaller often works best when you build on the same machine you run on, with the same GPU drivers/CUDA runtime.
- **bitsandbytes on Windows**: If 4-bit LLM fails on some setups, the app falls back to a template script so the pipeline still runs.

