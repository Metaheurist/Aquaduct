"""Phase 5 tests for the four-knob video quality preset registry."""
from __future__ import annotations

import pytest

from src.render import video_quality_presets as vqp


def test_length_preset_lookup_known_id() -> None:
    assert vqp.length_preset("short").clips_per_video == 3
    assert vqp.length_preset("medium").length_factor == pytest.approx(1.0)
    assert vqp.length_preset("long").pro_clip_seconds == pytest.approx(6.0)


def test_length_preset_falls_back_to_default() -> None:
    assert vqp.length_preset("garbage").id == vqp.DEFAULT_LENGTH


def test_scene_preset_target_seconds_in_order() -> None:
    assert (
        vqp.scene_preset("punchy").target_clip_seconds
        < vqp.scene_preset("balanced").target_clip_seconds
        < vqp.scene_preset("cinematic").target_clip_seconds
    )


def test_fps_preset_returns_smoothness_target_match_fps() -> None:
    for pid in ("cinematic_24", "standard_30", "smooth_60"):
        fp = vqp.fps_preset(pid)
        assert fp.smoothness_target_fps == fp.fps


def test_resolution_preset_widths() -> None:
    assert vqp.resolution_preset("vertical_1080p").width == 1080
    assert vqp.resolution_preset("vertical_720p").width == 720
    assert vqp.resolution_preset("square_1080").width == vqp.resolution_preset("square_1080").height


def test_apply_t2v_length_factor_scales_num_frames() -> None:
    out = vqp.apply_t2v_length_factor({"num_frames": 49}, 1.25)
    assert out["num_frames"] == 61


def test_apply_t2v_length_factor_floor_8_frames() -> None:
    out = vqp.apply_t2v_length_factor({"num_frames": 4}, 0.5)
    assert out["num_frames"] == 8


def test_apply_t2v_length_factor_noop_when_no_frames_key() -> None:
    out = vqp.apply_t2v_length_factor({}, 1.5)
    assert out == {}


def test_apply_t2v_length_factor_returns_new_dict() -> None:
    src = {"num_frames": 49}
    out = vqp.apply_t2v_length_factor(src, 1.5)
    assert out is not src
    assert src["num_frames"] == 49


def test_migrate_legacy_short_total() -> None:
    out = vqp.migrate_legacy_video_settings({"clips_per_video": 3, "pro_clip_seconds": 5.0, "fps": 30})
    assert out["video_length_preset_id"] == "short"
    assert out["video_scene_preset_id"] == "balanced"
    assert out["video_fps_preset_id"] == "standard_30"


def test_migrate_legacy_long_total() -> None:
    out = vqp.migrate_legacy_video_settings({"clips_per_video": 8, "pro_clip_seconds": 7.0})
    assert out["video_length_preset_id"] == "long"
    assert out["video_scene_preset_id"] == "cinematic"


def test_migrate_legacy_punchy_when_clip_seconds_low() -> None:
    out = vqp.migrate_legacy_video_settings({"clips_per_video": 4, "pro_clip_seconds": 3.0})
    assert out["video_scene_preset_id"] == "punchy"


def test_migrate_legacy_resolution_branches() -> None:
    assert (
        vqp.migrate_legacy_video_settings({"width": 1080, "height": 1080})["video_resolution_preset_id"]
        == "square_1080"
    )
    assert (
        vqp.migrate_legacy_video_settings({"width": 720, "height": 1280})["video_resolution_preset_id"]
        == "vertical_720p"
    )
    assert (
        vqp.migrate_legacy_video_settings({"width": 1080, "height": 1920})["video_resolution_preset_id"]
        == "vertical_1080p"
    )


def test_migrate_legacy_fps_branches() -> None:
    assert vqp.migrate_legacy_video_settings({"fps": 24})["video_fps_preset_id"] == "cinematic_24"
    assert vqp.migrate_legacy_video_settings({"fps": 30})["video_fps_preset_id"] == "standard_30"
    assert vqp.migrate_legacy_video_settings({"fps": 60})["video_fps_preset_id"] == "smooth_60"


def test_migrate_is_idempotent_when_ids_already_set() -> None:
    src = {
        "video_length_preset_id": "long",
        "video_scene_preset_id": "punchy",
        "video_fps_preset_id": "smooth_60",
        "video_resolution_preset_id": "square_1080",
        "fps": 30,
        "clips_per_video": 5,
        "pro_clip_seconds": 5.0,
    }
    out = vqp.migrate_legacy_video_settings(src)
    assert out["video_length_preset_id"] == "long"
    assert out["video_scene_preset_id"] == "punchy"
    assert out["video_fps_preset_id"] == "smooth_60"
    assert out["video_resolution_preset_id"] == "square_1080"


def test_apply_video_presets_overrides_raw_values() -> None:
    out = vqp.apply_video_presets(
        {
            "video_length_preset_id": "long",
            "video_fps_preset_id": "smooth_60",
            "video_resolution_preset_id": "vertical_720p",
            "fps": 30,
            "width": 1080,
            "height": 1920,
            "clips_per_video": 3,
            "pro_clip_seconds": 4.0,
        }
    )
    assert out["clips_per_video"] == 8
    assert out["pro_clip_seconds"] == 6.0
    assert out["fps"] == 60
    assert out["smoothness_target_fps"] == 60
    assert out["width"] == 720
    assert out["height"] == 1280


def test_apply_video_presets_blank_id_keeps_raw() -> None:
    out = vqp.apply_video_presets({"video_fps_preset_id": "", "fps": 42})
    assert out["fps"] == 42


def test_length_factor_for_helper_reads_video_settings() -> None:
    class _V:
        video_length_preset_id = "long"

    assert vqp.length_factor_for(_V()) == pytest.approx(1.25)


def test_length_factor_for_unknown_id_returns_one() -> None:
    class _V:
        video_length_preset_id = "garbage"

    assert vqp.length_factor_for(_V()) == pytest.approx(1.0)
