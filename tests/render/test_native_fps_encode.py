"""Phase 1: model-native FPS registry + per-clip metadata sidecar.

These tests pin the encoded FPS used by ``_write_mp4_from_frames`` against the
model registry so a regression like the CogVideoX 30 fps stretching never
sneaks back in, and verify the meta sidecar lets the editor recover real
durations without ffprobe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

from src.models.native_fps import (
    clip_duration_seconds,
    clip_meta_path,
    encoded_fps_for,
    native_fps_for,
    read_clip_meta,
    write_clip_meta,
)


def test_native_fps_registry_known_models() -> None:
    assert native_fps_for("THUDM/CogVideoX-5b") == 8
    assert native_fps_for("Wan-AI/Wan2.2-T2V-A14B-Diffusers") == 16
    assert native_fps_for("genmo/mochi-1-preview") == 30
    assert native_fps_for("Lightricks/LTX-2") == 24
    assert native_fps_for("Lightricks/LTX-Video") == 24
    assert native_fps_for("tencent/HunyuanVideo") == 24


def test_native_fps_registry_unknown_returns_none() -> None:
    assert native_fps_for("cerspense/zeroscope_v2_576w") is None
    assert native_fps_for("") is None
    assert native_fps_for(None) is None


def test_encoded_fps_falls_back_to_user_fps_when_unknown() -> None:
    assert encoded_fps_for("cerspense/zeroscope_v2_576w", user_fps=30) == 30


def test_encoded_fps_prefers_explicit_frame_rate_kwarg() -> None:
    assert encoded_fps_for("Lightricks/LTX-2", user_fps=30, frame_rate_kw=24.0) == 24
    assert encoded_fps_for("THUDM/CogVideoX-5b", user_fps=30, frame_rate_kw=12) == 12


def test_encoded_fps_uses_native_when_no_kwarg() -> None:
    assert encoded_fps_for("THUDM/CogVideoX-5b", user_fps=30) == 8
    assert encoded_fps_for("Wan-AI/Wan2.2-T2V-A14B-Diffusers", user_fps=30) == 16


def test_env_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("AQUADUCT_NATIVE_FPS_OVERRIDE_THUDM_COGVIDEOX_5B", "12")
    assert native_fps_for("THUDM/CogVideoX-5b") == 12
    assert encoded_fps_for("THUDM/CogVideoX-5b", user_fps=30) == 12


def test_clip_meta_sidecar_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "pro_clips" / "clip_001.mp4"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"\x00")  # placeholder so Path looks real
    meta_path = write_clip_meta(
        out,
        model_id="THUDM/CogVideoX-5b",
        encoded_fps=8,
        num_frames=49,
        user_fps=30,
        extra={"role": "t2v", "prompt": "foo"},
    )
    assert meta_path == clip_meta_path(out)
    data = read_clip_meta(out)
    assert data is not None
    assert data["model_id"] == "THUDM/CogVideoX-5b"
    assert data["encoded_fps"] == 8
    assert data["num_frames"] == 49
    assert data["user_fps"] == 30
    assert data["native_fps"] == 8
    assert data["role"] == "t2v"
    assert abs(data["duration_s"] - (49 / 8)) < 1e-6


def test_clip_meta_missing_returns_none(tmp_path: Path) -> None:
    out = tmp_path / "no_meta.mp4"
    out.write_bytes(b"\x00")
    assert read_clip_meta(out) is None
    assert clip_duration_seconds(out) is None
    assert clip_duration_seconds(out, fallback=4.0) == 4.0


def _fake_pil_frame(w: int = 32, h: int = 64) -> Any:
    """Minimal PIL-like frame for ``_write_mp4_from_frames`` to consume."""
    from PIL import Image

    return Image.fromarray(np.zeros((h, w, 3), dtype=np.uint8))


def test_t2v_writes_meta_sidecar_at_native_fps(tmp_path: Path, monkeypatch) -> None:
    """Smoke: when the diffusers pipeline returns N frames, the writer is called at native fps
    and the meta sidecar records duration = N / native_fps. We mock heavy load + inference paths."""
    from src.render import clips as clips_mod

    captured_writer_fps: list[int] = []

    class _FakeWriter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def append_data(self, fr):
            return None

    def _fake_get_writer(path, fps, codec, quality, macro_block_size):  # noqa: ARG001
        captured_writer_fps.append(int(fps))
        return _FakeWriter()

    import imageio  # type: ignore

    monkeypatch.setattr(imageio, "get_writer", _fake_get_writer, raising=True)

    monkeypatch.setattr(
        clips_mod, "resolve_pretrained_load_path", lambda mid, **_: tmp_path / "fake_model"
    )
    monkeypatch.setattr(clips_mod, "release_between_stages", lambda *a, **k: None)
    monkeypatch.setattr(clips_mod, "_maybe_enable_slice_inference", lambda *a, **k: None)
    monkeypatch.setattr(clips_mod, "place_diffusion_pipeline", lambda *a, **k: None)

    class _FakeOut:
        def __init__(self, n: int) -> None:
            self.frames = [[_fake_pil_frame() for _ in range(n)]]

    class _FakePipe:
        def __call__(self, *args, **kwargs):
            nf = int(kwargs.get("num_frames", 49) or 49)
            return _FakeOut(nf)

    monkeypatch.setattr(
        clips_mod, "_load_text_to_video_pipeline", lambda *a, **k: _FakePipe()
    )

    out_dir = tmp_path / "pro_clips"
    out_dir.mkdir()

    with patch.object(clips_mod, "diffusers_from_pretrained", side_effect=AssertionError("not used")):
        results = clips_mod._try_text_to_video(
            "THUDM/CogVideoX-5b",
            ["a haunted forest"],
            out_dir,
            fps=30,
            seconds=2.0,
            cuda_device_index=None,
            inference_settings=None,
        )

    assert len(results) == 1
    out_path = results[0].path
    assert captured_writer_fps == [8], "CogVideoX must encode at its native 8 fps, not user fps"

    meta = read_clip_meta(out_path)
    assert meta is not None
    assert meta["encoded_fps"] == 8
    assert meta["user_fps"] == 30
    assert meta["num_frames"] >= 9
    assert meta["duration_s"] == round(meta["num_frames"] / 8, 6)


def test_meta_sidecar_lives_next_to_clip(tmp_path: Path) -> None:
    p = tmp_path / "deep" / "clip_005.mp4"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"")
    meta = clip_meta_path(p)
    assert meta.parent == p.parent
    assert meta.name == "clip_005.mp4.meta.json"


def test_clip_meta_sidecar_has_pretty_json(tmp_path: Path) -> None:
    p = tmp_path / "c.mp4"
    p.write_bytes(b"")
    write_clip_meta(p, model_id="THUDM/CogVideoX-5b", encoded_fps=8, num_frames=49)
    raw = clip_meta_path(p).read_text(encoding="utf-8")
    assert "\n" in raw  # indent=2 produces multi-line JSON
    parsed = json.loads(raw)
    assert parsed["encoded_fps"] == 8
