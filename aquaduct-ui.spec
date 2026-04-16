# -*- mode: python ; coding: utf-8 -*-
# Kept in sync with build/build.ps1 (-UI). Prefer .\build\build.ps1 for reproducible builds.
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

# PyInstaller injects SPECPATH (directory containing this spec).
try:
    _root = SPECPATH  # type: ignore[name-defined]
except NameError:  # pragma: no cover
    _root = os.path.abspath('.')

datas = []
binaries = []
hiddenimports = [
    "PIL",
    "main",
    "soundfile",
    "dotenv",
    "imageio_ffmpeg",
    "imageio.plugins.ffmpeg",
    "imageio.plugins.pillow",
    "UI",
    "UI.ui_app",
    "UI.app",
    "UI.main_window",
    "UI.theme",
    "UI.workers",
    "UI.paths",
    "UI.tabs",
]

for pkg in (
    "imageio",
    "imageio-ffmpeg",
    "moviepy",
    "proglog",
    "decorator",
    "tqdm",
    "torch",
    "transformers",
    "diffusers",
    "huggingface_hub",
    "accelerate",
    "safetensors",
    "bitsandbytes",
):
    datas += copy_metadata(pkg)

datas.append((os.path.join(_root, "requirements.txt"), "."))

for pkg in ("moviepy", "imageio", "imageio_ffmpeg", "PyQt6", "soundfile"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

hiddenimports += collect_submodules("src")
hiddenimports += collect_submodules("UI")

a = Analysis(
    [os.path.join(_root, "UI", "ui_app.py")],
    pathex=[_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="aquaduct-ui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
