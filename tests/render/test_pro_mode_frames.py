from __future__ import annotations

from src.render.editor import pro_mode_frame_count


def test_pro_mode_frame_count_rounds_seconds_times_fps() -> None:
    assert pro_mode_frame_count(pro_clip_seconds=2.0, fps=60) == 120
    assert pro_mode_frame_count(pro_clip_seconds=4.0, fps=30) == 120


def test_pro_mode_frame_count_respects_env_cap(monkeypatch) -> None:
    monkeypatch.setenv("AQUADUCT_PRO_MAX_FRAMES", "50")
    assert pro_mode_frame_count(pro_clip_seconds=10.0, fps=60) == 50
    monkeypatch.delenv("AQUADUCT_PRO_MAX_FRAMES", raising=False)
