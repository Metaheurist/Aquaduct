from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .utils_vram import cleanup_vram, vram_guard


@dataclass(frozen=True)
class GeneratedClip:
    path: Path
    prompt: str


def _write_mp4_from_frames(frames: list[np.ndarray], out_path: Path, *, fps: int) -> None:
    import imageio

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with imageio.get_writer(str(out_path), fps=fps, codec="libx264", quality=8) as w:
        for fr in frames:
            if fr.dtype != np.uint8:
                fr = np.clip(fr, 0, 255).astype(np.uint8)
            w.append_data(fr)


def _try_text_to_video(model_id: str, prompts: list[str], out_dir: Path, *, fps: int, seconds: float) -> list[GeneratedClip]:
    """
    Best-effort text-to-video using diffusers. Different repos expose different pipelines; we use the generic
    DiffusionPipeline and common kwargs. If this fails, caller should fall back.
    """
    import torch
    from diffusers import DiffusionPipeline

    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))

    pipe = DiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16)
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("cpu")

    results: list[GeneratedClip] = []
    for i, p in enumerate(prompts, start=1):
        out = pipe(
            prompt=p,
            num_frames=frames_n,
            num_inference_steps=25,
        )
        # Common outputs: .frames (list[list[PIL]]), .images (PIL), or dict with "frames"
        pil_frames = None
        if hasattr(out, "frames"):
            pil_frames = out.frames[0] if isinstance(out.frames, list) and out.frames and isinstance(out.frames[0], list) else out.frames
        elif isinstance(out, dict) and "frames" in out:
            pil_frames = out["frames"]
        elif hasattr(out, "images"):
            pil_frames = out.images

        if not pil_frames:
            raise RuntimeError("Video pipeline returned no frames.")

        frames = [np.array(fr.convert("RGB")) for fr in pil_frames]
        out_path = out_dir / f"clip_{i:03d}.mp4"
        _write_mp4_from_frames(frames, out_path, fps=fps)
        results.append(GeneratedClip(path=out_path, prompt=p))

    del pipe
    cleanup_vram()
    return results


def _try_image_to_video(
    model_id: str,
    prompts: list[str],
    init_images: list[Path],
    out_dir: Path,
    *,
    fps: int,
    seconds: float,
) -> list[GeneratedClip]:
    """
    Best-effort img→vid. We try passing `image=` to a diffusers pipeline; if the repo doesn't support it,
    this will raise and caller can fall back.
    """
    import torch
    from diffusers import DiffusionPipeline
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))

    pipe = DiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16)
    pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")

    results: list[GeneratedClip] = []
    pairs = list(zip(init_images, prompts))
    for i, (img_path, p) in enumerate(pairs, start=1):
        image = Image.open(img_path).convert("RGB")
        out = pipe(
            prompt=p,
            image=image,
            num_frames=frames_n,
            num_inference_steps=25,
        )
        pil_frames = None
        if hasattr(out, "frames"):
            pil_frames = out.frames[0] if isinstance(out.frames, list) and out.frames and isinstance(out.frames[0], list) else out.frames
        elif isinstance(out, dict) and "frames" in out:
            pil_frames = out["frames"]
        elif hasattr(out, "images"):
            pil_frames = out.images
        if not pil_frames:
            raise RuntimeError("Video pipeline returned no frames.")
        frames = [np.array(fr.convert("RGB")) for fr in pil_frames]
        out_path = out_dir / f"clip_{i:03d}.mp4"
        _write_mp4_from_frames(frames, out_path, fps=fps)
        results.append(GeneratedClip(path=out_path, prompt=p))

    del pipe
    cleanup_vram()
    return results


def _fallback_clip_from_image(out_path: Path, *, fps: int, seconds: float, w: int = 1080, h: int = 1920) -> None:
    """
    Fallback: generate a solid-color clip so the pipeline can complete even if video models can't run.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    fr = np.zeros((h, w, 3), dtype=np.uint8)
    fr[:, :, :] = (10, 10, 16)
    _write_mp4_from_frames([fr] * frames_n, out_path, fps=fps)


def generate_clips(
    *,
    video_model_id: str,
    prompts: list[str],
    init_images: list[Path] | None = None,
    out_dir: Path,
    max_clips: int,
    fps: int,
    seconds_per_clip: float,
) -> list[GeneratedClip]:
    """
    Generates a small set of MP4 clips using a video generation model when possible.
    Falls back to placeholder clips if the model can't run.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = [p.strip() for p in prompts if p.strip()]
    if not prompts:
        prompts = ["high-contrast cyberpunk UI, neon, sharp, cinematic, 9:16 composition"]
    prompts = prompts[: max(1, int(max_clips))]
    init_images = (init_images or [])[: len(prompts)]

    with vram_guard():
        try:
            if init_images:
                return _try_image_to_video(video_model_id, prompts, init_images, out_dir, fps=fps, seconds=seconds_per_clip)
            return _try_text_to_video(video_model_id, prompts, out_dir, fps=fps, seconds=seconds_per_clip)
        except Exception:
            clips: list[GeneratedClip] = []
            for i, p in enumerate(prompts, start=1):
                out_path = out_dir / f"clip_{i:03d}.mp4"
                _fallback_clip_from_image(out_path, fps=fps, seconds=seconds_per_clip)
                clips.append(GeneratedClip(path=out_path, prompt=p))
            return clips

