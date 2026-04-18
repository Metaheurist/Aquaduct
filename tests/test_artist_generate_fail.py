"""Diffusion failures must not silently produce text-only placeholder slides."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_generate_images_raises_when_diffusion_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import src.artist as artist

    monkeypatch.setattr(
        artist,
        "_try_sdxl_turbo_seeded",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("simulated diffusion failure")),
    )
    monkeypatch.delenv("AQUADUCT_ALLOW_PLACEHOLDER_IMAGES", raising=False)

    with pytest.raises(RuntimeError, match="Diffusion image generation failed"):
        artist.generate_images(
            sdxl_turbo_model_id="dummy/model",
            prompts=["a cat"],
            out_dir=tmp_path,
            max_images=1,
            seeds=[42],
        )


def test_generate_images_placeholder_when_env_allows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import src.artist as artist

    monkeypatch.setenv("AQUADUCT_ALLOW_PLACEHOLDER_IMAGES", "1")
    monkeypatch.setattr(
        artist,
        "_try_sdxl_turbo_seeded",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("simulated diffusion failure")),
    )
    r = artist.generate_images(
        sdxl_turbo_model_id="dummy/model",
        prompts=["a cat"],
        out_dir=tmp_path,
        max_images=1,
        seeds=[42],
    )
    assert len(r) == 1
    assert r[0].path.exists()
