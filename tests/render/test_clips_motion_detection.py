from __future__ import annotations

from src.render.clips import is_image_to_video_motion_model


def test_stable_video_diffusion_is_image_to_video() -> None:
    assert is_image_to_video_motion_model("stabilityai/stable-video-diffusion-img2vid-xt")


def test_cogvideox_is_text_to_video_path() -> None:
    assert not is_image_to_video_motion_model("THUDM/CogVideoX-5b")


def test_wan_t2v_is_text_to_video_path() -> None:
    assert not is_image_to_video_motion_model("Wan-AI/Wan2.2-T2V-A14B-Diffusers")
