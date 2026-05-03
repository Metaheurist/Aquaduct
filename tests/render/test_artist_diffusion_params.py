"""Unit tests for model-specific diffusion hyperparameters (no GPU)."""

from __future__ import annotations

from src.render.artist import _diffusion_kw_for_model, t2i_user_step_choices


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


def test_t2i_user_step_choices_sd35_medium_matches_preset_range():
    opts = t2i_user_step_choices("stabilityai/stable-diffusion-3.5-medium")
    assert opts == [20, 24, 28, 32, 36, 40, 45, 50]
    for n in opts:
        kw = _diffusion_kw_for_model("stabilityai/stable-diffusion-3.5-medium", steps=n)
        assert kw["num_inference_steps"] == n


def test_t2i_user_step_choices_turbo_family_small_values():
    opts = t2i_user_step_choices("stabilityai/sdxl-turbo")
    assert opts == [1, 2, 3, 4]
    for n in opts:
        kw = _diffusion_kw_for_model("stabilityai/sdxl-turbo", steps=n)
        assert kw["num_inference_steps"] == n


def test_t2i_user_step_choices_sd15_minimum_respected():
    opts = t2i_user_step_choices("runwayml/stable-diffusion-v1-5")
    assert min(opts) >= 25
    for n in opts:
        kw = _diffusion_kw_for_model("runwayml/stable-diffusion-v1-5", steps=n)
        assert kw["num_inference_steps"] == n
