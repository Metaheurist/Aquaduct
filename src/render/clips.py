from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.core.config import get_paths
from src.models.model_manager import resolve_pretrained_load_path
from src.models.torch_dtypes import torch_float16
from src.render.utils_ffmpeg import ensure_ffmpeg
from src.util.utils_vram import cleanup_vram, vram_guard


@dataclass(frozen=True)
class GeneratedClip:
    path: Path
    prompt: str


def _norm_repo_id(model_id: str) -> str:
    return (model_id or "").strip().lower()


def _strip_negative_and_cap_for_clip(model_id: str, prompt: str) -> str:
    """
    Text-to-video pipelines often use CLIP text encoders with small context (e.g. 77 tokens).
    Strip our diffusion-conditioning artifacts and cap by words conservatively.
    """
    s = " ".join((prompt or "").split()).strip()
    if "\nNEGATIVE:" in s:
        s = s.split("\nNEGATIVE:", 1)[0].strip()
    low = s.lower()
    if " negative :" in low:
        s = s[: low.find(" negative :")].strip()
    if " negative:" in low:
        s = s[: low.find(" negative:")].strip()
    # Conservative caps (word-based) to avoid CLIP overflow.
    cap = 55 if "zeroscope" in _norm_repo_id(model_id) else 90
    parts = [p for p in s.split() if p]
    if len(parts) > cap:
        s = " ".join(parts[:cap]).strip()
    return s


# Curated video-generation repo ids from ``model_manager.model_options`` (img→vid / text→vid).
# Keep in sync when adding Hub entries used by ``generate_clips``.
CURATED_VIDEO_CLIP_REPO_IDS: frozenset[str] = frozenset(
    {
        "stabilityai/stable-video-diffusion-img2vid-xt",
        "cerspense/zeroscope_v2_576w",
    }
)


def _video_pipe_kwargs(model_id: str, *, num_frames: int) -> dict:
    """Inference kwargs for ``DiffusionPipeline.__call__`` when generating short MP4 clips."""
    mid = _norm_repo_id(model_id)
    nf = max(8, int(num_frames))

    # Exact ids from model_options
    if mid == "stabilityai/stable-video-diffusion-img2vid-xt":
        return {
            "num_frames": nf,
            "num_inference_steps": 25,
            "noise_aug_strength": 0.02,
            "motion_bucket_id": 127,
            "decode_chunk_size": 8,
        }

    if mid == "cerspense/zeroscope_v2_576w":
        return {
            "num_frames": nf,
            "num_inference_steps": 40,
            "height": 320,
            "width": 576,
        }

    # Heuristic fallbacks for user-typed Hub ids
    if "stable-video-diffusion" in mid or "img2vid" in mid:
        return {
            "num_frames": nf,
            "num_inference_steps": 25,
            "noise_aug_strength": 0.02,
            "motion_bucket_id": 127,
            "decode_chunk_size": 8,
        }
    if "zeroscope" in mid:
        return {
            "num_frames": nf,
            "num_inference_steps": 40,
            "height": 320,
            "width": 576,
        }

    return {"num_frames": nf, "num_inference_steps": 25}


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

    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_paths().models_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    vkw = _video_pipe_kwargs(model_id, num_frames=frames_n)

    try:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16, low_cpu_mem_usage=True)
    except TypeError:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16)
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("cpu")

    results: list[GeneratedClip] = []
    for i, p in enumerate(prompts, start=1):
        out = pipe(prompt=p, **vkw)
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

    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_paths().models_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    vkw = _video_pipe_kwargs(model_id, num_frames=frames_n)

    try:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16, low_cpu_mem_usage=True)
    except TypeError:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16)
    pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")

    results: list[GeneratedClip] = []
    pairs = list(zip(init_images, prompts))
    for i, (img_path, p) in enumerate(pairs, start=1):
        image = Image.open(img_path).convert("RGB")
        out = pipe(prompt=p, image=image, **vkw)
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


def extract_pngs_from_mp4(
    mp4: Path,
    out_dir: Path,
    *,
    n: int,
    ffmpeg_dir: Path,
    prefix: str = "img_",
) -> list[Path]:
    """
    Decode ``n`` evenly spaced frames from an MP4 into ``out_dir``/{prefix}001.png …
    Used for Pro mode when the Video slot runs text-to-video (e.g. Zeroscope).
    """
    exe = ensure_ffmpeg(ffmpeg_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_pro_extract_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    for old in tmp.glob("f_*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    pat = str(tmp / "f_%06d.png")
    subprocess.run(
        [str(exe), "-y", "-i", str(mp4), "-vsync", "0", pat],
        check=True,
        capture_output=True,
        text=True,
    )
    frames = sorted(tmp.glob("f_*.png"))
    if not frames:
        raise RuntimeError(f"No frames extracted from {mp4}")
    n = max(1, int(n))
    out_paths: list[Path] = []
    if len(frames) <= n:
        for i in range(n):
            src = frames[min(i, len(frames) - 1)]
            dst = out_dir / f"{prefix}{i + 1:03d}.png"
            shutil.copy2(src, dst)
            out_paths.append(dst)
    else:
        idxs = [int(round(j * (len(frames) - 1) / max(1, n - 1))) for j in range(n)] if n > 1 else [0]
        for i, ix in enumerate(idxs):
            dst = out_dir / f"{prefix}{i + 1:03d}.png"
            shutil.copy2(frames[ix], dst)
            out_paths.append(dst)
    for p in frames:
        try:
            p.unlink()
        except OSError:
            pass
    return out_paths


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
    from debug import dprint

    dprint(
        "clips",
        "generate_clips",
        f"model={video_model_id!r}",
        f"max={max_clips}",
        f"img2vid={bool(init_images)}",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = [_strip_negative_and_cap_for_clip(video_model_id, p) for p in prompts if (p or "").strip()]
    if not prompts:
        prompts = ["high-contrast cyberpunk UI, neon, sharp, cinematic, 9:16 composition"]
    prompts = prompts[: max(1, int(max_clips))]
    init_images = (init_images or [])[: len(prompts)]

    with vram_guard():
        try:
            if init_images:
                r = _try_image_to_video(video_model_id, prompts, init_images, out_dir, fps=fps, seconds=seconds_per_clip)
            else:
                r = _try_text_to_video(video_model_id, prompts, out_dir, fps=fps, seconds=seconds_per_clip)
            dprint("clips", "generate_clips done", f"count={len(r)}")
            return r
        except Exception:
            clips: list[GeneratedClip] = []
            for i, p in enumerate(prompts, start=1):
                out_path = out_dir / f"clip_{i:03d}.mp4"
                _fallback_clip_from_image(out_path, fps=fps, seconds=seconds_per_clip)
                clips.append(GeneratedClip(path=out_path, prompt=p))
            dprint("clips", "generate_clips fallback placeholders", f"count={len(clips)}")
            return clips

