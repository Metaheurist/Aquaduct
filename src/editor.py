from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image

from .captions import CaptionWord, caption_window_for_time, load_captions_json, render_caption_overlay_rgba
from .config import BrandingSettings, VideoSettings
from .facts_card import extract_candidate_facts, facts_visible_until, pick_top_facts, render_facts_card_rgba
from .ffmpeg_slideshow import build_motion_slideshow
from .utils_ffmpeg import configure_moviepy_ffmpeg, ensure_ffmpeg


def _build_overlay_make_frame(
    *,
    words: list[CaptionWord],
    settings: VideoSettings,
    branding: BrandingSettings | None,
    topic_tags: list[str],
    facts_lines: list[str] | None,
    total_dur: float,
):
    facts_arr: np.ndarray | None = None
    facts_end = 0.0
    if facts_lines and bool(getattr(settings, "facts_card_enabled", True)):
        pos = str(getattr(settings, "facts_card_position", "top_left") or "top_left")
        facts_arr = render_facts_card_rgba(
            lines=facts_lines,
            w=int(settings.width),
            h=int(settings.height),
            branding=branding,
            position=pos,
        )
        mode = str(getattr(settings, "facts_card_duration", "short") or "short")
        facts_end = facts_visible_until(total_dur=total_dur, duration_mode=mode)

    def make_frame(global_t: float) -> np.ndarray:
        max_w = int(getattr(settings, "caption_max_words", 8))
        ws, idxs, active = caption_window_for_time(words, global_t, max_w)
        cap = render_caption_overlay_rgba(
            word_strings=ws,
            window_indices=idxs,
            active_in_window=active,
            all_words=words,
            w=int(settings.width),
            h=int(settings.height),
            branding=branding,
            settings=settings,
            topic_tags=topic_tags,
        )
        if facts_arr is None or global_t >= facts_end:
            return cap
        base = Image.fromarray(facts_arr, mode="RGBA")
        top = Image.fromarray(cap, mode="RGBA")
        return np.array(Image.alpha_composite(base, top))

    return make_frame


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
    article_text: str | None = None,
    topic_tags: list[str] | None = None,
) -> None:
    """
    Builds 9:16 final video as concatenation of few-second micro-clips (one per image/beat).
    Captioning is word-by-word using timestamps over the whole audio.
    """
    from debug import dprint

    dprint("editor", "assemble_microclips_then_concat", f"images={len(images)}", f"out={out_final_mp4.name}")
    out_final_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_assets_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = ensure_ffmpeg(ffmpeg_dir)
    configure_moviepy_ffmpeg(ffmpeg_exe)

    audio = AudioFileClip(str(voice_wav)).volumex(settings.voice_volume)
    words = load_captions_json(captions_json)

    total_dur = float(audio.duration)
    if total_dur <= 0.2:
        total_dur = 5.0

    tags = list(topic_tags or [])
    facts_lines: list[str] | None = None
    if (article_text or "").strip() and bool(getattr(settings, "facts_card_enabled", True)):
        facts_lines = pick_top_facts(extract_candidate_facts(article_text or ""), n=2) or None

    overlay_fn = _build_overlay_make_frame(
        words=words,
        settings=settings,
        branding=branding,
        topic_tags=tags,
        facts_lines=facts_lines,
        total_dur=total_dur,
    )

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

    # Optional FFmpeg motion+transitions path (then captions/watermark via MoviePy).
    if bool(getattr(settings, "enable_motion", False)):
        try:
            durs = [max(0.25, float(t1 - t0)) for (t0, t1, _p) in clip_specs]
            base_mp4 = out_assets_dir / "motion_base.mp4"
            build_motion_slideshow(
                ffmpeg_dir=ffmpeg_dir,
                images=[p for (_t0, _t1, p) in clip_specs],
                durations=durs,
                out_mp4=base_mp4,
                width=settings.width,
                height=settings.height,
                fps=int(settings.fps),
                transition_strength=str(getattr(settings, "transition_strength", "low") or "low"),
            )

            base = VideoFileClip(str(base_mp4)).set_duration(total_dur).resize((settings.width, settings.height))

            def caption_make_frame(global_t: float):
                return overlay_fn(float(global_t))

            cap = ImageClip(caption_make_frame(0)).set_duration(total_dur)
            cap = cap.set_make_frame(caption_make_frame).set_position(("center", "center"))
            wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=total_dur)
            layers = [base, cap] + ([wm] if wm is not None else [])
            final = CompositeVideoClip(layers).set_audio(audio)

            if background_music and background_music.exists():
                try:
                    music = AudioFileClip(str(background_music)).volumex(settings.music_volume)
                    music = music.audio_loop(duration=final.duration)
                    final = final.set_audio(final.audio.set_fps(44100).fx(lambda a: a) + music)
                except Exception:
                    pass

            bitrate_map = {"low": "3500k", "med": "6000k", "high": "9000k"}
            final_bitrate = bitrate_map.get(settings.bitrate_preset, "6000k")
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
            return
        except Exception:
            # Fall back to the original MoviePy microclip path below.
            pass

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

        def caption_make_frame(local_t: float):
            return overlay_fn(float(t0 + local_t))

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
    article_text: str | None = None,
    topic_tags: list[str] | None = None,
) -> None:
    """
    Concats pre-generated MP4 clips into a final 9:16 video, applying the same word-by-word caption overlay
    and syncing each clip to a slice of the narration audio.
    """
    from debug import dprint

    dprint("editor", "assemble_generated_clips_then_concat", f"clips={len(clips)}", f"out={out_final_mp4.name}")
    out_final_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_assets_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = ensure_ffmpeg(ffmpeg_dir)
    configure_moviepy_ffmpeg(ffmpeg_exe)

    audio = AudioFileClip(str(voice_wav)).volumex(settings.voice_volume)
    words = load_captions_json(captions_json)

    total_dur = float(audio.duration)
    if total_dur <= 0.2:
        total_dur = max(3.0, float(len(clips)))

    tags = list(topic_tags or [])
    facts_lines: list[str] | None = None
    if (article_text or "").strip() and bool(getattr(settings, "facts_card_enabled", True)):
        facts_lines = pick_top_facts(extract_candidate_facts(article_text or ""), n=2) or None

    overlay_fn = _build_overlay_make_frame(
        words=words,
        settings=settings,
        branding=branding,
        topic_tags=tags,
        facts_lines=facts_lines,
        total_dur=total_dur,
    )

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

        def caption_make_frame(local_t: float):
            return overlay_fn(float(t0 + local_t))

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

