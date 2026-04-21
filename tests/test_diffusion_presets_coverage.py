"""Curated Hub diffusion models must each have explicit preset entries (artist + clips)."""

from __future__ import annotations

from src.render.artist import CURATED_TEXT2IMAGE_REPO_IDS, _IMAGE_T2I_PRESETS
from src.render.clips import CURATED_VIDEO_CLIP_REPO_IDS, _video_pipe_kwargs
from src.models.model_manager import model_options


def test_curated_text2image_presets_match_registry():
    assert CURATED_TEXT2IMAGE_REPO_IDS == frozenset(_IMAGE_T2I_PRESETS.keys())


def test_model_options_image_models_have_t2i_preset():
    """Every image-kind option has an explicit T2I preset."""
    needed: set[str] = set()
    for o in model_options():
        if o.kind != "image":
            continue
        needed.add(o.repo_id.strip().lower())
    assert needed == CURATED_TEXT2IMAGE_REPO_IDS
    assert needed <= frozenset(_IMAGE_T2I_PRESETS.keys())


def test_model_options_video_clip_models_match_clip_registry():
    needed: set[str] = set()
    for o in model_options():
        if o.kind != "video":
            continue
        needed.add(o.repo_id.strip().lower())
    assert needed == CURATED_VIDEO_CLIP_REPO_IDS


def test_video_pipe_kwargs_for_each_curated_clip_model():
    for rid in CURATED_VIDEO_CLIP_REPO_IDS:
        kw = _video_pipe_kwargs(rid, num_frames=24)
        if "stable-video-diffusion" in rid:
            assert kw["num_frames"] <= 24
        else:
            assert kw["num_frames"] == 24
        assert kw["num_inference_steps"] >= 1
    svd = _video_pipe_kwargs("stabilityai/stable-video-diffusion-img2vid-xt", num_frames=16)
    assert svd["motion_bucket_id"] == 127
    zs = _video_pipe_kwargs("cerspense/zeroscope_v2_576w", num_frames=24)
    assert zs["width"] == 576 and zs["height"] == 320
    zs_s = _video_pipe_kwargs("cerspense/zeroscope_v2_30x448x256", num_frames=24)
    assert zs_s["width"] == 448 and zs_s["height"] == 256
    ms = _video_pipe_kwargs("damo-vilab/text-to-video-ms-1.7b", num_frames=16)
    assert ms["width"] == 256 and ms["height"] == 256 and ms["num_frames"] == 16
