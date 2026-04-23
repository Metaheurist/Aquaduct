from __future__ import annotations

from src.render.ffmpeg_slideshow import sanitize_xfade_transition


def test_sanitize_xfade_transition_known() -> None:
    assert sanitize_xfade_transition("fade") == "fade"
    assert sanitize_xfade_transition("wipeleft") == "wipeleft"


def test_sanitize_xfade_transition_unknown_defaults() -> None:
    assert sanitize_xfade_transition("not_a_real_transition") == "fade"
    assert sanitize_xfade_transition("") == "fade"
