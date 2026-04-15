from __future__ import annotations

import os
import platform
import shutil
import zipfile
from pathlib import Path

import requests


FFMPEG_ZIP_URL = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)


def _is_windows() -> bool:
    return platform.system().lower().startswith("win")


def ensure_ffmpeg(ffmpeg_dir: Path) -> Path:
    """
    Downloads a static ffmpeg build on first run and returns the path to ffmpeg executable.
    """
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    exe_name = "ffmpeg.exe" if _is_windows() else "ffmpeg"

    # If already present, use it.
    existing = list(ffmpeg_dir.rglob(exe_name))
    if existing:
        return existing[0]

    zip_path = ffmpeg_dir / "ffmpeg.zip"
    tmp_extract = ffmpeg_dir / "_extract"

    with requests.get(FFMPEG_ZIP_URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    if tmp_extract.exists():
        shutil.rmtree(tmp_extract, ignore_errors=True)
    tmp_extract.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp_extract)

    # gyan.dev zip layout typically: ffmpeg-*/bin/ffmpeg.exe
    candidates = list(tmp_extract.rglob(exe_name))
    if not candidates:
        raise RuntimeError("FFmpeg download succeeded but ffmpeg executable was not found in the archive.")

    # Move the whole bin folder contents into ffmpeg_dir/bin
    chosen = candidates[0]
    bin_dir = ffmpeg_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for file in chosen.parent.iterdir():
        if file.is_file():
            shutil.copy2(file, bin_dir / file.name)

    # Cleanup
    try:
        os.remove(zip_path)
    except OSError:
        pass
    shutil.rmtree(tmp_extract, ignore_errors=True)

    final_path = bin_dir / exe_name
    if not final_path.exists():
        raise RuntimeError("FFmpeg install failed: expected executable missing after extraction.")
    return final_path


def configure_moviepy_ffmpeg(ffmpeg_exe: Path) -> None:
    """
    MoviePy uses imageio-ffmpeg internally; setting FFMPEG_BINARY helps it find ffmpeg.
    """
    os.environ["FFMPEG_BINARY"] = str(ffmpeg_exe)

