"""Regression: Path.replace was misused for quality regen (same path → file loss on Windows)."""

from __future__ import annotations

from pathlib import Path

from src.artist import GeneratedImage, apply_regenerated_image


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
