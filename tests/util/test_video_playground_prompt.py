from __future__ import annotations

from src.util.video_playground_prompt import (
    video_playground_motion_ui_kind,
    video_playground_prompt_char_limit,
)


def test_limit_kling_api() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="api", api_provider="kling")
    assert lim == 2000


def test_limit_magic_hour_api() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="api", api_provider="magic_hour")
    assert lim == 2000


def test_limit_replicate_api() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="api", api_provider="replicate")
    assert lim == 2500


def test_limit_local_cogvideox() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="local", video_repo_id="THUDM/cogvideox-5b")
    assert lim == 1800


def test_limit_local_zeroscope() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="local", video_repo_id="cerspense/zeroscope_v2_576w")
    assert lim == 320


def test_limit_local_svd_image_only_ui() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="local", video_repo_id="stabilityai/stable-video-diffusion-img2vid")
    assert lim == 0


def test_limit_local_empty_repo_defaults_clip() -> None:
    lim, _ = video_playground_prompt_char_limit(mode="local", video_repo_id="")
    assert lim == 320


def test_motion_kind_api() -> None:
    assert video_playground_motion_ui_kind(mode="api") == "api_t2v"


def test_motion_kind_cogvideox_t2v() -> None:
    assert video_playground_motion_ui_kind(mode="local", video_repo_id="THUDM/CogVideoX-5b") == "local_t2v"


def test_motion_kind_svd_image_only() -> None:
    assert (
        video_playground_motion_ui_kind(mode="local", video_repo_id="stabilityai/stable-video-diffusion-img2vid")
        == "local_img2vid_image_only"
    )
