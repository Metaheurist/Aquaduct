# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for desktop UI (portable paths). Prefer repo-root: pyinstaller aquaduct-ui.spec"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import copy_metadata

# Directory containing this spec file (repo root when spec lives next to main.py).
_ROOT = Path(SPECPATH).resolve()

datas = [(str(_ROOT / "requirements.txt"), ".")]
_docs = _ROOT / "docs"
if _docs.is_dir():
    for _md in sorted(_docs.glob("*.md")):
        datas.append((str(_md), "docs"))

binaries = []
hiddenimports = [
    "PIL",
    "soundfile",
    "pyttsx3",
    "requests",
    "charset_normalizer",
    "urllib3",
    "certifi",
    # Current package paths (belt-and-suspenders for --onefile static analysis)
    "src.speech.elevenlabs_tts",
    "src.content.characters_store",
    "main",
    "UI",
    "UI.ui_app",
    "UI.app",
    "UI.main_window",
    "UI.theme",
    "UI.workers",
    "UI.paths",
    "UI.library_fs",
    "UI.tab_sections",
    "UI.tutorial_dialog",
    "UI.tutorial_links",
    "UI.no_wheel_controls",
    "UI.model_execution_toggle",
    "UI.api_model_widgets",
    "UI.tabs",
    "UI.tabs.characters_tab",
    "UI.tabs.api_tab",
    "UI.tabs.run_tab",
    "UI.tabs.settings_tab",
    "UI.tabs.video_tab",
    "UI.tabs.effects_tab",
    "UI.tabs.topics_tab",
    "UI.tabs.tasks_tab",
    "UI.tabs.branding_tab",
    "UI.tabs.captions_tab",
    "UI.tabs.my_pc_tab",
    "UI.tabs.library_tab",
    "src.util.cpu_parallelism",
    "src.runtime.pipeline_api",
    "src.runtime.generation_facade",
    "imageio_ffmpeg",
    "imageio.plugins.ffmpeg",
    "imageio.plugins.pillow",
    "dotenv",
]
datas += copy_metadata("imageio")
datas += copy_metadata("imageio-ffmpeg")
datas += copy_metadata("moviepy")
datas += copy_metadata("proglog")
datas += copy_metadata("decorator")
datas += copy_metadata("tqdm")
datas += copy_metadata("torch")
datas += copy_metadata("transformers")
datas += copy_metadata("diffusers")
datas += copy_metadata("huggingface_hub")
datas += copy_metadata("accelerate")
datas += copy_metadata("safetensors")
datas += copy_metadata("bitsandbytes")
hiddenimports += collect_submodules("src")
hiddenimports += collect_submodules("debug")
hiddenimports += collect_submodules("UI")
tmp_ret = collect_all("moviepy")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all("imageio")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all("imageio_ffmpeg")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all("PyQt6")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all("soundfile")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all("certifi")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [str(_ROOT / "UI" / "ui_app.py")],
    pathex=[str(_ROOT)],
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
