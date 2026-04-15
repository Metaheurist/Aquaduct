from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

from .config import BrandingSettings, VideoSettings
from .utils_ffmpeg import configure_moviepy_ffmpeg, ensure_ffmpeg


@dataclass(frozen=True)
class CaptionWord:
    word: str
    start: float
    end: float


def _load_captions(captions_json: Path) -> list[CaptionWord]:
    data = json.loads(captions_json.read_text(encoding="utf-8"))
    out: list[CaptionWord] = []
    if isinstance(data, list):
        for w in data:
            if not isinstance(w, dict):
                continue
            word = str(w.get("word", "")).strip()
            try:
                start = float(w.get("start", 0.0))
                end = float(w.get("end", 0.0))
            except Exception:
                continue
            if word and end > start:
                out.append(CaptionWord(word=word, start=start, end=end))
    return out


def _fit_crop_9x16(img_w: int, img_h: int, out_w: int, out_h: int) -> tuple[int, int, int, int]:
    """
    Returns crop box (left, top, right, bottom) for a center-crop to out_w/out_h aspect.
    """
    target = out_w / out_h
    cur = img_w / img_h
    if cur > target:
        # too wide, crop width
        new_w = int(img_h * target)
        left = (img_w - new_w) // 2
        return left, 0, left + new_w, img_h
    else:
        # too tall, crop height
        new_h = int(img_w / target)
        top = (img_h - new_h) // 2
        return 0, top, img_w, top + new_h


def _caption_frame(
    *,
    words: list[str],
    active_idx: int,
    w: int,
    h: int,
) -> np.ndarray:
    """
    Renders a transparent RGBA caption frame with current word highlighted.
    """
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", 54)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 54)
        except Exception:
            font = ImageFont.load_default()

    text = " ".join(words)
    # Simple wrapping: split into 2 lines if too long
    if len(text) > 38:
        mid = max(1, len(words) // 2)
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        lines = [line1, line2]
    else:
        lines = [text]

    y = int(h * 0.70)
    for li, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (w - tw) // 2
        yy = y + li * (th + 10)
        # stroke for readability
        draw.text((x, yy), line, font=font, fill=(255, 255, 255, 235), stroke_width=6, stroke_fill=(0, 0, 0, 220))

    # Active word highlight (best-effort): draw a glow bar behind active word on first line
    if words and 0 <= active_idx < len(words):
        # Approximate: highlight center area
        bar_y = y - 18
        bar_h = 70
        draw.rounded_rectangle(
            [int(w * 0.10), bar_y, int(w * 0.90), bar_y + bar_h],
            radius=24,
            fill=(0, 255, 200, 45),
            outline=(0, 255, 200, 65),
            width=2,
        )
    return np.array(img)


def _watermark_position_xy(*, pos: str, w: int, h: int, wm_w: int, wm_h: int) -> tuple[int, int]:
    pad_x = int(w * 0.03)
    pad_y = int(h * 0.03)
    pos = (pos or "").strip().lower()
    if pos == "top_left":
        return pad_x, pad_y
    if pos == "top_right":
        return max(pad_x, w - wm_w - pad_x), pad_y
    if pos == "bottom_left":
        return pad_x, max(pad_y, h - wm_h - pad_y)
    if pos == "bottom_right":
        return max(pad_x, w - wm_w - pad_x), max(pad_y, h - wm_h - pad_y)
    # center
    return max(0, (w - wm_w) // 2), max(0, (h - wm_h) // 2)


def _make_watermark_clip(
    *,
    branding: BrandingSettings | None,
    out_w: int,
    out_h: int,
    duration: float,
) -> ImageClip | None:
    if not branding or not getattr(branding, "watermark_enabled", False):
        return None
    p = Path(str(getattr(branding, "watermark_path", "") or "").strip())
    if not p.exists() or not p.is_file():
        return None
    try:
        opacity = float(getattr(branding, "watermark_opacity", 0.22))
    except Exception:
        opacity = 0.22
    try:
        scale = float(getattr(branding, "watermark_scale", 0.18))
    except Exception:
        scale = 0.18
    scale = max(0.05, min(0.6, scale))
    opacity = max(0.05, min(1.0, opacity))
    pos = str(getattr(branding, "watermark_position", "top_right") or "top_right")

    wm = ImageClip(str(p)).set_duration(duration).set_opacity(opacity)
    target_w = max(24, int(out_w * scale))
    wm = wm.resize(width=target_w)
    x, y = _watermark_position_xy(pos=pos, w=out_w, h=out_h, wm_w=int(wm.w), wm_h=int(wm.h))
    wm = wm.set_position((x, y))
    return wm


def assemble_microclips_then_concat(
    *,
    ffmpeg_dir: Path,
    settings: VideoSettings,
    images: list[Path],
    voice_wav: Path,
    captions_json: Path,
    out_final_mp4: Path,
    out_assets_dir: Path,
    background_music: Path | None = None,
    branding: BrandingSettings | None = None,
) -> None:
    """
    Builds 9:16 final video as concatenation of few-second micro-clips (one per image/beat).
    Captioning is word-by-word using timestamps over the whole audio.
    """
    out_final_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_assets_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = ensure_ffmpeg(ffmpeg_dir)
    configure_moviepy_ffmpeg(ffmpeg_exe)

    audio = AudioFileClip(str(voice_wav)).volumex(settings.voice_volume)
    words = _load_captions(captions_json)

    total_dur = float(audio.duration)
    if total_dur <= 0.2:
        total_dur = 5.0

    # Decide clip count/durations
    imgs = images[:] if images else []
    if not imgs:
        raise ValueError("No images provided to editor.")

    clip_count = min(len(imgs), max(3, int(math.ceil(total_dur / settings.microclip_max_s))))
    imgs = imgs[:clip_count]

    # Evenly split the audio into `clip_count` chunks
    chunk = total_dur / clip_count
    clip_specs: list[tuple[float, float, Path]] = []
    for i in range(clip_count):
        start = i * chunk
        end = min(total_dur, (i + 1) * chunk)
        # Enforce min/max by borrowing from neighbors (simple clamp)
        dur = end - start
        if dur < settings.microclip_min_s:
            end = min(total_dur, start + settings.microclip_min_s)
        if (end - start) > settings.microclip_max_s:
            end = start + settings.microclip_max_s
        clip_specs.append((start, end, imgs[i]))

    clips = []
    bitrate_map = {"low": "3500k", "med": "6000k", "high": "9000k"}
    final_bitrate = bitrate_map.get(settings.bitrate_preset, "6000k")
    clip_bitrate = {"low": "2500k", "med": "4500k", "high": "6500k"}.get(settings.bitrate_preset, "4500k")
    for idx, (t0, t1, img_path) in enumerate(clip_specs, start=1):
        dur = max(0.25, t1 - t0)
        base = ImageClip(str(img_path)).set_duration(dur)

        # Crop to 9:16 and resize, add subtle zoom
        iw, ih = base.w, base.h
        l, t, r, b = _fit_crop_9x16(iw, ih, settings.width, settings.height)
        base = base.crop(x1=l, y1=t, x2=r, y2=b).resize((settings.width, settings.height))
        base = base.fx(lambda c: c.resize(lambda tt: 1.00 + 0.03 * (tt / dur)))

        # Audio segment
        a_seg = audio.subclip(t0, t0 + dur)

        # Captions for this time window
        w_in = [w for w in words if (w.end > t0 and w.start < t0 + dur)]
        # Render a small rolling window (last 6 words)
        def caption_make_frame(local_t: float):
            global_t = t0 + local_t
            active = -1
            seq = []
            for i, ww in enumerate(w_in):
                if ww.start <= global_t <= ww.end:
                    active = i
                seq.append(ww.word)
            seq = seq[-6:] if len(seq) > 6 else seq
            active_idx = min(len(seq) - 1, active) if active != -1 else -1
            return _caption_frame(words=seq, active_idx=active_idx, w=settings.width, h=settings.height)

        cap = ImageClip(caption_make_frame(0)).set_duration(dur)
        cap = cap.set_make_frame(caption_make_frame).set_position(("center", "center"))

        wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=dur)
        layers = [base, cap] + ([wm] if wm is not None else [])
        comp = CompositeVideoClip(layers).set_audio(a_seg)

        # Optional export each micro-clip
        if settings.export_microclips:
            clip_path = out_assets_dir / f"clip_{idx:02d}.mp4"
            comp.write_videofile(
                str(clip_path),
                fps=settings.fps,
                codec="libx264",
                audio_codec="aac",
                bitrate=clip_bitrate,
                preset="medium",
                threads=4,
                logger=None,
            )
        clips.append(comp)

    final = concatenate_videoclips(clips, method="compose").set_audio(audio)

    # Optional background music bed
    if background_music and background_music.exists():
        try:
            music = AudioFileClip(str(background_music)).volumex(settings.music_volume)
            music = music.audio_loop(duration=final.duration)
            final = final.set_audio(final.audio.set_fps(44100).fx(lambda a: a) + music)
        except Exception:
            pass

    final.write_videofile(
        str(out_final_mp4),
        fps=settings.fps,
        codec="libx264",
        audio_codec="aac",
        bitrate=final_bitrate,
        preset="medium",
        threads=4,
        logger=None,
    )


def assemble_generated_clips_then_concat(
    *,
    ffmpeg_dir: Path,
    settings: VideoSettings,
    clips: list[Path],
    voice_wav: Path,
    captions_json: Path,
    out_final_mp4: Path,
    out_assets_dir: Path,
    background_music: Path | None = None,
    branding: BrandingSettings | None = None,
) -> None:
    """
    Concats pre-generated MP4 clips into a final 9:16 video, applying the same word-by-word caption overlay
    and syncing each clip to a slice of the narration audio.
    """
    out_final_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_assets_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = ensure_ffmpeg(ffmpeg_dir)
    configure_moviepy_ffmpeg(ffmpeg_exe)

    audio = AudioFileClip(str(voice_wav)).volumex(settings.voice_volume)
    words = _load_captions(captions_json)

    total_dur = float(audio.duration)
    if total_dur <= 0.2:
        total_dur = max(3.0, float(len(clips)))

    src = clips[:] if clips else []
    if not src:
        raise ValueError("No clips provided to editor.")

    clip_count = len(src)
    chunk = total_dur / clip_count

    out_clips = []
    for idx, clip_path in enumerate(src, start=1):
        t0 = (idx - 1) * chunk
        t1 = min(total_dur, idx * chunk)
        dur = max(0.25, t1 - t0)

        base = VideoFileClip(str(clip_path)).subclip(0, min(dur, float(VideoFileClip(str(clip_path)).duration)))
        base = base.resize((settings.width, settings.height))

        a_seg = audio.subclip(t0, t0 + dur)

        w_in = [w for w in words if (w.end > t0 and w.start < t0 + dur)]

        def caption_make_frame(local_t: float):
            global_t = t0 + local_t
            active = -1
            seq = []
            for i, ww in enumerate(w_in):
                if ww.start <= global_t <= ww.end:
                    active = i
                seq.append(ww.word)
            seq = seq[-6:] if len(seq) > 6 else seq
            active_idx = min(len(seq) - 1, active) if active != -1 else -1
            return _caption_frame(words=seq, active_idx=active_idx, w=settings.width, h=settings.height)

        cap = ImageClip(caption_make_frame(0)).set_duration(dur)
        cap = cap.set_make_frame(caption_make_frame).set_position(("center", "center"))

        wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=dur)
        layers = [base, cap] + ([wm] if wm is not None else [])
        comp = CompositeVideoClip(layers).set_audio(a_seg)

        if settings.export_microclips:
            clip_out = out_assets_dir / f"clip_{idx:02d}.mp4"
            comp.write_videofile(
                str(clip_out),
                fps=settings.fps,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                threads=4,
                logger=None,
            )

        out_clips.append(comp)

    final = concatenate_videoclips(out_clips, method="compose").set_audio(audio)

    if background_music and background_music.exists():
        try:
            music = AudioFileClip(str(background_music)).volumex(settings.music_volume)
            music = music.audio_loop(duration=final.duration)
            final = final.set_audio(final.audio.set_fps(44100).fx(lambda a: a) + music)
        except Exception:
            pass

    final.write_videofile(
        str(out_final_mp4),
        fps=settings.fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )

