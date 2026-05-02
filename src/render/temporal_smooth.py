"""Temporal smoothing for generated T2V/I2V clips (Phase 2).

Most local T2V models render at low native frame rates (CogVideoX ≈ 8 fps,
LTX-2 / Wan ≈ 16–24 fps), which can read as a "flashing slideshow" when
displayed back at common social-media frame rates (24/30 fps). Phase 1
fixed the encoded fps + audio alignment; this module adds an optional
*motion-aware* upsampling pass that re-encodes each clip to a higher fps
while preserving its real time duration:

- ``off``    -- no work done (default).
- ``ffmpeg`` -- ``minterpolate`` motion-compensated upsample. CPU-only,
  ships with our bundled ffmpeg, never pulls extra weights.
- ``rife``   -- ML interpolator (lazy import — see :func:`_rife_available`).
  Falls back to ``ffmpeg`` if the package or VRAM budget is unavailable.

Public API:

- :func:`smooth_clip` --- in-place smooth a single clip (returns the path
  that should be used downstream; falls back to the original on failure).
- :func:`smooth_clips` --- batch wrapper.
- :func:`rife_available` / :func:`rife_vram_budget_ok` --- preflight helpers
  used by ``src/runtime/preflight.py``.

The encoded fps comes from the model registry
(:func:`src.models.native_fps.native_fps_for`) when present, falling back
to the value recorded in the ``.mp4.meta.json`` sidecar; the duration is
preserved so audio alignment stays correct.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.models.native_fps import (
    clip_duration_seconds,
    native_fps_for,
    read_clip_meta,
    write_clip_meta,
)

log = logging.getLogger("aquaduct.temporal_smooth")

SmoothnessMode = Literal["off", "ffmpeg", "rife"]

#: Hard ceiling so a misconfigured preset can never explode the encoded fps.
TARGET_FPS_MAX = 60
TARGET_FPS_MIN = 12
#: Estimated peak VRAM for the smallest mainstream RIFE checkpoint at 1080x1920.
RIFE_VRAM_BUDGET_MB = 1500


@dataclass(frozen=True)
class SmoothResult:
    """Outcome of a smoothing pass applied to a single clip."""

    output_path: Path
    mode_used: SmoothnessMode
    encoded_fps: int
    target_fps: int
    duration_s: float


def _resolve_encoded_fps(clip_path: Path, *, model_id: str | None) -> int:
    """Best-effort current encoded fps for *clip_path*.

    Order of precedence: sidecar metadata > native fps registry > 24 (sensible default).
    """
    meta = read_clip_meta(clip_path) or {}
    enc = meta.get("encoded_fps")
    if isinstance(enc, (int, float)) and enc > 0:
        return int(enc)
    nat = native_fps_for(model_id)
    if nat:
        return int(nat)
    return 24


def _resolve_target_fps(target_fps: int) -> int:
    return max(TARGET_FPS_MIN, min(TARGET_FPS_MAX, int(target_fps or 0) or 24))


def _ffmpeg_minterpolate(
    src: Path,
    dst: Path,
    *,
    target_fps: int,
    ffmpeg_exe: Path | str = "ffmpeg",
) -> bool:
    """Run ``minterpolate`` to upsample *src* to *target_fps*. Returns ``True`` on success."""
    cmd = [
        str(ffmpeg_exe),
        "-y",
        "-loglevel", "error",
        "-i", str(src),
        "-vf", f"minterpolate=fps={int(target_fps)}:mi_mode=mci:mc_mode=aobmc:vsbmf=1",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-an",
        str(dst),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        log.warning("ffmpeg not found for smoothing: %s", exc)
        return False
    if proc.returncode != 0:
        log.warning(
            "ffmpeg minterpolate failed (rc=%s): %s",
            proc.returncode,
            (proc.stderr or "").strip().splitlines()[-1:],
        )
        return False
    return dst.is_file() and dst.stat().st_size > 0


def rife_available() -> bool:
    """``True`` when an installed RIFE/FILM-style interpolator can be imported.

    Imports are lazy (no module top-level deps) so absence is not a hard error.
    """
    try:
        import importlib

        importlib.import_module("rife_ncnn_vulkan_python")
        return True
    except Exception:
        pass
    try:
        import importlib

        importlib.import_module("rife")
        return True
    except Exception:
        return False


def rife_vram_budget_ok(*, free_vram_mb: int | None) -> bool:
    """``True`` if there's enough free VRAM headroom to run RIFE.

    Conservatively we want at least :data:`RIFE_VRAM_BUDGET_MB` MB free so the
    diffusion pipeline weights aren't crowded out. ``None`` (CPU-only run)
    returns ``False`` so the caller falls back to ffmpeg.
    """
    if free_vram_mb is None:
        return False
    return int(free_vram_mb) >= RIFE_VRAM_BUDGET_MB


def _resolve_mode(
    requested: SmoothnessMode,
    *,
    free_vram_mb: int | None,
) -> SmoothnessMode:
    """Map the user-requested mode onto what we can actually run.

    - ``off`` always returns ``off``.
    - ``ffmpeg`` always returns ``ffmpeg`` (the bundled binary is the only
      requirement and that's checked at run time).
    - ``rife`` returns ``rife`` only when both :func:`rife_available` and
      :func:`rife_vram_budget_ok` are true; otherwise it degrades to
      ``ffmpeg`` so the user still gets motion-interpolation.
    """
    req = (requested or "off").strip().lower()
    if req not in ("off", "ffmpeg", "rife"):
        return "off"
    if req == "off":
        return "off"
    if req == "rife":
        if rife_available() and rife_vram_budget_ok(free_vram_mb=free_vram_mb):
            return "rife"
        log.info(
            "smoothness=rife requested but unavailable (rife_pkg=%s, vram_ok=%s); "
            "falling back to ffmpeg minterpolate",
            rife_available(),
            rife_vram_budget_ok(free_vram_mb=free_vram_mb),
        )
        return "ffmpeg"
    return "ffmpeg"


def _ffmpeg_exe() -> Path | str:
    """Best-effort ffmpeg executable location.

    Prefers the resolved binary set by ``configure_moviepy_ffmpeg`` (env
    ``FFMPEG_BINARY``); falls back to ``shutil.which("ffmpeg")``; finally the
    bare string ``"ffmpeg"`` so the subprocess call still works on PATH.
    """
    import os

    env = os.environ.get("FFMPEG_BINARY")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"


def smooth_clip(
    clip_path: Path,
    *,
    mode: SmoothnessMode,
    model_id: str | None,
    target_fps: int = 24,
    free_vram_mb: int | None = None,
    ffmpeg_exe: Path | str | None = None,
) -> SmoothResult:
    """Smooth a single clip in place; returns the path that should be used.

    On any failure or no-op, the returned ``output_path`` equals ``clip_path``
    (the original is preserved). The clip's ``.mp4.meta.json`` sidecar is
    rewritten with the new encoded fps so downstream alignment stays correct.

    Parameters
    ----------
    target_fps:
        Desired playback fps after smoothing; clamped to
        ``[TARGET_FPS_MIN, TARGET_FPS_MAX]``.
    free_vram_mb:
        Free VRAM budget on the active GPU; used only for the ``rife`` mode
        to decide whether to fall back to ffmpeg.
    """
    src = Path(clip_path)
    if not src.is_file():
        raise FileNotFoundError(src)

    enc_fps = _resolve_encoded_fps(src, model_id=model_id)
    tgt = _resolve_target_fps(target_fps)
    duration_s = clip_duration_seconds(src) or 0.0

    resolved = _resolve_mode(mode, free_vram_mb=free_vram_mb)
    if resolved == "off" or tgt <= enc_fps:
        return SmoothResult(
            output_path=src,
            mode_used="off",
            encoded_fps=enc_fps,
            target_fps=tgt,
            duration_s=float(duration_s),
        )

    tmp = src.with_suffix(".smooth.mp4")
    ok = False
    used: SmoothnessMode = resolved
    if resolved == "rife":
        try:
            ok = _rife_interpolate(src, tmp, target_fps=tgt)
        except Exception as exc:
            log.warning("RIFE smoothing failed (%s); falling back to ffmpeg", exc)
            ok = False
        if not ok:
            ok = _ffmpeg_minterpolate(src, tmp, target_fps=tgt, ffmpeg_exe=ffmpeg_exe or _ffmpeg_exe())
            used = "ffmpeg" if ok else "off"
    else:
        ok = _ffmpeg_minterpolate(src, tmp, target_fps=tgt, ffmpeg_exe=ffmpeg_exe or _ffmpeg_exe())
        used = "ffmpeg" if ok else "off"

    if not ok:
        try:
            if tmp.is_file():
                tmp.unlink()
        except Exception:
            pass
        return SmoothResult(
            output_path=src,
            mode_used="off",
            encoded_fps=enc_fps,
            target_fps=tgt,
            duration_s=float(duration_s),
        )

    backup = src.with_suffix(".pre_smooth.mp4")
    try:
        if backup.exists():
            backup.unlink()
        src.replace(backup)
        tmp.replace(src)
    except OSError as exc:
        log.warning("failed to replace original clip with smoothed version (%s)", exc)
        try:
            if tmp.is_file():
                tmp.unlink()
        except Exception:
            pass
        return SmoothResult(
            output_path=src,
            mode_used="off",
            encoded_fps=enc_fps,
            target_fps=tgt,
            duration_s=float(duration_s),
        )

    new_duration = duration_s
    try:
        write_clip_meta(
            src,
            model_id=model_id,
            encoded_fps=tgt,
            user_fps=tgt,
            num_frames=max(1, int(round(new_duration * tgt))),
        )
    except Exception:
        pass
    try:
        if backup.is_file():
            backup.unlink()
    except Exception:
        pass

    return SmoothResult(
        output_path=src,
        mode_used=used,
        encoded_fps=tgt,
        target_fps=tgt,
        duration_s=float(new_duration),
    )


def smooth_clips(
    clip_paths: list[Path],
    *,
    mode: SmoothnessMode,
    model_id: str | None,
    target_fps: int = 24,
    free_vram_mb: int | None = None,
    ffmpeg_exe: Path | str | None = None,
) -> list[SmoothResult]:
    """Apply :func:`smooth_clip` to every clip; never raises on per-clip errors."""
    out: list[SmoothResult] = []
    for p in clip_paths:
        try:
            r = smooth_clip(
                p,
                mode=mode,
                model_id=model_id,
                target_fps=target_fps,
                free_vram_mb=free_vram_mb,
                ffmpeg_exe=ffmpeg_exe,
            )
        except Exception as exc:
            log.warning("smoothing %s failed: %s", p, exc)
            r = SmoothResult(
                output_path=Path(p),
                mode_used="off",
                encoded_fps=_resolve_encoded_fps(Path(p), model_id=model_id),
                target_fps=_resolve_target_fps(target_fps),
                duration_s=float(clip_duration_seconds(Path(p)) or 0.0),
            )
        out.append(r)
    return out


def _rife_interpolate(src: Path, dst: Path, *, target_fps: int) -> bool:  # pragma: no cover
    """Lazy stub for the optional RIFE interpolator.

    Real installations should monkey-patch / override this in their build, or
    install a maintained package such as ``rife_ncnn_vulkan_python``. In this
    repo we keep the dependency optional, so the function returns ``False``
    (which causes :func:`smooth_clip` to fall back to ffmpeg automatically).
    """
    log.info(
        "RIFE backend not wired in this build; falling back to ffmpeg "
        "(install rife_ncnn_vulkan_python and override _rife_interpolate to enable)."
    )
    return False
