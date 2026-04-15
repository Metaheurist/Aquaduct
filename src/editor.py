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
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

from .config import VideoSettings
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

        comp = CompositeVideoClip([base, cap]).set_audio(a_seg)

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

