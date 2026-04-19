from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.core.config import AppSettings
from src.runtime.model_backend import api_preflight_errors, is_api_mode
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
    if is_api_mode(settings):
        errors.extend(api_preflight_errors(settings))
    if v.width <= 0 or v.height <= 0:
        errors.append(f"Invalid resolution: {v.width}×{v.height}.")
    if not (1 <= int(v.fps) <= 120):
        errors.append(f"Invalid FPS: {v.fps}.")
    pro_on = bool(getattr(v, "pro_mode", False))
    if pro_on and not is_api_mode(settings):
        # Pro mode is true text-to-video. Slideshow stitching must be OFF.
        if bool(getattr(v, "use_image_slideshow", True)):
            errors.append("Pro mode disables slideshow stitching — turn off 'Generate images and stitch (slideshow mode)'.")
        vid = str(getattr(settings, "video_model_id", "") or "").strip()
        if not vid:
            errors.append("Pro mode requires a Video (motion) model on the Model tab (e.g. ZeroScope for text-to-video Pro).")
        else:
            rl = vid.lower()
            if "stable-video-diffusion" in rl or "img2vid" in rl:
                errors.append(
                    "Pro mode currently supports text-to-video only. Stable Video Diffusion is image-to-video. "
                    "Choose ZeroScope in the Video slot, or turn off Pro."
                )
        pc = float(getattr(v, "pro_clip_seconds", 0) or 0)
        if pc <= 0:
            errors.append("Pro mode: scene length (seconds) must be > 0.")
        if v.clip_seconds <= 0 and not bool(getattr(v, "use_image_slideshow", True)):
            # Clip seconds isn't used by pro, but keep legacy sanity.
            pass
    elif pro_on and is_api_mode(settings):
        pc = float(getattr(v, "pro_clip_seconds", 0) or 0)
        if pc <= 0:
            errors.append("Pro mode: scene length (seconds) must be > 0.")
        if bool(getattr(v, "use_image_slideshow", True)):
            errors.append("API Pro mode: turn off slideshow — Pro uses cloud text-to-video clips.")
    elif v.use_image_slideshow:
        if v.images_per_video < 1:
            errors.append("Images per video must be >= 1 for slideshow mode.")
        if v.microclip_min_s <= 0 or v.microclip_max_s <= 0 or v.microclip_max_s < v.microclip_min_s:
            errors.append("Micro-scene min/max seconds must be > 0 and max >= min.")
    else:
        if not is_api_mode(settings):
            if v.clips_per_video < 1:
                errors.append("Scenes per video must be >= 1 for motion mode (slideshow off).")
            if v.clip_seconds <= 0:
                errors.append("Seconds per scene must be > 0 for motion mode (slideshow off).")

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
    if is_api_mode(settings):
        core_mods = [
            "requests",
            "bs4",
            "lxml",
            "numpy",
            "soundfile",
            "PIL",
            "moviepy",
            "huggingface_hub",
        ]
    else:
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
        # Video motion (scene) mode needs imageio writer in our implementation
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

