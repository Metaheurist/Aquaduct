"""Curated Hub diffusion models must each have explicit preset entries (artist + clips)."""

from __future__ import annotations

from src.render.artist import CURATED_TEXT2IMAGE_REPO_IDS, _IMAGE_T2I_PRESETS, _diffusion_kw_for_model
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
        if rid == "wan-ai/wan2.2-t2v-a14b-diffusers":
            assert kw["height"] == 480 and kw["width"] == 832
        elif rid == "genmo/mochi-1.5-final":
            assert kw["num_frames"] == 24
        elif rid == "thudm/cogvideox-5b":
            assert kw["num_frames"] == 24 and kw["guidance_scale"] == 6.0
        elif rid == "tencent/hunyuanvideo":
            assert kw["width"] == 960 and kw["height"] == 544 and kw["num_frames"] == 24
        elif rid == "lightricks/ltx-2":
            assert kw["height"] == 3840 and kw["width"] == 2176 and kw["guidance_scale"] == 4.0
        assert kw["num_inference_steps"] >= 1

    svd = _video_pipe_kwargs("stabilityai/stable-video-diffusion-img2vid-xt", num_frames=16)
    assert svd["motion_bucket_id"] == 127
    zs = _video_pipe_kwargs("cerspense/zeroscope_v2_576w", num_frames=24)
    assert zs["width"] == 576 and zs["height"] == 320
    cv5 = _video_pipe_kwargs("thudm/cogvideox-5b", num_frames=24)
    assert cv5["guidance_scale"] == 6.0
    hy = _video_pipe_kwargs("tencent/hunyuanvideo", num_frames=24)
    assert hy["width"] == 960 and hy["height"] == 544


def test_image_t2i_presets_frontier_examples():
    fs = _diffusion_kw_for_model("black-forest-labs/FLUX.1-schnell", steps=4)
    assert fs["guidance_scale"] == 0.0 and fs["num_inference_steps"] == 4
    fu = _diffusion_kw_for_model("black-forest-labs/FLUX.1.1-pro-ultra", steps=12)
    assert fu["guidance_scale"] == 3.5 and fu["num_inference_steps"] == 12
    fd = _diffusion_kw_for_model("black-forest-labs/FLUX.1-dev", steps=30)
    assert fd["guidance_scale"] == 3.5 and fd["num_inference_steps"] == 30
    sd35 = _diffusion_kw_for_model("stabilityai/stable-diffusion-3.5-medium", steps=28)
    assert sd35["guidance_scale"] == 7.0 and sd35["num_inference_steps"] == 28
    tr = _diffusion_kw_for_model("stabilityai/stable-diffusion-3.5-large-turbo", steps=4)
    assert tr["guidance_scale"] == 1.0 and tr["num_inference_steps"] == 4
