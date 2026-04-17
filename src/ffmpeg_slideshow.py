from __future__ import annotations

import subprocess
from pathlib import Path

from .utils_ffmpeg import ensure_ffmpeg

# Subset of names supported by FFmpeg `xfade` (varies slightly by build; unknown → fade).
XFADE_TRANSITIONS: tuple[str, ...] = (
    "fade",
    "dissolve",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "radial",
    "smoothleft",
    "smoothright",
    "circlecrop",
    "vertopen",
    "horzopen",
    "diagtl",
    "diagtr",
    "hlslice",
    "hrslice",
)


def sanitize_xfade_transition(name: str | None) -> str:
    t = (name or "fade").strip().lower()
    return t if t in XFADE_TRANSITIONS else "fade"


def build_motion_slideshow(
    *,
    ffmpeg_dir: Path,
    images: list[Path],
    durations: list[float],
    out_mp4: Path,
    width: int,
    height: int,
    fps: int,
    transition_strength: str = "low",
    xfade_transition: str = "fade",
) -> Path:
    """
    Build a motion slideshow with FFmpeg zoompan and optional xfade.
    Returns out_mp4 path.
    """
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = ensure_ffmpeg(ffmpeg_dir)

    imgs = [p for p in images if p and Path(p).exists()]
    if not imgs:
        raise ValueError("No images for slideshow.")
    durs = [max(0.25, float(d)) for d in (durations or [])][: len(imgs)]
    if len(durs) < len(imgs):
        durs += [durs[-1] if durs else 3.0] * (len(imgs) - len(durs))

    xfade_dur = 0.0
    if transition_strength == "med":
        xfade_dur = 0.35
    elif transition_strength == "low":
        xfade_dur = 0.22

    xfn = sanitize_xfade_transition(xfade_transition)

    # Inputs: each image as looped input for its duration (+ transition overlap).
    cmd = [str(ffmpeg), "-y"]
    for p, d in zip(imgs, durs):
        loop_d = d + (xfade_dur if xfade_dur > 0 else 0.0)
        cmd += ["-loop", "1", "-t", f"{loop_d:.3f}", "-i", str(p)]

    # Filter per input: scale/crop to target, then zoompan to create motion.
    # Then chain xfade between adjacent streams.
    fc_parts = []
    for i, d in enumerate(durs):
        frames = int(round((d + (xfade_dur if xfade_dur > 0 else 0.0)) * fps))
        # subtle zoom
        fc_parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='min(zoom+0.0008,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}[v{i}]"
        )

    if len(imgs) == 1:
        fc_parts.append("[v0]format=yuv420p[vout]")
    else:
        # Chain xfade
        cur = "v0"
        offset = durs[0]
        for i in range(1, len(imgs)):
            if xfade_dur > 0:
                off = max(0.0, offset - xfade_dur)
                fc_parts.append(
                    f"[{cur}][v{i}]xfade=transition={xfn}:duration={xfade_dur:.3f}:offset={off:.3f}[x{i}]"
                )
                cur = f"x{i}"
            else:
                fc_parts.append(f"[{cur}][v{i}]concat=n=2:v=1:a=0[vcat{i}]")
                cur = f"vcat{i}"
            offset += durs[i]
        fc_parts.append(f"[{cur}]format=yuv420p[vout]")

    filter_complex = ";".join(fc_parts)
    cmd += ["-filter_complex", filter_complex, "-map", "[vout]", "-r", str(int(fps)), "-pix_fmt", "yuv420p", str(out_mp4)]

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_mp4

