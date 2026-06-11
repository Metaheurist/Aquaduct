"""Auto thumbnail extraction beside ``final.mp4``."""

from __future__ import annotations

import subprocess
from pathlib import Path


def generate_thumbnail(
    *,
    ffmpeg_dir: Path,
    video_mp4: Path,
    out_path: Path | None = None,
    seek_s: float = 1.0,
) -> Path | None:
    """
    Extract a single JPEG frame from ``video_mp4`` and write ``thumbnail.jpg``
    beside the video (or to ``out_path``). Returns the output path on success.
    """
    video_mp4 = video_mp4.resolve()
    if not video_mp4.is_file():
        return None
    out = (out_path or (video_mp4.parent / "thumbnail.jpg")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from src.render.utils_ffmpeg import ensure_ffmpeg

        ffmpeg_bin = Path(ensure_ffmpeg(ffmpeg_dir))
    except Exception:
        return None
    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-ss",
        str(max(0.0, float(seek_s))),
        "-i",
        str(video_mp4),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, OSError):
        return None
    if out.is_file() and out.stat().st_size > 256:
        return out
    return None
