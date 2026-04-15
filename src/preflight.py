from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import AppSettings
from .utils_ffmpeg import find_ffmpeg


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
        if v.images_per_video < 1:
            errors.append("Images per video must be >= 1 for slideshow mode.")
        if v.microclip_min_s <= 0 or v.microclip_max_s <= 0 or v.microclip_max_s < v.microclip_min_s:
            errors.append("Micro-clip min/max seconds must be > 0 and max >= min.")
    else:
        if v.clips_per_video < 1:
            errors.append("Clips per video must be >= 1 for clip mode.")
        if v.clip_seconds <= 0:
            errors.append("Seconds per clip must be > 0 for clip mode.")

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
        from .config import get_paths

        paths = get_paths()
        if not find_ffmpeg(paths.ffmpeg_dir):
            errors.append(
                "FFmpeg is not installed yet. Run once to auto-download it (or open the app with internet) and try again."
            )
    except Exception as e:
        errors.append(f"FFmpeg not available: {e}")

    # HF token isn't strictly required, but downloads can be rate-limited
    import os

    if not os.environ.get("HF_TOKEN") and not os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
        warnings.append("No HF_TOKEN set (downloads may be slower / rate-limited).")

    if strict:
        return PreflightResult(ok=(len(errors) == 0), errors=errors, warnings=warnings)

    # Non-strict mode: downgrade errors into warnings (best-effort runs)
    if errors:
        warnings.extend(errors)
        errors = []
    return PreflightResult(ok=True, errors=errors, warnings=warnings)

