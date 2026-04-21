# Building and verifying the Windows desktop EXE

Operator-focused guide for **PyInstaller** builds of the **Aquaduct** desktop UI (`aquaduct-ui`). For script flags and PyInstaller details, see **[`build/README.md`](../build/README.md)** (canonical).

## Prerequisites

- **Windows 10/11**, **Python 3.11 or 3.12** (avoid 3.14 for PyTorch wheels).
- Repo cloned; PowerShell **ExecutionPolicy** that allows `build/build.ps1` (e.g. `RemoteSigned` for your user scope).
- Enough disk space for a **`.venv-build`** (or your chosen venv dir) plus PyTorch and project wheels.

## Build environment (one clean venv)

The recommended flow avoids **duplicate PyTorch** installs and keeps **test wheels out** of the packaging environment:

1. **Fresh venv** — `.\build\build.ps1 -Clean` recreates **`.venv-build`** (only what the script installs).
2. **PyTorch for this machine** — [`scripts/install_pytorch.py`](../scripts/install_pytorch.py) **`--with-rest`** runs **`install_pytorch_for_hardware`** (CUDA index when an NVIDIA GPU is detected, else CPU wheels; macOS uses PyPI), then **`pip install -r requirements.txt`**. **`requirements.txt` does not list `torch`**, so pip does not reinstall torch a second time from that file.
3. **PyInstaller only** — **`pip install -r requirements-build.txt`** (not full **`requirements-dev.txt`**), so **pytest**, **pytest-qt**, etc. are not installed into **`.venv-build`**. Run the test suite from a separate dev venv (e.g. **`.venv`**) with **`requirements-dev.txt`**.
4. Optional — **`.\build\build.ps1 -IncludeDevDeps`** installs **`requirements-dev.txt`** into the build venv instead (legacy / debugging only).

## Golden-path build

From the **repository root**:

```powershell
.\build\build.ps1 -Clean -UI
```

This creates the **build venv**, runs the steps above, then runs **PyInstaller** in **onedir** mode with **`--noconsole`**, then **import smoke** (`scripts/frozen_smoke.py` against the new EXE).

Outputs:

- **Default UI onedir**: `dist\aquaduct-ui\aquaduct-ui.exe` and `_internal\` dependencies.

### One-file UI

```powershell
.\build\build.ps1 -Clean -UI -OneFile
```

Output: `dist\aquaduct-ui.exe`.

### Spec-based build (portable `aquaduct-ui.spec`)

```powershell
.\build\build.ps1 -Clean -UI -UseSpec
```

Uses **`aquaduct-ui.spec`** only (paths relative to the spec via `SPECPATH`). Default artifact: **`dist\aquaduct-ui.exe`** (onefile, windowless). Keep **`build.ps1`** and **`aquaduct-ui.spec`** hidden-import lists aligned when you add new top-level `UI/*.py` modules or rename `src.*` packages.

## Verify after build

1. **Automated**: Build log should show successful **`frozen_smoke`** (exit **0**). Manual:  
   `python scripts\frozen_smoke.py --exe dist\aquaduct-ui\aquaduct-ui.exe`
2. **Launch**: Run the EXE from Explorer; confirm the main window opens.
3. **Console / tracebacks**: `dist\aquaduct-ui\aquaduct-ui.exe -debug` or `--debug` (see [`UI/ui_app.py`](../UI/ui_app.py)).
4. **API mode smoke** (optional): Configure keys on the **API** tab, set **Model execution** to **API** on the **Model** tab ([api_generation.md](api_generation.md), [config.md](config.md)); run a short **Preview** or scripted run if you use API execution.

## First-run downloads (what the EXE still fetches)

The frozen app **does not** embed multi-gigabyte HF weights. On first use it may download:

- **Models** into `models/` (per [`models.md`](models.md) and Hugging Face cache behavior).
- **FFmpeg** into `.cache/ffmpeg/` ([`ffmpeg.md`](ffmpeg.md)).

User data and settings typically live under the app’s working directory or paths described in [config.md](config.md) (`get_paths()`).

## Troubleshooting

| Symptom | Things to check |
|--------|-------------------|
| SSL / HTTPS errors (ElevenLabs, OpenAI, etc.) | Build uses **`--collect-all certifi`**; run from a writable cwd; corporate TLS inspection may need extra trust. |
| Missing module at runtime (`ModuleNotFoundError` in `-debug`) | Add **`--hidden-import`** in **`build/build.ps1`** and the same name in **`aquaduct-ui.spec`** `hiddenimports`; prefer imports from the main window chain so `collect_submodules('UI')` sees new packages. |
| Huge EXE or slow extract | **Onefile** extracts to a temp dir each launch; **onedir** (`build.ps1 -UI` without `-OneFile`) is often faster to start. |

## Related documentation

- [Desktop UI](ui.md) — tabs, wheel guard, run queue.
- [API execution mode](api_generation.md) — OpenAI / Replicate paths when `model_execution_mode` is **api**.
- [Main / CLI](main.md) — headless vs UI launcher.
- [Dependencies](../DEPENDENCIES.md) — PyTorch install, test tiers.
