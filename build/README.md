# Build Windows EXE (PyInstaller)

This folder contains the scripts to build a Windows executable for the project.

Canonical driver: **`build/build.ps1`** (onedir / onefile flags, docs glob, metadata).  
Portable mirror: **`aquaduct-ui.spec`** at repo root (same hidden imports + `docs/*.md` via `SPECPATH`; default **onefile** windowless). Build either way with `-UseSpec` (see below).

**Build venv (recommended):** use **`-Clean`** so **`.venv-build`** is only for packaging. The script runs **`scripts/install_pytorch.py --with-rest`** (installs **torch** / **torchvision** / **torchaudio** for this PC’s CUDA or CPU, then **`requirements.txt`** — torch is not listed there, so no second torch install), then **`requirements-build.txt`** (**PyInstaller** only). Run **pytest** from a separate dev venv with **`requirements-dev.txt`**. Optional **`build/build.ps1 -IncludeDevDeps`** restores the old behavior (install **full** `requirements-dev.txt` into the build venv).

## Build

From the repo root:

```powershell
.\build\build.ps1 -Clean
```

## Build the desktop UI EXE

```powershell
.\build\build.ps1 -Clean -UI
```

Successful UI builds run an **import smoke** automatically (`scripts/frozen_smoke.py` against the new EXE, using `AQUADUCT_IMPORT_SMOKE=1` in `UI/ui_app.py`). To run smoke manually after a build:

```powershell
python scripts\frozen_smoke.py
python scripts\frozen_smoke.py --exe dist\aquaduct-ui\aquaduct-ui.exe
python scripts\frozen_smoke.py --exe dist\aquaduct-ui.exe
```

### Build via spec (parity / CI)

```powershell
.\build\build.ps1 -Clean -UI -UseSpec
```

This invokes `pyinstaller aquaduct-ui.spec` from the repo root (outputs **`dist\aquaduct-ui.exe`**, onefile). Use **`build.ps1 -UI`** without `-UseSpec` for the usual **onedir** layout and `-OneFile` choice.

### One-file EXE (optional)

```powershell
# CLI (main.py)
.\build\build.ps1 -Clean -OneFile

# Desktop UI (recommended — Aquaduct window)
.\build\build.ps1 -Clean -UI -OneFile
```

## Output

- `--onedir` (default): `dist\aquaduct\aquaduct.exe` or `dist\aquaduct-ui\aquaduct-ui.exe` with `-UI`
- `--onefile` (CLI): `dist\aquaduct.exe`
- `--onefile` + `-UI`: `dist\aquaduct-ui.exe`
- `-UseSpec`: `dist\aquaduct-ui.exe` (spec-defined onefile)

## Verification checklist (first ship)

1. **Smoke**: Build finished without errors; console shows `AQUADUCT_IMPORT_SMOKE_OK` during the post-build step (or run `python scripts\frozen_smoke.py --exe …` and exit code **0**).
2. **First launch**: Double-click the EXE from Explorer or run from `dist\…`; confirm the main window appears.
3. **Debug console**: Run `dist\aquaduct-ui\aquaduct-ui.exe -debug` (or `--debug`) to attach a Windows console and see tracebacks/logs. Optional categories: `dist\aquaduct-ui\aquaduct-ui.exe --debug pipeline,ui` (parsed before Qt; see `debug.debug_log`).
4. **Model / API**: Open the **Model** tab; switch **local vs API** execution if your build includes that control; confirm no crash when toggling.
5. **Scroll / combos**: Open tabs with combo boxes and scroll areas; confirm mouse wheel does not change combo values unexpectedly (wheel guard — `UI/no_wheel_controls.py`).
6. **HTTPS / APIs**: If you use ElevenLabs or other HTTPS features, exercise one short call; on SSL errors, confirm `certifi` is bundled (`--collect-all certifi` in the script).

## Runtime downloads

The EXE will still download models and FFmpeg on first run into:

- `.cache/` (relative to the working directory)

The build script bundles `requirements.txt`, optional `docs/*.md` (UI builds), and uses `--collect-submodules` for `src` (and `UI` for desktop builds) so PyInstaller picks up the full package tree plus common ML/media metadata (`--copy-metadata` / `--collect-all` where needed). Extra hidden imports cover **HTTPS** (`requests`, `urllib3`, `certifi`, `charset_normalizer` for ElevenLabs / APIs), **local TTS** (`pyttsx3`), and modules such as **`src.speech.elevenlabs_tts`** / **`src.content.characters_store`** that static analysis can miss in `--onefile` mode, plus **`UI.no_wheel_controls`**, **`UI.model_execution_toggle`**, **`UI.api_model_widgets`**, runtime **`src.runtime.pipeline_api`** / **`src.runtime.generation_facade`**, and tab modules under `UI.tabs.*`.

## Notes / common issues

- **UI dialogs**: The desktop app uses borderless modal dialogs (`UI/frameless_dialog.py`); `collect_submodules('UI')` in the spec includes them. If you add a new top-level `UI/*.py` module, prefer imports from the main window chain or extend hidden imports in **`build.ps1`** and **`aquaduct-ui.spec`** together.
- **UI console**: UI builds use `--noconsole` (no terminal window). To see tracebacks, run `dist\aquaduct-ui.exe -debug` or `--debug` (allocates a console on Windows; see `UI/ui_app.py`).
- **Torch + CUDA packaging**: PyInstaller often works best when you build on the same machine you run on, with the same GPU drivers/CUDA runtime.
- **bitsandbytes on Windows**: If 4-bit LLM fails on some setups, the app falls back to a template script so the pipeline still runs.
- **PyInstaller + bitsandbytes**: You may see many `Library not found` warnings for CUDA DLLs (`cudart64_*.dll`, `cublas*.dll`, etc.). That is normal on a machine without the full CUDA toolkit in PATH; PyInstaller still bundles `bitsandbytes`, and at runtime CUDA comes from the NVIDIA driver/toolkit where installed.
- **PyInstaller + torch**: You may see a warning about `torch.utils.tensorboard` / missing `tensorboard`; it is optional for this app and can be ignored unless you use TensorBoard.
- **ElevenLabs / HTTPS**: If the frozen app fails to reach the API with SSL errors, verify `certifi` is bundled (the script uses `--collect-all certifi`). Stay on a current **PyInstaller** from `requirements-build.txt` (installed by `build.ps1` before building).

For a longer operator-focused guide (prereqs, troubleshooting, data locations), see [`docs/building_windows_exe.md`](../docs/building_windows_exe.md).
