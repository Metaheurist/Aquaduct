from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.core.config import AppSettings
from src.render.utils_ffmpeg import find_ffmpeg
from debug import dprint


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def _check_imports(mods: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for m in mods:
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    return missing


def preflight_check(*, settings: AppSettings, strict: bool = True) -> PreflightResult:
    """
    Validates environment + settings before starting a run.

    If strict=True, any missing requirement returns ok=False (caller should not run).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Settings sanity
    v = settings.video
    if v.width <= 0 or v.height <= 0:
        errors.append(f"Invalid resolution: {v.width}×{v.height}.")
    if not (1 <= int(v.fps) <= 120):
        errors.append(f"Invalid FPS: {v.fps}.")
    if v.use_image_slideshow:
        pro_on = bool(getattr(v, "pro_mode", False))
        if pro_on:
            vid = str(getattr(settings, "video_model_id", "") or "").strip()
            if not vid:
                errors.append(
                    "Pro mode requires a Video (motion) model on the Model tab (e.g. ZeroScope for text-to-video Pro)."
                )
            else:
                rl = vid.lower()
                if "stable-video-diffusion" in rl or "img2vid" in rl:
                    errors.append(
                        "Pro mode cannot use Stable Video Diffusion (image-to-video). "
                        "Choose ZeroScope in the Video slot, or turn off Pro."
                    )
            pc = float(getattr(v, "pro_clip_seconds", 0) or 0)
            if pc <= 0:
                errors.append("Pro mode: clip length (seconds) must be > 0.")
            else:
                try:
                    from src.render.editor import pro_mode_frame_count

                    nf = pro_mode_frame_count(pro_clip_seconds=pc, fps=int(v.fps))
                    if nf > 600:
                        warnings.append(
                            f"Pro mode will generate {nf} diffusion frames — expect very long runtimes and high VRAM use "
                            "(lower FPS or clip length, or set AQUADUCT_PRO_MAX_FRAMES)."
                        )
                    elif nf > 300:
                        warnings.append(
                            f"Pro mode will generate {nf} frames — this can take a long time on consumer GPUs."
                        )
                except Exception:
                    pass
        elif v.images_per_video < 1:
            errors.append("Images per video must be >= 1 for slideshow mode.")
        if v.microclip_min_s <= 0 or v.microclip_max_s <= 0 or v.microclip_max_s < v.microclip_min_s:
            errors.append("Micro-clip min/max seconds must be > 0 and max >= min.")
    elif bool(getattr(v, "pro_mode", False)):
        errors.append("Pro mode requires 'Generate images and stitch (slideshow mode)' to be enabled.")
    else:
        if v.clips_per_video < 1:
            errors.append("Clips per video must be >= 1 for clip mode.")
        if v.clip_seconds <= 0:
            errors.append("Seconds per clip must be > 0 for clip mode.")

    # Branding watermark sanity (optional)
    try:
        b = getattr(settings, "branding", None)
        if b and bool(getattr(b, "watermark_enabled", False)):
            p = str(getattr(b, "watermark_path", "") or "").strip()
            if not p:
                errors.append("Watermark is enabled but no logo file is selected.")
            else:
                from pathlib import Path

                wp = Path(p)
                if not wp.exists() or not wp.is_file():
                    errors.append(f"Watermark logo file not found: {p}")
    except Exception:
        pass

    # Python deps required to run end-to-end
    core_mods = [
        "requests",
        "bs4",
        "lxml",
        "numpy",
        "soundfile",
        "PIL",
        "moviepy",
        "huggingface_hub",
        "torch",
        "transformers",
        "accelerate",
        "diffusers",
    ]
    # Video clip mode needs imageio writer in our implementation
    if not v.use_image_slideshow:
        core_mods.append("imageio")

    missing = _check_imports(core_mods)
    if missing:
        errors.append("Missing Python packages: " + ", ".join(missing))

    # FFmpeg must be present. (We do NOT auto-download during preflight to avoid hanging the UI.)
    try:
        from src.core.config import get_paths

        paths = get_paths()
        if not find_ffmpeg(paths.ffmpeg_dir):
            errors.append(
                "FFmpeg is not under .Aquaduct_data/.cache/ffmpeg yet. In the desktop app, click Run once — it downloads in the "
                "background on first launch (internet required). CLI: the next `python main.py --once` downloads it "
                "before the pipeline starts. Or install FFmpeg yourself and ensure ffmpeg.exe is discoverable."
            )
    except Exception as e:
        errors.append(f"FFmpeg not available: {e}")

    # HF token isn't strictly required, but downloads can be rate-limited
    import os

    if not os.environ.get("HF_TOKEN") and not os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
        warnings.append("No HF_TOKEN set (downloads may be slower / rate-limited).")

    if strict:
        result = PreflightResult(ok=(len(errors) == 0), errors=errors, warnings=warnings)
        dprint("preflight", f"strict ok={result.ok}", f"errors={len(result.errors)}", f"warnings={len(result.warnings)}")
        return result

    # Non-strict mode: downgrade errors into warnings (best-effort runs)
    if errors:
        warnings.extend(errors)
        errors = []
    result = PreflightResult(ok=True, errors=errors, warnings=warnings)
    dprint("preflight", f"non-strict ok={result.ok}", f"warnings={len(result.warnings)}")
    return result

