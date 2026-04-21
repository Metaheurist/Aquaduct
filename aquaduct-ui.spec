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
    "UI.theme.palette",
    "UI.workers",
    "UI.workers.impl",
    "UI.services.paths",
    "UI.services.library_fs",
    "UI.widgets.tab_sections",
    "UI.dialogs.tutorial_dialog",
    "UI.help.tutorial_links",
    "UI.widgets.no_wheel_controls",
    "UI.widgets.model_execution_toggle",
    "UI.widgets.gpu_policy_toggle",
    "UI.services.api_model_widgets",
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
    "UI.tabs.picture_tab",
    "UI.widgets.title_bar_outline_button",
    "UI.dialogs.startup_splash",
    "UI.widgets.media_mode_toggle",
    "UI.dialogs.frameless_dialog",
    "UI.dialogs.preview_dialog",
    "UI.dialogs.storyboard_dialog",
    "UI.dialogs.resource_graph_dialog",
    "UI.dialogs.download_popup",
    "UI.services.brain_expand",
    "UI.services.progress_tasks",
    "UI.dialogs.install_deps_dialog",
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
try:
    datas += copy_metadata("python-dotenv")
except Exception:
    pass
try:
    datas += copy_metadata("psutil")
except Exception:
    pass
try:
    datas += copy_metadata("rich")
except Exception:
    pass
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

# Runtime deps from requirements.txt (often missed by graph analysis on onefile builds).
for _pkg in ("psutil", "rich", "bs4", "lxml", "dotenv"):
    try:
        tmp_ret = collect_all(_pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

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
