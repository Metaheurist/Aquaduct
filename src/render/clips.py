from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.core.models_dir import get_models_dir
from src.models.model_manager import resolve_pretrained_load_path
from src.models.torch_dtypes import torch_float16
from src.render.utils_ffmpeg import ensure_ffmpeg
from src.util.diffusion_placement import place_diffusion_pipeline
from src.util.utils_vram import cleanup_vram, prepare_for_next_model, vram_guard


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
    low_id = _norm_repo_id(model_id)
    if "zeroscope" in low_id or "text-to-video-ms" in low_id or "modelscope" in low_id:
        cap = 55
    else:
        cap = 90
    parts = [p for p in s.split() if p]
    if len(parts) > cap:
        s = " ".join(parts[:cap]).strip()
    return s


# Curated video-generation repo ids from ``model_manager.model_options`` (img→vid / text→vid).
# Keep in sync when adding Hub entries used by ``generate_clips``.
CURATED_VIDEO_CLIP_REPO_IDS: frozenset[str] = frozenset(
    {
        "stabilityai/stable-video-diffusion-img2vid-xt",
        "stabilityai/stable-video-diffusion-img2vid",
        "cerspense/zeroscope_v2_576w",
        "cerspense/zeroscope_v2_30x448x256",
        "damo-vilab/text-to-video-ms-1.7b",
    }
)


def _svd_cap_num_frames(requested: int) -> int:
    """
    Stable Video Diffusion img2vid is trained for a small num_frames (typically ≤25).

    We also derive num_frames from fps×seconds; that must not exceed the model ceiling or VRAM explodes.
    On ≤10 GB VRAM, use a tighter cap to reduce peak memory during temporal attention.
    """
    nf = max(8, int(requested))
    cap = 25
    try:
        from src.models.hardware import get_hardware_info

        v = get_hardware_info().vram_gb
        if v is not None and v <= 10:
            cap = 14
    except Exception:
        pass
    return min(nf, cap)


def _video_pipe_kwargs(model_id: str, *, num_frames: int) -> dict:
    """Inference kwargs for ``DiffusionPipeline.__call__`` when generating short MP4 clips."""
    mid = _norm_repo_id(model_id)
    nf = max(8, int(num_frames))

    # Exact ids from model_options
    if mid == "stabilityai/stable-video-diffusion-img2vid-xt":
        return {
            "num_frames": _svd_cap_num_frames(nf),
            "num_inference_steps": 25,
            "noise_aug_strength": 0.02,
            "motion_bucket_id": 127,
            "decode_chunk_size": 4,
        }

    if mid == "cerspense/zeroscope_v2_576w":
        return {
            "num_frames": nf,
            "num_inference_steps": 40,
            "height": 320,
            "width": 576,
        }

    if mid == "cerspense/zeroscope_v2_30x448x256":
        return {
            "num_frames": nf,
            "num_inference_steps": 40,
            "height": 256,
            "width": 448,
        }

    if mid in ("damo-vilab/text-to-video-ms-1.7b", "ali-vilab/text-to-video-ms-1.7b"):
        return {
            "num_frames": min(max(8, nf), 24),
            "num_inference_steps": 25,
            "height": 256,
            "width": 256,
        }

    # Heuristic fallbacks for user-typed Hub ids
    if "stable-video-diffusion" in mid or ("img2vid" in mid and "zeroscope" not in mid):
        return {
            "num_frames": _svd_cap_num_frames(nf),
            "num_inference_steps": 25,
            "noise_aug_strength": 0.02,
            "motion_bucket_id": 127,
            "decode_chunk_size": 4,
        }
    if "zeroscope" in mid:
        if "30x448" in mid or "448x256" in mid:
            return {
                "num_frames": nf,
                "num_inference_steps": 40,
                "height": 256,
                "width": 448,
            }
        return {
            "num_frames": nf,
            "num_inference_steps": 40,
            "height": 320,
            "width": 576,
        }
    if "text-to-video-ms" in mid or "modelscope" in mid:
        return {
            "num_frames": min(max(8, nf), 24),
            "num_inference_steps": 25,
            "height": 256,
            "width": 256,
        }

    return {"num_frames": nf, "num_inference_steps": 25}


def _img2vid_accepts_text_prompt(model_id: str) -> bool:
    """
    Stable Video Diffusion img2vid pipelines condition only on the input image — no ``prompt`` kwarg.

    Text-to-video models (e.g. ZeroScope) use ``prompt``; pass that through when supported.
    """
    mid = _norm_repo_id(model_id)
    if "stable-video-diffusion" in mid:
        return False
    if "img2vid" in mid and "zeroscope" not in mid:
        return False
    return True


def _write_mp4_from_frames(frames: list[np.ndarray], out_path: Path, *, fps: int) -> None:
    import imageio

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Default macro_block_size=16 makes imageio pad widths like 1080 -> 1088 before libx264.
    # Use 1 to preserve exact frame sizes (common 9:16 presets) and avoid noisy warnings.
    with imageio.get_writer(
        str(out_path), fps=fps, codec="libx264", quality=8, macro_block_size=1
    ) as w:
        for fr in frames:
            if fr.dtype != np.uint8:
                fr = np.clip(fr, 0, 255).astype(np.uint8)
            w.append_data(fr)


def _maybe_enable_slice_inference(pipe) -> None:
    """Lower peak VRAM for diffusers pipelines that support VAE/attention slicing."""
    for name in ("enable_vae_slicing", "enable_attention_slicing"):
        fn = getattr(pipe, name, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass


def _try_text_to_video(
    model_id: str,
    prompts: list[str],
    out_dir: Path,
    *,
    fps: int,
    seconds: float,
    cuda_device_index: int | None = None,
) -> list[GeneratedClip]:
    """
    Best-effort text-to-video using diffusers. Different repos expose different pipelines; we use the generic
    DiffusionPipeline and common kwargs. If this fails, caller should fall back.
    """
    from diffusers import DiffusionPipeline

    prepare_for_next_model()
    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    vkw = _video_pipe_kwargs(model_id, num_frames=frames_n)

    try:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16, low_cpu_mem_usage=True)
    except TypeError:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16)
    place_diffusion_pipeline(pipe, cuda_device_index=cuda_device_index)
    _maybe_enable_slice_inference(pipe)

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
    cuda_device_index: int | None = None,
) -> list[GeneratedClip]:
    """
    Best-effort img→vid. We try passing `image=` to a diffusers pipeline; if the repo doesn't support it,
    this will raise and caller can fall back.
    """
    from diffusers import DiffusionPipeline
    from PIL import Image

    prepare_for_next_model()
    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    vkw = _video_pipe_kwargs(model_id, num_frames=frames_n)

    try:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16, low_cpu_mem_usage=True)
    except TypeError:
        pipe = DiffusionPipeline.from_pretrained(load_path, torch_dtype=_fp16)
    place_diffusion_pipeline(pipe, cuda_device_index=cuda_device_index)
    _maybe_enable_slice_inference(pipe)

    results: list[GeneratedClip] = []
    pairs = list(zip(init_images, prompts))
    use_prompt = _img2vid_accepts_text_prompt(model_id)
    for i, (img_path, p) in enumerate(pairs, start=1):
        image = Image.open(img_path).convert("RGB")
        if use_prompt:
            out = pipe(prompt=p, image=image, **vkw)
        else:
            out = pipe(image=image, **vkw)
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
    cuda_device_index: int | None = None,
) -> list[GeneratedClip]:
    """
    Generates a small set of MP4 clips with the configured video model.

    On load or inference failure, raises the underlying exception (no placeholder clips).
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
        prompts = ["vertical 9:16, one clear focal subject, bold readable composition, matches narration topic"]
    prompts = prompts[: max(1, int(max_clips))]
    init_images = (init_images or [])[: len(prompts)]

    with vram_guard():
        if init_images:
            r = _try_image_to_video(
                video_model_id,
                prompts,
                init_images,
                out_dir,
                fps=fps,
                seconds=seconds_per_clip,
                cuda_device_index=cuda_device_index,
            )
        else:
            r = _try_text_to_video(
                video_model_id,
                prompts,
                out_dir,
                fps=fps,
                seconds=seconds_per_clip,
                cuda_device_index=cuda_device_index,
            )
        if not r:
            raise RuntimeError(
                f"Video model {video_model_id!r} produced no clips. "
                "Check the Model tab, GPU/CUDA, and that the repo downloaded completely (e.g. unet/vae weights)."
            )
        dprint("clips", "generate_clips done", f"count={len(r)}")
        return r

