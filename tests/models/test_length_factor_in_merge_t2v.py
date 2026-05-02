"""Phase 5/7 tests for ``apply_t2v_length_factor`` integration in ``merge_t2v_from_settings``.

These tests verify that the new four-knob preset system actually scales the
T2V ``num_frames`` parameter handed to the diffusers pipelines, after the
VRAM-band profile has been applied. The integration covers:

  * ``short`` length preset → factor 0.85 → fewer frames than the band default,
  * ``medium`` length preset → factor 1.0 → identical to the band default,
  * ``long`` length preset → factor 1.25 → more frames than the band default,
  * 8-frame floor is enforced when an aggressive factor would otherwise zero
    out a clip's motion budget.

We bypass the GPU-detection path with a monkey-patched
``resolve_effective_vram_gb`` so the tests run on any host.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from src.core.config import AppSettings, VideoSettings
from src.models import inference_profiles as ip
from src.render import video_quality_presets as vqp


@pytest.fixture(autouse=True)
def _stub_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ip,
        "resolve_effective_vram_gb",
        lambda *, kind, settings: 16.0,
    )

    def _no_scale(out: dict[str, Any], settings: AppSettings) -> dict[str, Any]:
        return out

    monkeypatch.setattr(
        "src.runtime.resource_ladder.apply_inference_profile_scales",
        _no_scale,
        raising=False,
    )


def _settings(length_id: str) -> AppSettings:
    video = dataclasses.replace(VideoSettings(), video_length_preset_id=length_id)
    return dataclasses.replace(AppSettings(), video=video)


def test_medium_preset_keeps_band_default_num_frames() -> None:
    """``medium`` (factor 1.0) does not modify the band-resolved frame count."""
    medium_out = ip.merge_t2v_from_settings("THUDM/CogVideoX-5b", {}, _settings("medium"))
    band_default = medium_out["num_frames"]
    assert band_default >= 8
    out2 = ip.merge_t2v_from_settings("THUDM/CogVideoX-5b", {"num_frames": 999}, _settings("medium"))
    assert out2["num_frames"] == band_default


def test_short_preset_scales_num_frames_down() -> None:
    base_out = ip.merge_t2v_from_settings("THUDM/CogVideoX-5b", {}, _settings("medium"))
    short_out = ip.merge_t2v_from_settings("THUDM/CogVideoX-5b", {}, _settings("short"))
    assert short_out["num_frames"] < base_out["num_frames"]
    assert short_out["num_frames"] >= 8


def test_long_preset_scales_num_frames_up() -> None:
    base_out = ip.merge_t2v_from_settings("THUDM/CogVideoX-5b", {}, _settings("medium"))
    long_out = ip.merge_t2v_from_settings("THUDM/CogVideoX-5b", {}, _settings("long"))
    assert long_out["num_frames"] > base_out["num_frames"]


def test_length_factor_floors_at_eight() -> None:
    out = vqp.apply_t2v_length_factor({"num_frames": 1}, factor=0.05)
    assert out["num_frames"] >= 8


def test_length_factor_unknown_id_defaults_to_one() -> None:
    factor = vqp.length_factor_for(VideoSettings())
    assert abs(factor - 1.0) < 1e-6


def test_length_factor_for_invalid_id_safely_returns_one() -> None:
    video = dataclasses.replace(VideoSettings(), video_length_preset_id="not_a_real_preset")
    assert abs(vqp.length_factor_for(video) - 1.0) < 1e-6


def test_apply_factor_returns_new_dict() -> None:
    src = {"num_frames": 32, "extra": "kept"}
    out = vqp.apply_t2v_length_factor(src, factor=1.25)
    assert out is not src
    assert out["extra"] == "kept"
    assert src["num_frames"] == 32  # input unmutated


def test_apply_factor_handles_missing_num_frames() -> None:
    out = vqp.apply_t2v_length_factor({"width": 720}, factor=1.5)
    assert "num_frames" not in out
    assert out["width"] == 720
