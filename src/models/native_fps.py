"""
Native frame-rate registry per text-to-video / image-to-video model.

Why this exists
---------------
Every diffusers T2V model is trained with a target playback FPS that can differ
from the user's preferred export FPS (often 30). The pipeline used to encode
all clips at the user FPS, which stretched a CogVideoX 17-frame clip across
~0.57 seconds at 30 fps and produced "flashing slideshow" output.

Encoding at the model's native fps preserves the trained motion timing; the
upstream stitcher and (optionally) the temporal-smoothing pass in
``src/render/temporal_smooth.py`` align audio and re-time to the user FPS.

Sources
-------
- CogVideoX-5b: 8 fps (model card / diffusers example)
- Wan 2.x: 16 fps native at 480p; 24 fps at 720p (use 16 for the safe default)
- Mochi 1.x: 30 fps
- LTX-Video / LTX-2: 24 fps (already honored by ``frame_rate`` kwarg)
- HunyuanVideo: 24 fps
- ZeroScope / ModelScope and unknown ids: ``None`` (caller uses the user fps).

Override: set ``AQUADUCT_NATIVE_FPS_OVERRIDE_<KEY>`` where ``<KEY>`` is the
upper-snake-case form of the repo id (e.g. ``THUDM__COGVIDEOX_5B``) to a
positive integer.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


def _norm_repo(model_id: str | None) -> str:
    return (model_id or "").strip().lower()


def _env_override_key(model_id: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9]+", "_", (model_id or "").strip()).strip("_").upper()
    return f"AQUADUCT_NATIVE_FPS_OVERRIDE_{raw}" if raw else ""


def _env_override(model_id: str) -> int | None:
    key = _env_override_key(model_id)
    if not key:
        return None
    raw = os.environ.get(key, "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def native_fps_for(model_id: str | None) -> int | None:
    """Return the model's intended playback fps, or ``None`` if unknown.

    ``None`` means "the caller's user/export fps is fine"; callers should
    fall back to the user fps in that case.
    """
    ov = _env_override(model_id or "")
    if ov:
        return ov

    mid = _norm_repo(model_id)
    if not mid:
        return None
    if "cogvideox" in mid:
        return 8
    if "wan-ai" in mid or "wan2" in mid:
        return 16
    if "mochi" in mid:
        return 30
    if "ltx-2" in mid or "ltx-video" in mid or "lightricks/ltx" in mid:
        return 24
    if "hunyuanvideo" in mid:
        return 24
    return None


def encoded_fps_for(model_id: str | None, *, user_fps: int, frame_rate_kw: float | int | None = None) -> int:
    """Resolve the actual fps used when writing the model's clip mp4.

    Precedence: explicit pipeline kwarg ``frame_rate`` (e.g. LTX-2) >
    native registry > user fps.
    """
    if frame_rate_kw is not None:
        try:
            f = int(round(float(frame_rate_kw)))
            if f > 0:
                return f
        except (TypeError, ValueError):
            pass
    nat = native_fps_for(model_id)
    if nat:
        return int(nat)
    return max(1, int(user_fps))


def clip_meta_path(out_path: Path) -> Path:
    """Sidecar metadata file path for a clip mp4."""
    out = Path(out_path)
    return out.with_suffix(out.suffix + ".meta.json") if out.suffix else out.parent / f"{out.name}.meta.json"


def write_clip_meta(
    out_path: Path,
    *,
    model_id: str | None,
    encoded_fps: int,
    num_frames: int,
    user_fps: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a per-clip JSON sidecar with reliable timing info.

    duration_s is what the editor / audio aligner should trust.
    """
    nf = max(1, int(num_frames))
    ef = max(1, int(encoded_fps))
    payload: dict[str, Any] = {
        "model_id": str(model_id or ""),
        "encoded_fps": ef,
        "num_frames": nf,
        "duration_s": round(nf / ef, 6),
        "native_fps": native_fps_for(model_id),
        "user_fps": int(user_fps) if user_fps is not None else None,
    }
    if extra:
        for k, v in extra.items():
            payload.setdefault(k, v)
    p = clip_meta_path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def read_clip_meta(out_path: Path) -> dict[str, Any] | None:
    """Read the sidecar metadata; return ``None`` if absent or malformed."""
    p = clip_meta_path(out_path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def clip_duration_seconds(out_path: Path, *, fallback: float | None = None) -> float | None:
    """Best-known duration for a clip: sidecar first, then None."""
    meta = read_clip_meta(out_path)
    if meta is not None:
        d = meta.get("duration_s")
        try:
            v = float(d) if d is not None else None
            if v is not None and v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return fallback
