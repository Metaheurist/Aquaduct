from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.core.config import AppSettings
from src.core.models_dir import get_models_dir
from src.models.model_manager import resolve_pretrained_load_path
from src.models.torch_dtypes import torch_float16
from src.render.utils_ffmpeg import ensure_ffmpeg
from src.util.diffusion_placement import place_diffusion_pipeline
from src.util.diffusers_load import diffusers_from_pretrained
from src.util.cuda_capabilities import cuda_device_reported_by_torch
from src.util.memory_budget import release_between_stages
from src.util.utils_vram import cleanup_vram, vram_guard


@dataclass(frozen=True)
class GeneratedClip:
    path: Path
    prompt: str


def _norm_repo_id(model_id: str) -> str:
    return (model_id or "").strip().lower()


def _truncate_clip_text_encoder_77(text: str, *, low_id: str) -> str:
    """
    Many T2V / composite pipelines use OpenAI-style CLIP with **max 77 tokens** for the text branch.
    CogVideoX (T5) and LTX (long context) are skipped — see model-specific branches in callers.
    Mochi / Wan (T5- or UMT5-class) skip CLIP-77; Hunyuan uses a long path below.
    """
    if "cogvideox" in low_id or "ltx-video" in low_id or "lightricks/ltx" in low_id:
        return text
    if "mochi" in low_id or "wan-ai" in low_id or "wan2" in low_id:
        return text
    t = (text or "").strip()
    if not t:
        return t
    try:
        from transformers import CLIPTokenizerFast

        tok = CLIPTokenizerFast.from_pretrained("openai/clip-vit-large-patch14", local_files_only=True)
    except Exception:
        try:
            from transformers import CLIPTokenizerFast

            tok = CLIPTokenizerFast.from_pretrained("openai/clip-vit-large-patch14")
        except Exception:
            return text
    try:
        ids = tok.encode(t, truncation=True, max_length=77)
        return tok.decode(ids, skip_special_tokens=True).strip()
    except Exception:
        return text


def _strip_negative_and_cap_for_clip(model_id: str, prompt: str) -> str:
    """
    Text-to-video pipelines often use CLIP text encoders with a **77-token** limit (tokens ≠ words).
    Strip diffusion-conditioning artifacts; cap words conservatively (~1.2–1.8 tokens/word for English).
    """
    s = " ".join((prompt or "").split()).strip()
    if "\nNEGATIVE:" in s:
        s = s.split("\nNEGATIVE:", 1)[0].strip()
    low = s.lower()
    if " negative :" in low:
        s = s[: low.find(" negative :")].strip()
    if " negative:" in low:
        s = s[: low.find(" negative:")].strip()
    # Drop redundant aspect hints at the end (pipe sets resolution; CLIP budget is tiny).
    s = re.sub(r",\s*vertical\s+9\s*:\s*16\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r",\s*9\s*:\s*16\s*$", "", s, flags=re.IGNORECASE)
    s = " ".join(s.split()).strip().strip(",")
    low_id = _norm_repo_id(model_id)
    # CLIP-77 families: stay ≤ ~40 words to land under 77 tokens with punctuation.
    if "zeroscope" in low_id or "text-to-video-ms" in low_id or "modelscope" in low_id:
        cap = 36
    elif "hunyuanvideo" in low_id:
        cap = 42
    elif "cogvideox" in low_id:
        cap = 200
    elif "ltx-video" in low_id or "lightricks/ltx" in low_id:
        cap = 120
    elif "mochi" in low_id or "wan-ai" in low_id or "wan2" in low_id:
        cap = 200
    else:
        cap = 42
    parts = [p for p in s.split() if p]
    if len(parts) > cap:
        s = " ".join(parts[:cap]).strip()
    # Hard char ceiling for CLIP-like stacks (last resort).
    if "cogvideox" not in low_id and len(s) > 320:
        s = s[:320].rsplit(" ", 1)[0].strip()
    # Exact OpenAI CLIP token cap (words ≠ tokens; punctuation/hyphens inflate token count).
    s = _truncate_clip_text_encoder_77(s, low_id=low_id)
    return s


# Curated video-generation repo ids from ``model_manager.model_options`` (img→vid / text→vid).
# Keep in sync when adding Hub entries used by ``generate_clips``.
CURATED_VIDEO_CLIP_REPO_IDS: frozenset[str] = frozenset(
    {
        "wan-ai/wan2.2-t2v-a14b-diffusers",
        "genmo/mochi-1.5-final",
        "thudm/cogvideox-5b",
        "tencent/hunyuanvideo",
        "lightricks/ltx-2",
    }
)


def _svd_cap_num_frames(requested: int) -> int:
    """
    Stable Video Diffusion img2vid is trained for a small num_frames (typically ≤25).

    We also derive num_frames from fps×seconds; that must not exceed the model ceiling or VRAM explodes.
    On ≤10 GB VRAM, use a tighter cap; on ≤12 GB, a moderate cap (Pro often leaves other models on-GPU).
    """
    nf = max(8, int(requested))
    cap = 25
    try:
        from src.models.hardware import get_hardware_info

        v = get_hardware_info().vram_gb
        if v is not None and v <= 10:
            cap = 14
        elif v is not None and v <= 12:
            # 12 GB cards often run Pro with other models still resident; keep temporal batch smaller.
            cap = min(cap, 18)
    except Exception:
        pass
    return min(nf, cap)


def _svd_decode_chunk_size() -> int:
    """Smaller VAE decode batches on 12 GB when other models may still be resident."""
    try:
        from src.models.hardware import get_hardware_info

        v = get_hardware_info().vram_gb
        if v is not None and v <= 12:
            return 2
    except Exception:
        pass
    return 4


def _video_pipe_kwargs(model_id: str, *, num_frames: int) -> dict:
    """Inference kwargs for text-to-video / img2vid ``__call__`` when generating short MP4 clips."""
    mid = _norm_repo_id(model_id)
    nf = max(8, int(num_frames))

    if mid == "wan-ai/wan2.2-t2v-a14b-diffusers":
        # 480P-style defaults; 720P needs more VRAM (see Wan model card / diffusers example).
        nf_w = min(max(17, nf), 97)
        return {
            "num_frames": nf_w,
            "num_inference_steps": 30,
            "height": 480,
            "width": 832,
            "guidance_scale": 5.0,
        }
    if mid == "genmo/mochi-1.5-final":
        # 1.5: longer default clips (~10s); cap ~12.5s @ 24fps (300) to stay in-model.
        nf_m = min(max(8, nf), 300)
        return {
            "num_frames": nf_m,
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
        }
    if mid == "lightricks/ltx-2":
        # 9:16 "4K" vertical for Shorts: both dims divisible by 32 (LTX-2 constraint). Heavy VRAM.
        nf_l = min(max(9, nf), 241)
        while (nf_l - 1) % 8 != 0:
            nf_l = min(nf_l + 1, 241)
        return {
            "num_frames": nf_l,
            "num_inference_steps": 40,
            "height": 3840,
            "width": 2176,
            "frame_rate": 24.0,
            "guidance_scale": 4.0,
            "negative_prompt": (
                "shaky, glitchy, low quality, worst quality, deformed, distorted, disfigured, "
                "motion smear, motion artifacts, fused fingers, bad anatomy, weird hand, ugly, "
                "transition, static"
            ),
        }
    # CogVideoX 5B (dedicated diffusers — see ``_load_text_to_video_pipeline``)
    if mid == "thudm/cogvideox-5b":
        nf_use = min(max(9, nf), 49)
        return {
            "num_frames": nf_use,
            "num_inference_steps": 50,
            "guidance_scale": 6.0,
        }
    if mid == "lightricks/ltx-video":
        nf_adj = max(9, min(nf, 97))
        if nf_adj % 2 == 0:
            nf_adj += 1
        return {
            "num_frames": nf_adj,
            "num_inference_steps": 40,
            "height": 512,
            "width": 704,
            "guidance_scale": 3.0,
            "decode_timestep": 0.03,
            "decode_noise_scale": 0.025,
            "negative_prompt": "worst quality, inconsistent motion, blurry, jittery, distorted",
        }
    if mid == "tencent/hunyuanvideo":
        nf_h = min(max(17, nf), 61)
        return {
            "num_frames": nf_h,
            "num_inference_steps": 35,
            "height": 544,
            "width": 960,
            "guidance_scale": 6.0,
        }

    # Exact ids from model_options
    if mid == "stabilityai/stable-video-diffusion-img2vid-xt":
        return {
            "num_frames": _svd_cap_num_frames(nf),
            "num_inference_steps": 25,
            "noise_aug_strength": 0.02,
            "motion_bucket_id": 127,
            "decode_chunk_size": _svd_decode_chunk_size(),
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
            "decode_chunk_size": _svd_decode_chunk_size(),
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
    if "cogvideox" in mid and "i2v" not in mid:
        return {
            "num_frames": min(max(9, nf), 49),
            "num_inference_steps": 50,
            "guidance_scale": 6.0,
        }
    if "ltx-2" in mid:
        nf_l = min(max(9, nf), 241)
        while (nf_l - 1) % 8 != 0:
            nf_l = min(nf_l + 1, 241)
        return {
            "num_frames": nf_l,
            "num_inference_steps": 40,
            "height": 3840,
            "width": 2176,
            "frame_rate": 24.0,
            "guidance_scale": 4.0,
            "negative_prompt": (
                "shaky, glitchy, low quality, worst quality, deformed, distorted, disfigured, "
                "motion smear, motion artifacts, fused fingers, bad anatomy, weird hand, ugly, "
                "transition, static"
            ),
        }
    if "ltx-video" in mid or ("lightricks/ltx" in mid and "ltx-2" not in mid):
        nf_adj = max(9, min(nf, 97))
        if nf_adj % 2 == 0:
            nf_adj += 1
        return {
            "num_frames": nf_adj,
            "num_inference_steps": 40,
            "height": 512,
            "width": 704,
            "guidance_scale": 3.0,
            "decode_timestep": 0.03,
            "decode_noise_scale": 0.025,
        }
    if "hunyuanvideo" in mid:
        return {
            "num_frames": min(max(17, nf), 61),
            "num_inference_steps": 35,
            "height": 544,
            "width": 960,
            "guidance_scale": 6.0,
        }

    return {"num_frames": nf, "num_inference_steps": 25}


def _video_quant_dtype(quant_mode: str | None, default_dt, _fp16):
    """Pick a torch dtype for a video pipeline given an explicit quant mode (else ``default_dt``)."""
    import torch

    qm = (quant_mode or "").strip().lower()
    if qm == "bf16":
        try:
            return torch.bfloat16
        except Exception:
            return _fp16
    if qm in ("fp16", "int8", "nf4_4bit", "cpu_offload"):
        return _fp16
    return default_dt


def _load_text_to_video_pipeline(
    model_id: str,
    load_path: str,
    _fp16,
    *,
    quant_mode: str | None = None,
):
    """
    Load the appropriate diffusers pipeline for ``model_id``.

    Wan / Mochi / CogVideoX / LTX / HunyuanVideo use concrete pipeline classes; generic
    ``DiffusionPipeline`` works for ZeroScope, ModelScope, and many community repos.

    ``quant_mode`` can override dtype (``bf16``/``fp16``) and triggers ``cpu_offload`` placement
    via the loader's caller. Experimental ``int8``/``nf4_4bit`` falls back to fp16 for video.
    """
    import torch

    mid = _norm_repo_id(model_id)
    if "wan-ai" in mid and "wan2" in mid:
        from diffusers import AutoencoderKLWan, WanPipeline

        from debug import pipeline_console

        pipeline_console(f"Wan T2V: loading VAE submodule from {load_path!r}", stage="video_t2v_load")
        vae = diffusers_from_pretrained(
            AutoencoderKLWan, load_path, subfolder="vae", torch_dtype=torch.float32
        )
        default_dt = torch.bfloat16 if cuda_device_reported_by_torch() else _fp16
        dt = _video_quant_dtype(quant_mode, default_dt, _fp16)
        pipeline_console(
            "Wan T2V: loading main pipeline (diffusers 'Loading pipeline components…' may take several minutes)",
            stage="video_t2v_load",
        )
        pipe = diffusers_from_pretrained(
            WanPipeline,
            load_path,
            vae=vae,
            torch_dtype=dt,
            low_cpu_mem_usage=True,
        )
        pipeline_console("Wan T2V: pipeline weights loaded", stage="video_t2v_load")
        _maybe_enable_slice_inference(pipe)
        try:
            from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler

            pipe.scheduler = UniPCMultistepScheduler.from_config(
                pipe.scheduler.config, flow_shift=3.0
            )
        except Exception:
            pass
        return pipe
    if "mochi" in mid:
        from diffusers import MochiPipeline

        from debug import pipeline_console

        pipeline_console(f"Mochi T2V: loading from {load_path!r}", stage="video_t2v_load")
        dt = _video_quant_dtype(quant_mode, _fp16, _fp16)
        return diffusers_from_pretrained(
            MochiPipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
        )
    if "cogvideox" in mid and "i2v" not in mid:
        from diffusers import CogVideoXPipeline

        dt = _video_quant_dtype(quant_mode, _fp16, _fp16)
        return diffusers_from_pretrained(
            CogVideoXPipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
        )
    if "ltx-2" in mid:
        from diffusers import LTX2Pipeline

        default_dt = torch.bfloat16 if cuda_device_reported_by_torch() else _fp16
        dt = _video_quant_dtype(quant_mode, default_dt, _fp16)
        return diffusers_from_pretrained(
            LTX2Pipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
        )
    if "ltx-video" in mid or mid.startswith("lightricks/ltx"):
        from diffusers import LTXPipeline

        default_dt = torch.bfloat16 if cuda_device_reported_by_torch() else _fp16
        dt = _video_quant_dtype(quant_mode, default_dt, _fp16)
        return diffusers_from_pretrained(
            LTXPipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
        )
    if "hunyuanvideo" in mid:
        from diffusers import HunyuanVideoPipeline

        dt = _video_quant_dtype(quant_mode, _fp16, _fp16)
        return diffusers_from_pretrained(
            HunyuanVideoPipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
        )

    from diffusers import DiffusionPipeline

    from debug import pipeline_console

    pipeline_console(
        f"Generic T2V: DiffusionPipeline.from_pretrained({load_path!r}) — watch Hub / disk I/O",
        stage="video_t2v_load",
    )
    dt = _video_quant_dtype(quant_mode, _fp16, _fp16)
    return diffusers_from_pretrained(
        DiffusionPipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
    )


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
    vae = getattr(pipe, "vae", None)
    if vae is not None and hasattr(vae, "enable_tiling"):
        try:
            vae.enable_tiling()
        except Exception:
            pass
    try:
        from diffusers.models.attention_processor import AttnProcessor2_0

        if hasattr(pipe, "set_attn_processor"):
            pipe.set_attn_processor(AttnProcessor2_0())
    except Exception:
        pass
    try:
        if hasattr(pipe, "enable_xformers_memory_efficient_attention"):
            pipe.enable_xformers_memory_efficient_attention()
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
    inference_settings: AppSettings | None = None,
) -> list[GeneratedClip]:
    """
    Best-effort text-to-video using diffusers. ZeroScope / ModelScope use generic ``DiffusionPipeline``;
    CogVideoX / LTX / HunyuanVideo use dedicated pipeline classes.
    """
    release_between_stages(
        "before_text_to_video_load",
        cuda_device_index=cuda_device_index,
        variant="prepare_diffusion",
    )
    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    vkw = _video_pipe_kwargs(model_id, num_frames=frames_n)
    if inference_settings is not None:
        from src.models.inference_profiles import merge_t2v_from_settings

        vkw = merge_t2v_from_settings(model_id, vkw, inference_settings)

    qm = (
        str(getattr(inference_settings, "video_quant_mode", "auto") or "auto")
        if inference_settings is not None
        else "auto"
    )
    from debug import pipeline_console

    pipeline_console(
        f"T2V resolve: model_id={model_id!r} load_path={load_path!r} quant={qm!r}",
        stage="video_t2v_load",
    )
    try:
        pipe = _load_text_to_video_pipeline(model_id, load_path, _fp16, quant_mode=qm)
    except BaseException as e:
        pipeline_console(
            f"T2V load FAILED before inference: {type(e).__name__}: {e} (model_id={model_id!r})",
            stage="video_t2v_load",
        )
        raise
    pipeline_console("T2V pipeline loaded; placing modules on CUDA / applying offload…", stage="video_t2v_load")
    place_diffusion_pipeline(
        pipe,
        cuda_device_index=cuda_device_index,
        force_offload="model" if qm == "cpu_offload" else None,
        inference_settings=inference_settings,
        model_repo_id=model_id,
        placement_role="video",
        quant_mode=qm,
    )
    try:
        from debug import debug_enabled, dprint

        if debug_enabled("clips"):
            dprint(
                "clips",
                "t2v placement",
                f"cuda={cuda_device_index!r}",
                f"quant={qm!r}",
            )
    except Exception:
        pass
    _maybe_enable_slice_inference(pipe)
    mid_run = _norm_repo_id(model_id)
    if mid_run == "lightricks/ltx-2" and getattr(pipe, "vae", None) is not None:
        try:
            pipe.vae.enable_tiling()
        except Exception:
            pass

    results: list[GeneratedClip] = []
    for i, p in enumerate(prompts, start=1):
        pipeline_console(
            f"T2V inference clip {i}/{len(prompts)} (num_frames≈{vkw.get('num_frames', '?')})",
            stage="video_t2v_infer",
        )
        out = pipe(prompt=p, **vkw)
        out_path = out_dir / f"clip_{i:03d}.mp4"

        if mid_run == "lightricks/ltx-2" and hasattr(out, "frames") and getattr(out, "audio", None) is not None:
            try:
                from diffusers.pipelines.ltx2.export_utils import encode_video
                from diffusers.utils import is_av_available

                if is_av_available():
                    vframes = (
                        out.frames[0]
                        if isinstance(out.frames, list)
                        and out.frames
                        and isinstance(out.frames[0], list)
                        else out.frames
                    )
                    aud = out.audio[0] if isinstance(out.audio, (list, tuple)) and out.audio else out.audio
                    voc = getattr(pipe, "vocoder", None)
                    sr = int(
                        getattr(getattr(voc, "config", None), "output_sampling_rate", 24000)
                        or 24000
                    )
                    fr_ltx = int(vkw.get("frame_rate", fps) or fps)
                    encode_video(vframes, fr_ltx, aud, sr, str(out_path))
                    results.append(GeneratedClip(path=out_path, prompt=p))
                    continue
            except Exception:
                pass

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
        _write_mp4_from_frames(frames, out_path, fps=int(vkw.get("frame_rate", fps) or fps) if mid_run == "lightricks/ltx-2" else fps)
        results.append(GeneratedClip(path=out_path, prompt=p))

    del pipe
    release_between_stages("after_text_to_video_batch", cuda_device_index=cuda_device_index, variant="cheap")
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
    inference_settings: AppSettings | None = None,
) -> list[GeneratedClip]:
    """
    Best-effort img→vid. We try passing `image=` to a diffusers pipeline; if the repo doesn't support it,
    this will raise and caller can fall back.
    """
    from diffusers import DiffusionPipeline
    from PIL import Image

    release_between_stages(
        "before_image_to_video_load",
        cuda_device_index=cuda_device_index,
        variant="prepare_diffusion",
    )
    _fp16 = torch_float16()
    load_path = resolve_pretrained_load_path(model_id, models_dir=get_models_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_n = max(8, int(round(fps * seconds)))
    vkw = _video_pipe_kwargs(model_id, num_frames=frames_n)
    if inference_settings is not None:
        from src.models.inference_profiles import merge_t2v_from_settings

        vkw = merge_t2v_from_settings(model_id, vkw, inference_settings)

    qm = (
        str(getattr(inference_settings, "video_quant_mode", "auto") or "auto")
        if inference_settings is not None
        else "auto"
    )
    dt = _video_quant_dtype(qm, _fp16, _fp16)
    pipe = diffusers_from_pretrained(
        DiffusionPipeline, load_path, torch_dtype=dt, low_cpu_mem_usage=True
    )
    place_diffusion_pipeline(
        pipe,
        cuda_device_index=cuda_device_index,
        force_offload="model" if qm == "cpu_offload" else None,
        inference_settings=inference_settings,
        model_repo_id=model_id,
        placement_role="video",
        quant_mode=qm,
    )
    try:
        from debug import debug_enabled, dprint

        if debug_enabled("clips"):
            dprint(
                "clips",
                "i2v placement",
                f"cuda={cuda_device_index!r}",
                f"quant={qm!r}",
            )
    except Exception:
        pass
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
    release_between_stages("after_image_to_video_batch", cuda_device_index=cuda_device_index, variant="cheap")
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
    inference_settings: AppSettings | None = None,
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
        prompts = ["vertical video, one clear subject, bold composition"]
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
                inference_settings=inference_settings,
            )
        else:
            r = _try_text_to_video(
                video_model_id,
                prompts,
                out_dir,
                fps=fps,
                seconds=seconds_per_clip,
                cuda_device_index=cuda_device_index,
                inference_settings=inference_settings,
            )
        if not r:
            raise RuntimeError(
                f"Video model {video_model_id!r} produced no clips. "
                "Check the Model tab, GPU/CUDA, and that the repo downloaded completely (e.g. unet/vae weights)."
            )
        dprint("clips", "generate_clips done", f"count={len(r)}")
        return r

