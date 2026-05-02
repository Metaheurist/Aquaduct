"""
Ephemeral downgrade steps when quantization cannot go lower — shrink diffusion resolution / frames.

Values live on ``AppSettings.resource_retry_*`` and are stripped by ``save_settings``.
"""

from __future__ import annotations

from dataclasses import replace

from src.core.config import AppSettings

from src.models.quantization import QuantRole


_RS_MULT = 0.75  # geometry shrink per notch
_FM_MULT = 0.5   # frame count multiplier per notch
_MIN_EDGE = 256
_MIN_FRAMES = 9


def _norm_role(role: QuantRole | str) -> str:
    return str(role or "").strip().lower()


def downgrade_resolution_step(settings: AppSettings, *, role: QuantRole | str) -> AppSettings | None:
    """Return settings with smaller ``resource_retry_resolution_scale``, or ``None`` if exhausted."""
    r = _norm_role(role)
    if r not in ("image", "video"):
        return None
    cur = float(getattr(settings, "resource_retry_resolution_scale", 1.0) or 1.0)
    if cur * _RS_MULT < 0.395:  # ~0.75^4 floor
        return None
    return replace(settings, resource_retry_resolution_scale=cur * _RS_MULT)


def downgrade_frames_step(settings: AppSettings, *, role: QuantRole | str) -> AppSettings | None:
    if _norm_role(role) != "video":
        return None
    cur = float(getattr(settings, "resource_retry_frames_scale", 1.0) or 1.0)
    if cur * _FM_MULT < 0.249:  # 0.5^2 floor-ish
        return None
    return replace(settings, resource_retry_frames_scale=cur * _FM_MULT)


def apply_inference_profile_scales(kwargs: dict, settings: AppSettings) -> dict:
    """Clamp width/height/num_frames in diffusers kwargs according to ephemeral scales."""
    out = dict(kwargs)
    rs = float(getattr(settings, "resource_retry_resolution_scale", 1.0) or 1.0)
    fs = float(getattr(settings, "resource_retry_frames_scale", 1.0) or 1.0)
    if rs < 0.999:
        try:
            w = int(out.get("width", 512) or 512)
            h = int(out.get("height", 512) or 512)
            nw = max(_MIN_EDGE, int(round(w * rs)))
            nh = max(_MIN_EDGE, int(round(h * rs)))
            out["width"] = nw - (nw % 8)
            out["height"] = nh - (nh % 8)
        except Exception:
            pass
    if fs < 0.999 and "num_frames" in out:
        try:
            nf = max(_MIN_FRAMES, int(round(int(out["num_frames"] or _MIN_FRAMES) * fs)))
            # WAN-style alignment: prefer (nf - 1) % 8 == 0 without ballooning endlessly.
            while (nf - 1) % 8 != 0 and nf < 1000:
                nf -= 1
            out["num_frames"] = max(_MIN_FRAMES, nf)
        except Exception:
            pass
    return out
