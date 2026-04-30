"""
Mock end-to-end exercise of Pro mode + Stable Video Diffusion (image-to-video).

Validates wiring: script scenes → image model keyframes → img2vid clips → final assemble,
without loading diffusers or FFmpeg internals.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.content.brain import ScriptSegment, VideoPackage
from src.core.config import AppSettings, Paths, VideoSettings
from src.render.artist import GeneratedImage
from src.render.clips import GeneratedClip


def _paths(tmp_path: Path) -> Paths:
    ada = tmp_path / ".Aquaduct_data"
    p = Paths(
        root=tmp_path,
        app_data_dir=ada,
        data_dir=ada / "data",
        news_cache_dir=ada / "data" / "news_cache",
        runs_dir=ada / "runs",
        videos_dir=ada / "videos",
        pictures_dir=ada / "pictures",
        models_dir=ada / "models",
        cache_dir=ada / ".cache",
        ffmpeg_dir=ada / ".cache" / "ffmpeg",
    )
    for d in (
        p.news_cache_dir,
        p.runs_dir,
        p.videos_dir,
        p.pictures_dir,
        p.models_dir,
        p.cache_dir,
        p.ffmpeg_dir,
    ):
        d.mkdir(parents=True, exist_ok=True)
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    (p.ffmpeg_dir / exe).write_bytes(b"")
    return p


def test_pro_stable_video_diffusion_pipeline_mock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import main as pipeline_main
    import src.render.editor as editor_mod

    paths = _paths(tmp_path)
    monkeypatch.setattr(pipeline_main, "get_paths", lambda: paths)
    monkeypatch.setattr(
        pipeline_main,
        "preflight_check",
        lambda **kwargs: type("R", (), {"ok": True, "errors": [], "warnings": []})(),
    )
    monkeypatch.setattr(pipeline_main, "prepare_for_next_model", lambda *_a, **_k: None)
    monkeypatch.setattr(editor_mod, "_ffmpeg_align_wav_to_duration", lambda *a, **k: None)

    capture: dict = {}

    def _fake_synthesize(**kwargs: object) -> None:
        out_wav = kwargs["out_wav_path"]
        assert isinstance(out_wav, Path)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"fake_wav")
        cap = kwargs.get("out_captions_json")
        if isinstance(cap, Path):
            cap.write_text('{"words":[]}', encoding="utf-8")

    def _fake_gen_images(**kwargs: object) -> list[GeneratedImage]:
        capture["image_kw"] = kwargs
        out_dir = kwargs["out_dir"]
        assert isinstance(out_dir, Path)
        out_dir.mkdir(parents=True, exist_ok=True)
        prompts = list(kwargs.get("prompts") or [])
        seeds = list(kwargs.get("seeds") or [])
        out: list[GeneratedImage] = []
        for i, pr in enumerate(prompts):
            pth = out_dir / f"kf_{i:03d}.png"
            pth.write_bytes(b"\x89PNG\r\n\x1a\n")
            out.append(GeneratedImage(path=pth, prompt=str(pr)))
        assert len(seeds) == len(prompts)
        return out

    def _fake_gen_clips(**kwargs: object) -> list[GeneratedClip]:
        capture["clip_kw"] = kwargs
        out_dir = kwargs["out_dir"]
        assert isinstance(out_dir, Path)
        out_dir.mkdir(parents=True, exist_ok=True)
        prompts = list(kwargs.get("prompts") or [])
        inits = list(kwargs.get("init_images") or [])
        assert len(inits) == len(prompts)
        clips: list[GeneratedClip] = []
        for i, pr in enumerate(prompts):
            pth = out_dir / f"clip_{i + 1:03d}.mp4"
            pth.write_text("fake", encoding="utf-8")
            clips.append(GeneratedClip(path=pth, prompt=str(pr)))
        return clips

    def _fake_assemble(**kwargs: object) -> None:
        capture["assemble_kw"] = kwargs
        out = kwargs["out_final_mp4"]
        assert isinstance(out, Path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake_mp4")

    monkeypatch.setattr(pipeline_main, "synthesize", _fake_synthesize)
    monkeypatch.setattr(pipeline_main, "process_voice_wav", lambda **kwargs: kwargs["in_wav"])
    monkeypatch.setattr(pipeline_main, "generate_images", _fake_gen_images)
    monkeypatch.setattr(pipeline_main, "generate_clips", _fake_gen_clips)
    monkeypatch.setattr(pipeline_main, "assemble_generated_clips_then_concat", _fake_assemble)

    pkg = VideoPackage(
        title="Mock headline for Pro",
        description="",
        hashtags=[],
        hook="Open hook.",
        segments=[
            ScriptSegment(narration="First narration beat.", visual_prompt="v1", on_screen_text=""),
            ScriptSegment(narration="Second narration beat.", visual_prompt="v2", on_screen_text=""),
        ],
        cta="Subscribe.",
    )

    video = VideoSettings(
        use_image_slideshow=False,
        pro_mode=True,
        pro_clip_seconds=4.0,
        fps=24,
    )
    app = AppSettings(
        video=video,
        video_format="news",
        video_model_id="stabilityai/stable-video-diffusion-img2vid-xt",
        image_model_id="stabilityai/sdxl-turbo-1.0",
    )

    out = pipeline_main.run_once(
        settings=app,
        prebuilt_pkg=pkg,
        prebuilt_sources=[{"title": "t", "url": "u", "source": "s"}],
        prebuilt_prompts=["v1", "v2"],
        prebuilt_seeds=[1, 2],
    )

    assert out is not None
    assert out.name == "final.mp4"
    assets = out.parent / "assets"
    assert (assets / "pro_prompt.txt").is_file()
    assert (assets / "pro_keyframes").is_dir()
    text = (assets / "pro_prompt.txt").read_text(encoding="utf-8")
    assert "Mock headline for Pro" in text
    img_kw = capture.get("image_kw") or {}
    clip_kw = capture.get("clip_kw") or {}
    assert img_kw.get("sdxl_turbo_model_id") == "stabilityai/sdxl-turbo-1.0"
    assert clip_kw.get("video_model_id") == "stabilityai/stable-video-diffusion-img2vid-xt"
    pro_prompts = list(img_kw.get("prompts") or [])
    assert pro_prompts == list(clip_kw.get("prompts") or [])
    assert len(pro_prompts) >= 1
    assert img_kw.get("max_images") == len(pro_prompts)
    assert len(clip_kw.get("init_images") or []) == len(pro_prompts)


def test_split_pro_scenes_respects_video_format_cartoon() -> None:
    from main import _split_into_pro_scenes_from_script

    pkg = VideoPackage(
        title="Long Title That Should Not Appear In Cartoon Scenes",
        description="",
        hashtags=[],
        hook="Hook only.",
        segments=[ScriptSegment(narration="Beat one.", visual_prompt="x", on_screen_text="")],
        cta="",
    )
    scenes = _split_into_pro_scenes_from_script(pkg=pkg, prompts=["x"], video_format="cartoon")
    assert scenes
    joined = " ".join(scenes)
    assert "Long Title That Should Not" not in joined
