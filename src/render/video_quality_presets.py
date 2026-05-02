"""Video tab v2 preset registry (Phase 5).

The legacy Video tab exposed five raw spinners (`clips_per_video`,
`pro_clip_seconds`, `fps`, `width`, `height`, plus the smoothness toggle
introduced in Phase 2). The trace from `Two_Sentenced_Horror_Stories`
showed users mismatching the values — e.g. picking 30 fps for a model
that natively encodes at 8 fps, which produced the "flashing slideshow"
look — so the v2 tab replaces them with **four named knobs** plus the
existing smoothness mode:

| Knob       | Choice key              | Drives                                     |
|------------|-------------------------|--------------------------------------------|
| Length     | `short` / `medium` / `long` | `clips_per_video`, `pro_clip_seconds`, T2V `length_factor` |
| Scene      | `punchy` / `balanced` / `cinematic` | per-scene length and prompt expansion |
| FPS        | `cinematic_24` / `standard_30` / `smooth_60` | output fps, `smoothness_target_fps` |
| Resolution | `vertical_1080p` / `vertical_720p` / `square_1080` | width, height |
| Smoothness | `off` / `ffmpeg` / `rife` | unchanged from Phase 2 |

The legacy spinners stay accessible behind an "Advanced" disclosure so
power users can still set arbitrary values (and so existing settings
files keep round-tripping). When a settings file has *no* preset id,
:func:`migrate_legacy_video_settings` picks the closest preset for each
knob from the existing values, so every install lands on a sane v2
default after one round-trip through `save_settings()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

LengthPresetId = Literal["short", "medium", "long"]
ScenePresetId = Literal["punchy", "balanced", "cinematic"]
FpsPresetId = Literal["cinematic_24", "standard_30", "smooth_60"]
ResolutionPresetId = Literal["vertical_1080p", "vertical_720p", "square_1080"]


@dataclass(frozen=True)
class LengthPreset:
    id: LengthPresetId
    label: str
    description: str
    clips_per_video: int
    pro_clip_seconds: float
    length_factor: float


@dataclass(frozen=True)
class ScenePreset:
    id: ScenePresetId
    label: str
    description: str
    target_clip_seconds: float
    expand_to_n_scenes: bool


@dataclass(frozen=True)
class FpsPreset:
    id: FpsPresetId
    label: str
    description: str
    fps: int
    smoothness_target_fps: int


@dataclass(frozen=True)
class ResolutionPreset:
    id: ResolutionPresetId
    label: str
    description: str
    width: int
    height: int


LENGTH_PRESETS: dict[LengthPresetId, LengthPreset] = {
    "short": LengthPreset(
        id="short",
        label="Short clip (~10–15 s)",
        description="Fewer scenes, snappier pacing — ideal for hooks and TikTok loops.",
        clips_per_video=3,
        pro_clip_seconds=4.0,
        length_factor=0.85,
    ),
    "medium": LengthPreset(
        id="medium",
        label="Medium clip (~25–35 s)",
        description="Balanced pacing for most short-form formats (default).",
        clips_per_video=5,
        pro_clip_seconds=5.0,
        length_factor=1.0,
    ),
    "long": LengthPreset(
        id="long",
        label="Long clip (~50–70 s)",
        description="More beats and longer scenes — best for cinematic horror or explainers.",
        clips_per_video=8,
        pro_clip_seconds=6.0,
        length_factor=1.25,
    ),
}


SCENE_PRESETS: dict[ScenePresetId, ScenePreset] = {
    "punchy": ScenePreset(
        id="punchy",
        label="Punchy scenes",
        description="Each scene ~3 s — many quick cuts.",
        target_clip_seconds=3.0,
        expand_to_n_scenes=True,
    ),
    "balanced": ScenePreset(
        id="balanced",
        label="Balanced scenes",
        description="Each scene ~5 s (default).",
        target_clip_seconds=5.0,
        expand_to_n_scenes=True,
    ),
    "cinematic": ScenePreset(
        id="cinematic",
        label="Cinematic scenes",
        description="Each scene ~7 s — fewer, longer beats.",
        target_clip_seconds=7.0,
        expand_to_n_scenes=False,
    ),
}


FPS_PRESETS: dict[FpsPresetId, FpsPreset] = {
    "cinematic_24": FpsPreset(
        id="cinematic_24",
        label="Cinematic 24 fps",
        description="Film-look pacing; pairs well with most local T2V models.",
        fps=24,
        smoothness_target_fps=24,
    ),
    "standard_30": FpsPreset(
        id="standard_30",
        label="Standard 30 fps",
        description="Default for short-form social platforms.",
        fps=30,
        smoothness_target_fps=30,
    ),
    "smooth_60": FpsPreset(
        id="smooth_60",
        label="Smooth 60 fps",
        description="High frame rate for talking-head clarity; needs Smoothness ≥ ffmpeg.",
        fps=60,
        smoothness_target_fps=60,
    ),
}


RESOLUTION_PRESETS: dict[ResolutionPresetId, ResolutionPreset] = {
    "vertical_1080p": ResolutionPreset(
        id="vertical_1080p",
        label="Vertical 1080×1920",
        description="Default 9:16 vertical for TikTok/Reels/Shorts.",
        width=1080,
        height=1920,
    ),
    "vertical_720p": ResolutionPreset(
        id="vertical_720p",
        label="Vertical 720×1280",
        description="Lighter render — useful for slow GPUs.",
        width=720,
        height=1280,
    ),
    "square_1080": ResolutionPreset(
        id="square_1080",
        label="Square 1080×1080",
        description="Square 1:1 — Instagram/X feed posts.",
        width=1080,
        height=1080,
    ),
}


DEFAULT_LENGTH: LengthPresetId = "medium"
DEFAULT_SCENE: ScenePresetId = "balanced"
DEFAULT_FPS: FpsPresetId = "standard_30"
DEFAULT_RESOLUTION: ResolutionPresetId = "vertical_1080p"


def length_preset(pid: str | None) -> LengthPreset:
    return LENGTH_PRESETS.get((pid or "").strip().lower(), LENGTH_PRESETS[DEFAULT_LENGTH])  # type: ignore[arg-type]


def scene_preset(pid: str | None) -> ScenePreset:
    return SCENE_PRESETS.get((pid or "").strip().lower(), SCENE_PRESETS[DEFAULT_SCENE])  # type: ignore[arg-type]


def fps_preset(pid: str | None) -> FpsPreset:
    return FPS_PRESETS.get((pid or "").strip().lower(), FPS_PRESETS[DEFAULT_FPS])  # type: ignore[arg-type]


def resolution_preset(pid: str | None) -> ResolutionPreset:
    return RESOLUTION_PRESETS.get((pid or "").strip().lower(), RESOLUTION_PRESETS[DEFAULT_RESOLUTION])  # type: ignore[arg-type]


def length_factor_for(settings: Any) -> float:
    """Read the length factor regardless of legacy / v2 settings shape."""
    pid = str(getattr(settings, "video_length_preset_id", "") or "").strip().lower()
    if pid in LENGTH_PRESETS:
        return LENGTH_PRESETS[pid].length_factor  # type: ignore[index]
    return 1.0


def apply_t2v_length_factor(kwargs: dict[str, Any], factor: float) -> dict[str, Any]:
    """Scale the T2V ``num_frames`` by *factor*, keeping LTX-2's ``8k+1`` invariant.

    Returns a new dict (does not mutate the input). Conservatively clamps the
    output to >= 8 frames so a misconfigured factor can't ask the pipeline for
    zero motion.
    """
    out = dict(kwargs)
    nf_raw = out.get("num_frames")
    try:
        nf = int(nf_raw) if nf_raw is not None else 0
    except (TypeError, ValueError):
        nf = 0
    if nf <= 0:
        return out
    scaled = max(8, int(round(nf * float(factor or 1.0))))
    if "frame_rate" in out and isinstance(out.get("frame_rate"), (int, float)):
        scaled = max(scaled, 8)
    out["num_frames"] = scaled
    return out


def migrate_legacy_video_settings(legacy: dict[str, Any]) -> dict[str, Any]:
    """Pick the closest v2 preset ids for an existing settings dict.

    Idempotent — when all four preset ids are already present (and valid),
    returns the input unchanged.
    """
    out = dict(legacy)

    if str(out.get("video_length_preset_id", "")).strip().lower() not in LENGTH_PRESETS:
        clips = int(out.get("clips_per_video", 5) or 5)
        secs = float(out.get("pro_clip_seconds", 5.0) or 5.0)
        total = clips * secs
        if total <= 18:
            out["video_length_preset_id"] = "short"
        elif total >= 45:
            out["video_length_preset_id"] = "long"
        else:
            out["video_length_preset_id"] = "medium"

    if str(out.get("video_scene_preset_id", "")).strip().lower() not in SCENE_PRESETS:
        secs = float(out.get("pro_clip_seconds", 5.0) or 5.0)
        if secs <= 4.0:
            out["video_scene_preset_id"] = "punchy"
        elif secs >= 6.5:
            out["video_scene_preset_id"] = "cinematic"
        else:
            out["video_scene_preset_id"] = "balanced"

    if str(out.get("video_fps_preset_id", "")).strip().lower() not in FPS_PRESETS:
        fps = int(out.get("fps", 30) or 30)
        if fps <= 26:
            out["video_fps_preset_id"] = "cinematic_24"
        elif fps >= 50:
            out["video_fps_preset_id"] = "smooth_60"
        else:
            out["video_fps_preset_id"] = "standard_30"

    if str(out.get("video_resolution_preset_id", "")).strip().lower() not in RESOLUTION_PRESETS:
        w = int(out.get("width", 1080) or 1080)
        h = int(out.get("height", 1920) or 1920)
        if w == h:
            out["video_resolution_preset_id"] = "square_1080"
        elif h <= 1300:
            out["video_resolution_preset_id"] = "vertical_720p"
        else:
            out["video_resolution_preset_id"] = "vertical_1080p"

    return out


def apply_video_presets(legacy: dict[str, Any]) -> dict[str, Any]:
    """Reconcile v2 preset ids back onto raw spinner values.

    When a preset id is set we *override* the matching raw value so the
    rest of the pipeline (which still reads `width`, `height`, `fps`, etc.)
    sees a coherent configuration. The legacy spinners remain editable from
    the Advanced disclosure -- doing so blanks the preset id, which makes
    this function a no-op for that field.
    """
    out = dict(legacy)
    lp_id = str(out.get("video_length_preset_id", "") or "").strip().lower()
    if lp_id in LENGTH_PRESETS:
        lp = LENGTH_PRESETS[lp_id]  # type: ignore[index]
        out["clips_per_video"] = int(lp.clips_per_video)
        out["pro_clip_seconds"] = float(lp.pro_clip_seconds)
    sp_id = str(out.get("video_scene_preset_id", "") or "").strip().lower()
    if sp_id in SCENE_PRESETS:
        sp = SCENE_PRESETS[sp_id]  # type: ignore[index]
        out.setdefault("pro_clip_seconds", float(sp.target_clip_seconds))
    fp_id = str(out.get("video_fps_preset_id", "") or "").strip().lower()
    if fp_id in FPS_PRESETS:
        fp = FPS_PRESETS[fp_id]  # type: ignore[index]
        out["fps"] = int(fp.fps)
        out["smoothness_target_fps"] = int(fp.smoothness_target_fps)
    rp_id = str(out.get("video_resolution_preset_id", "") or "").strip().lower()
    if rp_id in RESOLUTION_PRESETS:
        rp = RESOLUTION_PRESETS[rp_id]  # type: ignore[index]
        out["width"] = int(rp.width)
        out["height"] = int(rp.height)
    return out
