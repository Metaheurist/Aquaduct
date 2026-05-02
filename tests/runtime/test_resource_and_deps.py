from __future__ import annotations

from pathlib import Path

from src.core.config import AppSettings
from src.runtime import oom_retry
from src.runtime.resource_ladder import apply_inference_profile_scales, downgrade_frames_step, downgrade_resolution_step
from src.runtime import run_checkpoint as rc


def test_downgrade_resolution_scales_settings() -> None:
    s = AppSettings()
    s2 = downgrade_resolution_step(s, role="video")
    assert s2 is not None
    assert s2.resource_retry_resolution_scale < 1.0


def test_downgrade_frames_steps_adjusts_scale() -> None:
    s = AppSettings()
    s2 = downgrade_frames_step(s, role="video")
    assert s2 is not None
    assert s2.resource_retry_frames_scale < 1.0


def test_apply_inference_profile_scales_shrinks() -> None:
    s = AppSettings(resource_retry_resolution_scale=0.75, resource_retry_frames_scale=0.5)
    m = apply_inference_profile_scales({"width": 800, "height": 448, "num_frames": 25}, s)
    assert int(m["width"]) <= 800
    assert int(m["num_frames"]) <= 25


def test_dependency_setup_error_detects_tiktoken_message() -> None:
    e = ValueError("`tiktoken` is required to read a `tiktoken` file. Install it with `pip install tiktoken`.")
    assert oom_retry.is_dependency_setup_error(e) is True


def test_run_checkpoint_roundtrip(tmp_path: Path) -> None:
    app = AppSettings(llm_model_id="a/b", image_model_id="c/d", video_model_id="e/f", voice_model_id="g/h")
    rc.mark_stage_complete(tmp_path, app, "script_pkg")
    done = rc.stages_done(tmp_path, app)
    assert "script_pkg" in done
