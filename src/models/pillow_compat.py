"""
Pillow 10+ removed ``Image.ANTIALIAS`` (and related aliases on ``Image``).
MoviePy 1.x still references ``Image.ANTIALIAS`` in ``video.fx.resize`` ÔÇö patch aliases once at import time.
"""

from __future__ import annotations


def apply_pillow_moviepy_compat() -> None:
    from PIL import Image

    if hasattr(Image, "ANTIALIAS"):
        return
    try:
        from PIL.Image import Resampling

        lanczos = Resampling.LANCZOS
    except Exception:
        lanczos = getattr(Image, "LANCZOS", 1)

    Image.ANTIALIAS = lanczos
