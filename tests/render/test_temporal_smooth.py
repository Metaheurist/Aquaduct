"""Phase 2 tests for ``src/render/temporal_smooth.py``.

Pure-Python tests that do not actually run ffmpeg or RIFE; we monkey-patch
the subprocess call so the module logic itself is exercised in isolation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models import native_fps as native_fps_mod
from src.render import temporal_smooth as ts


def _write_dummy_clip(tmp_path: Path, *, num_frames: int = 24, encoded_fps: int = 8) -> Path:
    clip = tmp_path / "clip_000.mp4"
    clip.write_bytes(b"\x00" * 64)
    native_fps_mod.write_clip_meta(
        clip,
        model_id="THUDM/CogVideoX-5b",
        encoded_fps=encoded_fps,
        num_frames=num_frames,
    )
    return clip


def test_resolve_mode_off_passthrough() -> None:
    assert ts._resolve_mode("off", free_vram_mb=99999) == "off"


def test_resolve_mode_invalid_returns_off() -> None:
    assert ts._resolve_mode("garbage", free_vram_mb=99999) == "off"  # type: ignore[arg-type]


def test_resolve_mode_ffmpeg_always_ffmpeg() -> None:
    assert ts._resolve_mode("ffmpeg", free_vram_mb=0) == "ffmpeg"
    assert ts._resolve_mode("ffmpeg", free_vram_mb=None) == "ffmpeg"


def test_resolve_mode_rife_falls_back_when_package_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "rife_available", lambda: False)
    assert ts._resolve_mode("rife", free_vram_mb=8000) == "ffmpeg"


def test_resolve_mode_rife_falls_back_when_vram_short(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "rife_available", lambda: True)
    assert ts._resolve_mode("rife", free_vram_mb=100) == "ffmpeg"


def test_resolve_mode_rife_active_when_resources_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts, "rife_available", lambda: True)
    assert ts._resolve_mode("rife", free_vram_mb=ts.RIFE_VRAM_BUDGET_MB + 100) == "rife"


def test_rife_vram_budget_ok_handles_none() -> None:
    assert ts.rife_vram_budget_ok(free_vram_mb=None) is False


def test_resolve_target_fps_clamps() -> None:
    assert ts._resolve_target_fps(0) == 24
    assert ts._resolve_target_fps(8) == 12
    assert ts._resolve_target_fps(99) == 60
    assert ts._resolve_target_fps(30) == 30


def test_smooth_clip_off_is_noop(tmp_path: Path) -> None:
    src = _write_dummy_clip(tmp_path)
    before = src.read_bytes()
    res = ts.smooth_clip(src, mode="off", model_id="THUDM/CogVideoX-5b", target_fps=24)
    assert res.output_path == src
    assert res.mode_used == "off"
    assert src.read_bytes() == before


def test_smooth_clip_target_below_encoded_is_noop(tmp_path: Path) -> None:
    src = _write_dummy_clip(tmp_path, encoded_fps=30)
    res = ts.smooth_clip(
        src, mode="ffmpeg", model_id="THUDM/CogVideoX-5b", target_fps=24
    )
    assert res.mode_used == "off"


def test_smooth_clip_invokes_ffmpeg_and_writes_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _write_dummy_clip(tmp_path, num_frames=24, encoded_fps=8)

    invoked: dict[str, object] = {}

    def fake_minterpolate(s: Path, d: Path, *, target_fps: int, ffmpeg_exe: object) -> bool:
        invoked["src"] = s
        invoked["dst"] = d
        invoked["target_fps"] = target_fps
        d.write_bytes(b"\x01" * 32)
        return True

    monkeypatch.setattr(ts, "_ffmpeg_minterpolate", fake_minterpolate)

    res = ts.smooth_clip(src, mode="ffmpeg", model_id="THUDM/CogVideoX-5b", target_fps=24)

    assert res.mode_used == "ffmpeg"
    assert res.encoded_fps == 24
    assert res.target_fps == 24
    assert res.output_path == src
    assert invoked["target_fps"] == 24
    meta = native_fps_mod.read_clip_meta(src)
    assert meta is not None
    assert meta["encoded_fps"] == 24
    duration_after = ts.clip_duration_seconds(src)
    assert duration_after is not None
    assert abs(duration_after - 3.0) < 0.05


def test_smooth_clip_failure_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _write_dummy_clip(tmp_path, num_frames=24, encoded_fps=8)
    original_bytes = src.read_bytes()

    monkeypatch.setattr(
        ts, "_ffmpeg_minterpolate", lambda *a, **k: False
    )

    res = ts.smooth_clip(src, mode="ffmpeg", model_id="THUDM/CogVideoX-5b", target_fps=24)

    assert res.mode_used == "off"
    assert res.output_path == src
    assert src.read_bytes() == original_bytes
    meta_after = native_fps_mod.read_clip_meta(src)
    assert meta_after is not None
    assert meta_after["encoded_fps"] == 8


def test_smooth_clips_continues_on_per_clip_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a").mkdir(parents=True, exist_ok=True)
    (tmp_path / "b").mkdir(parents=True, exist_ok=True)
    a = _write_dummy_clip(tmp_path / "a", num_frames=24, encoded_fps=8)
    b = _write_dummy_clip(tmp_path / "b", num_frames=24, encoded_fps=8)

    calls: list[str] = []

    def fake_minterpolate(s: Path, d: Path, *, target_fps: int, ffmpeg_exe: object) -> bool:
        calls.append(str(s))
        if s.parent.name == "a":
            raise RuntimeError("boom")
        d.write_bytes(b"\x01")
        return True

    monkeypatch.setattr(ts, "_ffmpeg_minterpolate", fake_minterpolate)

    results = ts.smooth_clips(
        [a, b],
        mode="ffmpeg",
        model_id="THUDM/CogVideoX-5b",
        target_fps=24,
    )
    assert len(results) == 2
    assert results[0].mode_used == "off"
    assert results[1].mode_used == "ffmpeg"


def test_resolve_encoded_fps_falls_back_to_native_registry(tmp_path: Path) -> None:
    src = tmp_path / "no_meta.mp4"
    src.write_bytes(b"x")
    fps = ts._resolve_encoded_fps(src, model_id="THUDM/CogVideoX-5b")
    assert fps == native_fps_mod.native_fps_for("THUDM/CogVideoX-5b")


def test_resolve_encoded_fps_default_when_unknown_model(tmp_path: Path) -> None:
    src = tmp_path / "no_meta.mp4"
    src.write_bytes(b"x")
    assert ts._resolve_encoded_fps(src, model_id="some/never-seen") == 24


def test_meta_sidecar_round_trip_after_smooth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _write_dummy_clip(tmp_path, num_frames=16, encoded_fps=8)

    def fake_minterpolate(s: Path, d: Path, *, target_fps: int, ffmpeg_exe: object) -> bool:
        d.write_bytes(b"\x02" * 16)
        return True

    monkeypatch.setattr(ts, "_ffmpeg_minterpolate", fake_minterpolate)

    ts.smooth_clip(src, mode="ffmpeg", model_id="THUDM/CogVideoX-5b", target_fps=24)
    payload = json.loads(native_fps_mod.clip_meta_path(src).read_text(encoding="utf-8"))
    assert payload["encoded_fps"] == 24
    assert payload["num_frames"] == 48
    assert abs(payload["duration_s"] - 2.0) < 1e-3
