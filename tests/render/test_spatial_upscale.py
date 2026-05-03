"""Unit tests for ``src/render/spatial_upscale`` helpers (no GPU)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.render import spatial_upscale as su


def test_needs_spatial_upscale() -> None:
    assert su.needs_spatial_upscale(640, 360, 1080, 1920)
    assert not su.needs_spatial_upscale(1080, 1920, 1080, 1920)
    assert not su.needs_spatial_upscale(1200, 2000, 1080, 1920)
    assert su.needs_spatial_upscale(0, 100, 1080, 1920) is False


def test_pytorch_realesrgan_available_smoke() -> None:
    # May be True or False in dev env; call must not raise.
    assert isinstance(su.pytorch_realesrgan_available(), bool)


def test_ncnn_spatial_available_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQUADUCT_DISABLE_REALESRGAN_NCNN", raising=False)
    assert isinstance(su.ncnn_spatial_available(), bool)


def test_spatial_vram_budget_ok() -> None:
    assert su.spatial_vram_budget_ok(free_vram_mb=None) is False
    assert su.spatial_vram_budget_ok(free_vram_mb=100) is False
    assert su.spatial_vram_budget_ok(free_vram_mb=su.SPATIAL_VRAM_BUDGET_MB) is True


def test_upscale_clip_file_off_returns_original(tmp_path: Path) -> None:
    p = tmp_path / "a.mp4"
    p.write_bytes(b"not a real mp4")
    r = su.upscale_clip_file(
        p,
        target_w=1080,
        target_h=1920,
        mode="off",
        ffmpeg_dir=tmp_path,
    )
    assert r.output_path == p
    assert r.mode_used == "off"


def test_fit_crop_box() -> None:
    l, t, r, b = su._fit_crop_box(2000, 1000, 1080, 1920)
    assert r - l <= 2000
    assert b - t <= 1000


def test_upscale_clips_inplace_reports_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[int, int]] = []

    def fake_upscale(
        src: Path,
        *,
        target_w: int,
        target_h: int,
        mode: str,
        ffmpeg_dir: Path,
        cuda_device_index: int | None = None,
        free_vram_mb: int | None = None,
    ) -> su.SpatialUpscaleResult:
        return su.SpatialUpscaleResult(output_path=src, mode_used="off")

    monkeypatch.setattr(su, "upscale_clip_file", fake_upscale)
    p1, p2 = tmp_path / "a.mp4", tmp_path / "b.mp4"
    p1.write_bytes(b"x")
    p2.write_bytes(b"y")
    su.upscale_clips_inplace(
        [p1, p2],
        target_w=1080,
        target_h=1920,
        mode="auto",
        ffmpeg_dir=tmp_path,
        on_clip_progress=lambda c, t: calls.append((c, t)),
    )
    assert calls == [(1, 2), (2, 2)]
