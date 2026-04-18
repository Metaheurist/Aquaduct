from __future__ import annotations

from src.video_platform_presets import (
    PLATFORM_PRESETS,
    find_best_preset_for_video,
    preset_by_id,
)


def test_every_preset_has_unique_id() -> None:
    ids = [p.id for p in PLATFORM_PRESETS]
    assert len(ids) == len(set(ids))


def test_preset_by_id_roundtrip() -> None:
    for p in PLATFORM_PRESETS:
        assert preset_by_id(p.id) == p
    assert preset_by_id("") is None
    assert preset_by_id("nope") is None


def test_find_best_preset_matches_template() -> None:
    p = PLATFORM_PRESETS[0]
    got = find_best_preset_for_video(
        width=p.width,
        height=p.height,
        fps=p.fps,
        microclip_min_s=p.microclip_min_s,
        microclip_max_s=p.microclip_max_s,
        images_per_video=p.images_per_video,
        bitrate_preset=p.bitrate_preset,
        clips_per_video=p.clips_per_video,
        clip_seconds=p.clip_seconds,
    )
    assert got == p.id


def test_find_best_preset_returns_empty_when_mismatch() -> None:
    p = PLATFORM_PRESETS[0]
    assert (
        find_best_preset_for_video(
            width=p.width,
            height=p.height,
            fps=p.fps,
            microclip_min_s=p.microclip_min_s + 2.0,
            microclip_max_s=p.microclip_max_s,
            images_per_video=p.images_per_video,
            bitrate_preset=p.bitrate_preset,
            clips_per_video=p.clips_per_video,
            clip_seconds=p.clip_seconds,
        )
        == ""
    )
