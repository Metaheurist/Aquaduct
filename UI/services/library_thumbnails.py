"""Thumbnail paths for Library project cards (video JPEG extract or picture final)."""

from __future__ import annotations

from pathlib import Path

THUMBNAIL_NAME = "thumbnail.jpg"


def project_final_media(project_dir: Path, *, photo: bool) -> Path:
    return project_dir / ("final.png" if photo else "final.mp4")


def resolve_library_thumbnail(
    project_dir: Path,
    *,
    photo: bool,
    ffmpeg_dir: Path | None = None,
    ensure: bool = True,
) -> Path | None:
    """
    Return an image path suitable for a Library card thumbnail.

    Pictures use ``final.png``. Videos prefer ``thumbnail.jpg`` beside ``final.mp4``,
    generating it with ffmpeg when missing or older than the video.
    """
    project_dir = project_dir.resolve()
    final = project_final_media(project_dir, photo=photo)
    if not final.is_file():
        return None
    if photo:
        return final

    thumb = project_dir / THUMBNAIL_NAME
    try:
        stale = not thumb.is_file() or thumb.stat().st_mtime < final.stat().st_mtime
    except OSError:
        stale = True
    if thumb.is_file() and not stale:
        return thumb
    if not ensure or ffmpeg_dir is None:
        return thumb if thumb.is_file() else None

    try:
        from src.render.thumbnail import generate_thumbnail

        out = generate_thumbnail(ffmpeg_dir=ffmpeg_dir, video_mp4=final, out_path=thumb)
        return out if out is not None and out.is_file() else (thumb if thumb.is_file() else None)
    except Exception:
        return thumb if thumb.is_file() else None
