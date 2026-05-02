"""Phase 1: editor uses real per-clip durations instead of equal-T chunks.

These tests assert that ``assemble_generated_clips_then_concat`` slices the
narration audio at the boundaries we feed in (or that it derives from the
``.mp4.meta.json`` sidecars), so a CogVideoX 6.125 s clip and a Mochi 5.4 s
clip don't both get force-fit to the same chunk.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from src.models.native_fps import write_clip_meta


@pytest.fixture()
def fake_moviepy(monkeypatch):
    """Stub MoviePy and ffmpeg utilities used by the editor."""
    from src.render import editor as ed

    sub_calls: list[tuple[float, float]] = []

    class _FakeAudio:
        def __init__(self, duration: float = 12.0) -> None:
            self.duration = float(duration)

        def volumex(self, *a, **kw):
            return self

        def subclip(self, t0: float, t1: float):
            sub_calls.append((float(t0), float(t1)))
            return self

        def set_fps(self, *a, **kw):
            return self

        def fx(self, *a, **kw):
            return self

        def __add__(self, other):
            return self

        def audio_loop(self, **kw):
            return self

    class _FakeBase:
        def __init__(self, duration: float = 4.0) -> None:
            self.duration = float(duration)

        def subclip(self, t0, t1):
            return self

        def resize(self, *a, **kw):
            return self

        def fl_image(self, *a, **kw):
            return self

        def set_audio(self, *a, **kw):
            return self

        def set_position(self, *a, **kw):
            return self

        def set_duration(self, *a, **kw):
            return self

        def write_videofile(self, *a, **kw):
            return None

    file_clip_durations: dict[str, float] = {}

    class _FakeVideoFileClip(_FakeBase):
        def __init__(self, path):
            self.path = str(path)
            self.duration = float(file_clip_durations.get(self.path, 4.0))

    monkeypatch.setattr(ed, "AudioFileClip", lambda *a, **kw: _FakeAudio(duration=12.0))
    monkeypatch.setattr(ed, "VideoFileClip", _FakeVideoFileClip)
    monkeypatch.setattr(ed, "CompositeVideoClip", lambda *a, **kw: _FakeBase())
    monkeypatch.setattr(
        ed, "concatenate_videoclips", lambda clips, **kw: _FakeBase(duration=sum(c.duration for c in clips))
    )
    monkeypatch.setattr(ed, "ensure_ffmpeg", lambda *a, **kw: "/fake/ffmpeg")
    monkeypatch.setattr(ed, "configure_moviepy_ffmpeg", lambda *a, **kw: None)
    monkeypatch.setattr(ed, "load_captions_json", lambda *a, **kw: [])
    monkeypatch.setattr(
        ed, "_build_overlay_make_frame", lambda **kw: (lambda t: None)
    )
    monkeypatch.setattr(
        ed,
        "_video_clip_from_rgba_overlay_fn",
        lambda fn, duration: _FakeBase(duration=duration),
    )
    monkeypatch.setattr(
        ed, "_make_watermark_clip", lambda **kw: None
    )

    return {"sub_calls": sub_calls, "file_clip_durations": file_clip_durations}


def _make_clip(path: Path, *, frames: int, fps_native: int, model_id: str) -> Path:
    path.write_bytes(b"\x00")
    write_clip_meta(
        path, model_id=model_id, encoded_fps=fps_native, num_frames=frames, user_fps=30
    )
    return path


def test_editor_uses_explicit_clip_durations(fake_moviepy, tmp_path: Path) -> None:
    from src.core.config import VideoSettings
    from src.render.editor import assemble_generated_clips_then_concat

    out_dir = tmp_path / "assets"
    out_dir.mkdir()
    clip_a = _make_clip(out_dir / "clip_001.mp4", frames=49, fps_native=8, model_id="THUDM/CogVideoX-5b")
    clip_b = _make_clip(out_dir / "clip_002.mp4", frames=80, fps_native=16, model_id="Wan-AI/Wan2.2")

    durations = [49 / 8, 80 / 16]
    fake_moviepy["file_clip_durations"][str(clip_a)] = durations[0]
    fake_moviepy["file_clip_durations"][str(clip_b)] = durations[1]

    settings = dataclasses.replace(VideoSettings(), export_microclips=False)

    voice_wav = out_dir / "voice.wav"
    voice_wav.write_bytes(b"\x00")
    captions_json = out_dir / "captions.json"
    captions_json.write_text("[]")
    out_final = out_dir / "final.mp4"

    assemble_generated_clips_then_concat(
        ffmpeg_dir=tmp_path / "ffmpeg",
        settings=settings,
        clips=[clip_a, clip_b],
        voice_wav=voice_wav,
        captions_json=captions_json,
        out_final_mp4=out_final,
        out_assets_dir=out_dir,
        clip_durations=durations,
    )

    sub_calls = fake_moviepy["sub_calls"]
    assert len(sub_calls) >= 2
    t0_a, t1_a = sub_calls[0]
    t0_b, t1_b = sub_calls[1]
    assert t0_a == 0.0
    assert abs((t1_a - t0_a) - durations[0]) < 1e-6
    assert abs(t0_b - durations[0]) < 1e-6
    assert abs((t1_b - t0_b) - durations[1]) < 1e-6


def test_editor_falls_back_to_meta_sidecar_when_durations_missing(
    fake_moviepy, tmp_path: Path
) -> None:
    """Without explicit `clip_durations=`, editor recovers from the .meta.json sidecar."""
    from src.core.config import VideoSettings
    from src.render.editor import assemble_generated_clips_then_concat

    out_dir = tmp_path / "assets"
    out_dir.mkdir()
    clip_a = _make_clip(out_dir / "clip_001.mp4", frames=24, fps_native=24, model_id="Lightricks/LTX-2")
    clip_b = _make_clip(out_dir / "clip_002.mp4", frames=240, fps_native=24, model_id="Lightricks/LTX-2")

    fake_moviepy["file_clip_durations"][str(clip_a)] = 999.0  # ensure meta wins, not VideoFileClip.duration
    fake_moviepy["file_clip_durations"][str(clip_b)] = 999.0

    settings = dataclasses.replace(VideoSettings(), export_microclips=False)

    voice_wav = out_dir / "voice.wav"
    voice_wav.write_bytes(b"\x00")
    captions_json = out_dir / "captions.json"
    captions_json.write_text("[]")
    out_final = out_dir / "final.mp4"

    assemble_generated_clips_then_concat(
        ffmpeg_dir=tmp_path / "ffmpeg",
        settings=settings,
        clips=[clip_a, clip_b],
        voice_wav=voice_wav,
        captions_json=captions_json,
        out_final_mp4=out_final,
        out_assets_dir=out_dir,
    )

    sub_calls = fake_moviepy["sub_calls"]
    assert len(sub_calls) >= 2
    t0_a, t1_a = sub_calls[0]
    t0_b, t1_b = sub_calls[1]
    expected_a = 24 / 24
    expected_b = 240 / 24
    assert abs((t1_a - t0_a) - expected_a) < 1e-6
    assert abs((t1_b - t0_b) - expected_b) < 1e-6
