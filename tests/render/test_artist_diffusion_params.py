"""Unit tests for model-specific diffusion hyperparameters (no GPU)."""

from __future__ import annotations

from src.render.artist import _diffusion_kw_for_model


def test_sdxl_turbo_uses_cfg_zero_and_low_steps():
    kw = _diffusion_kw_for_model("stabilityai/sdxl-turbo", steps=4)
    assert kw["guidance_scale"] == 0.0
    assert kw["num_inference_steps"] == 4
    assert kw["width"] == kw["height"] == 1024


def test_sd15_uses_cfg_and_more_steps_and_512():
    kw = _diffusion_kw_for_model("runwayml/stable-diffusion-v1-5", steps=4)
    assert kw["guidance_scale"] == 7.5
    assert kw["num_inference_steps"] >= 25
    assert kw["width"] == kw["height"] == 512


def test_sdxl_base_uses_cfg_and_1024():
    kw = _diffusion_kw_for_model("stabilityai/stable-diffusion-xl-base-1.0", steps=4)
    assert kw["guidance_scale"] == 7.0
    assert kw["num_inference_steps"] >= 20
    assert kw["width"] == kw["height"] == 1024
