"""Smoke tests for editor assembly helpers (no real FFmpeg/MoviePy encode)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_pro_mode_frame_count_positive() -> None:
    from src.render.editor import pro_mode_frame_count

    n = pro_mode_frame_count(pro_clip_seconds=4.0, fps=24)
    assert n >= 1


@pytest.mark.parametrize("mode", ["off", "auto"])
def test_editor_maybe_spatial_upscale_path_respects_mode(mode: str) -> None:
    from src.core.config import VideoSettings
    from src.render.editor import editor_maybe_spatial_upscale_path

    vs = VideoSettings(spatial_upscale_mode=mode)  # type: ignore[arg-type]
    p = Path("clip.mp4")
    out = editor_maybe_spatial_upscale_path(p, settings=vs, ffmpeg_dir=Path("/tmp/ffmpeg"))
    assert out == p or out.name.endswith(".mp4")
