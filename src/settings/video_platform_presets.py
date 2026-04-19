"""
Curated social / platform templates for the Video settings tab.

Each preset sets resolution (width × height), timing, and export-related fields
to sensible defaults for that use case. Users can still tweak controls afterward
(which switches the template row to Custom).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformPreset:
    id: str
    #: Short label for the template dropdown
    title: str
    #: Platforms / use cases (subtitle)
    platforms: str
    width: int
    height: int
    fps: int
    microclip_min_s: float
    microclip_max_s: float
    images_per_video: int
    bitrate_preset: str  # low | med | high
    clips_per_video: int
    clip_seconds: float
    #: Pro mode (slideshow): one diffusion frame per output frame; clip_seconds above is for non-pro clip mode only
    pro_mode: bool = False
    pro_clip_seconds: float = 4.0


# Order: short-form vertical → square / portrait → landscape
PLATFORM_PRESETS: tuple[PlatformPreset, ...] = (
    PlatformPreset(
        id="shortform_vertical_1080",
        title="Short-form vertical (full HD)",
        platforms="TikTok · Reels · Shorts · Facebook Reels · Snapchat · X/Threads vertical",
        width=1080,
        height=1920,
        fps=30,
        microclip_min_s=3.0,
        microclip_max_s=6.0,
        images_per_video=8,
        bitrate_preset="med",
        clips_per_video=3,
        clip_seconds=4.0,
    ),
    PlatformPreset(
        id="shortform_vertical_720",
        title="Short-form vertical (720p)",
        platforms="Same as above — lighter file size / faster export",
        width=720,
        height=1280,
        fps=30,
        microclip_min_s=3.0,
        microclip_max_s=5.5,
        images_per_video=6,
        bitrate_preset="low",
        clips_per_video=3,
        clip_seconds=3.5,
    ),
    PlatformPreset(
        id="instagram_facebook_square",
        title="Instagram / Facebook square",
        platforms="Feed posts · carousel video · 1:1",
        width=1080,
        height=1080,
        fps=30,
        microclip_min_s=4.0,
        microclip_max_s=7.0,
        images_per_video=7,
        bitrate_preset="med",
        clips_per_video=3,
        clip_seconds=4.0,
    ),
    PlatformPreset(
        id="instagram_facebook_portrait",
        title="Instagram / Facebook portrait (4:5)",
        platforms="Feed · in-stream ads",
        width=1080,
        height=1350,
        fps=30,
        microclip_min_s=4.0,
        microclip_max_s=7.0,
        images_per_video=7,
        bitrate_preset="med",
        clips_per_video=3,
        clip_seconds=4.0,
    ),
    PlatformPreset(
        id="pinterest_pin",
        title="Pinterest standard pin",
        platforms="Idea Pins · tall 2:3",
        width=1000,
        height=1500,
        fps=30,
        microclip_min_s=4.0,
        microclip_max_s=8.0,
        images_per_video=8,
        bitrate_preset="med",
        clips_per_video=3,
        clip_seconds=5.0,
    ),
    PlatformPreset(
        id="landscape_1080p",
        title="Landscape 1080p (16:9)",
        platforms="YouTube · LinkedIn · Facebook in-stream · X landscape",
        width=1920,
        height=1080,
        fps=30,
        microclip_min_s=4.0,
        microclip_max_s=8.0,
        images_per_video=8,
        bitrate_preset="high",
        clips_per_video=4,
        clip_seconds=5.0,
    ),
    PlatformPreset(
        id="landscape_720p",
        title="Landscape 720p (16:9)",
        platforms="X · embedded web · faster uploads",
        width=1280,
        height=720,
        fps=30,
        microclip_min_s=4.0,
        microclip_max_s=7.5,
        images_per_video=7,
        bitrate_preset="med",
        clips_per_video=3,
        clip_seconds=4.0,
    ),
    PlatformPreset(
        id="pro_shortform_60fps",
        title="Pro — vertical 60 fps",
        platforms="Frame-accurate diffusion (one gen frame per video frame) · very GPU/time heavy",
        width=1080,
        height=1920,
        fps=60,
        microclip_min_s=3.0,
        microclip_max_s=6.0,
        images_per_video=8,
        bitrate_preset="high",
        clips_per_video=3,
        clip_seconds=4.0,
        pro_mode=True,
        pro_clip_seconds=4.0,
    ),
)


def preset_by_id(preset_id: str) -> PlatformPreset | None:
    pid = str(preset_id or "").strip()
    if not pid:
        return None
    for p in PLATFORM_PRESETS:
        if p.id == pid:
            return p
    return None


# All (width, height) pairs presets use — for populating the resolution dropdown
# Labels for the resolution dropdown (one row per distinct size used by templates)
_RESOLUTION_ROWS: tuple[tuple[str, int, int], ...] = (
    ("Vertical 9:16 — 1080×1920", 1080, 1920),
    ("Vertical 9:16 — 720×1280", 720, 1280),
    ("Square 1:1 — 1080×1080", 1080, 1080),
    ("Portrait 4:5 — 1080×1350", 1080, 1350),
    ("Tall 2:3 — 1000×1500 (Pinterest)", 1000, 1500),
    ("Landscape 16:9 — 1920×1080", 1920, 1080),
    ("Landscape 16:9 — 1280×720", 1280, 720),
)


def distinct_resolutions() -> list[tuple[str, int, int]]:
    """Friendly labels + dimensions for the Video format combo (deduped by size)."""
    seen: set[tuple[int, int]] = set()
    rows: list[tuple[str, int, int]] = []
    for label, w, h in _RESOLUTION_ROWS:
        key = (w, h)
        if key in seen:
            continue
        seen.add(key)
        rows.append((label, w, h))
    return rows


def find_best_preset_for_video(
    *,
    width: int,
    height: int,
    fps: int,
    microclip_min_s: float,
    microclip_max_s: float,
    images_per_video: int,
    bitrate_preset: str,
    clips_per_video: int,
    clip_seconds: float,
    pro_mode: bool = False,
    pro_clip_seconds: float = 4.0,
) -> str:
    """
    If current numeric settings match a template closely, return its id; else "".
    Used to restore the template dropdown when loading settings.
    """
    for p in PLATFORM_PRESETS:
        if p.width != width or p.height != height:
            continue
        if p.fps != fps:
            continue
        if abs(p.microclip_min_s - microclip_min_s) > 0.51:
            continue
        if abs(p.microclip_max_s - microclip_max_s) > 0.51:
            continue
        if p.images_per_video != images_per_video:
            continue
        if str(p.bitrate_preset) != str(bitrate_preset):
            continue
        if p.clips_per_video != clips_per_video:
            continue
        if abs(p.clip_seconds - clip_seconds) > 0.51:
            continue
        if bool(getattr(p, "pro_mode", False)) != bool(pro_mode):
            continue
        if pro_mode and abs(float(getattr(p, "pro_clip_seconds", 4.0)) - float(pro_clip_seconds)) > 0.51:
            continue
        return p.id
    return ""
