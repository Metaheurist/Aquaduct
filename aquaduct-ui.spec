# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import copy_metadata

datas = [('requirements.txt', '.'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\artist.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\brain.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\branding.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\characters.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\config.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\crawler.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\editor.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\elevenlabs.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\ffmpeg.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\hardware.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\main.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\models.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\model_youtube_demos.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\tiktok.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\ui.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\voice.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\vram.md', 'docs'), ('C:\\Users\\OnceU\\OneDrive\\Documents\\GitHub\\Aquaduct\\docs\\youtube.md', 'docs')]
binaries = []
hiddenimports = ['PIL', 'soundfile', 'pyttsx3', 'requests', 'charset_normalizer', 'urllib3', 'certifi', 'src.elevenlabs_tts', 'src.characters_store', 'main', 'UI', 'UI.ui_app', 'UI.app', 'UI.main_window', 'UI.theme', 'UI.workers', 'UI.paths', 'UI.tabs', 'UI.tabs.characters_tab', 'UI.tabs.api_tab', 'UI.tabs.run_tab', 'imageio_ffmpeg', 'imageio.plugins.ffmpeg', 'imageio.plugins.pillow', 'dotenv']
datas += copy_metadata('imageio')
datas += copy_metadata('imageio-ffmpeg')
datas += copy_metadata('moviepy')
datas += copy_metadata('proglog')
datas += copy_metadata('decorator')
datas += copy_metadata('tqdm')
datas += copy_metadata('torch')
datas += copy_metadata('transformers')
datas += copy_metadata('diffusers')
datas += copy_metadata('huggingface_hub')
datas += copy_metadata('accelerate')
datas += copy_metadata('safetensors')
datas += copy_metadata('bitsandbytes')
hiddenimports += collect_submodules('src')
hiddenimports += collect_submodules('debug')
hiddenimports += collect_submodules('UI')
tmp_ret = collect_all('moviepy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('imageio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('imageio_ffmpeg')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PyQt6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('soundfile')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['UI\\ui_app.py'],
    pathex=[],
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
    name='aquaduct-ui',
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
