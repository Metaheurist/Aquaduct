"""Helpers for img2vid pipeline kwargs (Stable Video Diffusion vs text-conditioned)."""

from __future__ import annotations

import pytest

from src.models.hardware import HardwareInfo
from src.render.clips import (
    _img2vid_accepts_text_prompt,
    _strip_negative_and_cap_for_clip,
    _svd_cap_num_frames,
    _video_pipe_kwargs,
)


def test_svd_img2vid_does_not_use_prompt_kwarg() -> None:
    assert _img2vid_accepts_text_prompt("stabilityai/stable-video-diffusion-img2vid-xt") is False
    assert _img2vid_accepts_text_prompt("SomeOrg/some-img2vid-custom") is False


def test_zeroscope_may_use_prompt() -> None:
    assert _img2vid_accepts_text_prompt("cerspense/zeroscope_v2_576w") is True


def test_svd_num_frames_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=16.0),
    )
    assert _svd_cap_num_frames(200) == 25


def test_svd_num_frames_tighter_on_8gb_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=8.0),
    )
    assert _svd_cap_num_frames(200) == 14


def test_svd_num_frames_moderate_on_12gb_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=12.0),
    )
    assert _svd_cap_num_frames(200) == 18


def test_video_pipe_kwargs_svd_does_not_use_fps_times_seconds_raw() -> None:
    kw = _video_pipe_kwargs("stabilityai/stable-video-diffusion-img2vid-xt", num_frames=120)
    assert kw["num_frames"] <= 25


def test_svd_decode_chunk_smaller_on_12gb_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.models.hardware.get_hardware_info",
        lambda: HardwareInfo(os="t", cpu="c", ram_gb=32.0, gpu_name="g", vram_gb=12.0),
    )
    kw = _video_pipe_kwargs("stabilityai/stable-video-diffusion-img2vid-xt", num_frames=16)
    assert kw["decode_chunk_size"] == 2


def test_strip_negative_caps_openai_clip_token_count() -> None:
    """CLIP text encoders in many pipelines are hard-limited to 77 tokens; words ≠ tokens."""
    from transformers import CLIPTokenizerFast

    tok = CLIPTokenizerFast.from_pretrained("openai/clip-vit-large-patch14")
    long = "hello, " * 100
    out = _strip_negative_and_cap_for_clip("cerspense/zeroscope_v2_576w", long)
    assert len(tok.encode(out)) <= 77
