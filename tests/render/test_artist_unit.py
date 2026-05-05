"""Unit tests for src.render.artist — hyperparameters, failure modes, regen paths (no full GPU run)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.render.artist import (
    GeneratedImage,
    _diffusion_kw_for_model,
    apply_regenerated_image,
    generate_images,
    t2i_user_step_choices,
)


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


def test_generate_images_raises_when_diffusion_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import src.render.artist as artist_module

    monkeypatch.setattr(
        artist_module,
        "_try_sdxl_turbo_seeded",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("simulated diffusion failure")),
    )
    monkeypatch.delenv("AQUADUCT_ALLOW_PLACEHOLDER_IMAGES", raising=False)

    with pytest.raises(RuntimeError, match="Diffusion image generation failed"):
        generate_images(
            sdxl_turbo_model_id="dummy/model",
            prompts=["a cat"],
            out_dir=tmp_path,
            max_images=1,
            seeds=[42],
        )


def test_generate_images_placeholder_when_env_allows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import src.render.artist as artist_module

    monkeypatch.setenv("AQUADUCT_ALLOW_PLACEHOLDER_IMAGES", "1")
    monkeypatch.setattr(
        artist_module,
        "_try_sdxl_turbo_seeded",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("simulated diffusion failure")),
    )
    r = generate_images(
        sdxl_turbo_model_id="dummy/model",
        prompts=["a cat"],
        out_dir=tmp_path,
        max_images=1,
        seeds=[42],
    )
    assert len(r) == 1
    assert r[0].path.exists()


def test_apply_regenerated_image_same_path_keeps_file(tmp_path: Path) -> None:
    p = tmp_path / "img_001.png"
    p.write_bytes(b"ok")
    regen = [GeneratedImage(path=p, prompt="a")]
    apply_regenerated_image(regen, p)
    assert p.exists()
    assert p.read_bytes() == b"ok"


def test_apply_regenerated_image_copies_when_paths_differ(tmp_path: Path) -> None:
    src = tmp_path / "img_001.png"
    dst = tmp_path / "scene_01.png"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    regen = [GeneratedImage(path=src, prompt="a")]
    apply_regenerated_image(regen, dst)
    assert dst.read_bytes() == b"new"
    assert not src.exists()
