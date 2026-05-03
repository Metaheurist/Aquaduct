from __future__ import annotations

import math
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import numpy as np

from src.models.pillow_compat import apply_pillow_moviepy_compat

apply_pillow_moviepy_compat()

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image

from .captions import CaptionWord, caption_window_for_time, load_captions_json, render_caption_overlay_rgba
from src.core.config import BrandingSettings, VideoSettings, video_format_supports_facts_card
from .facts_card import extract_candidate_facts, facts_visible_until, pick_top_facts, render_facts_card_rgba
from .ffmpeg_slideshow import build_motion_slideshow
from .utils_ffmpeg import configure_moviepy_ffmpeg, ensure_ffmpeg


def _default_ffmpeg_dir() -> Path:
    from src.core.config import get_paths

    return get_paths().ffmpeg_dir


def editor_maybe_spatial_upscale_path(
    path: Path,
    *,
    settings: VideoSettings,
    ffmpeg_dir: Path,
    cuda_device_index: int | None = None,
) -> Path:
    mode = str(getattr(settings, "spatial_upscale_mode", "off") or "off").strip().lower()
    if mode != "auto":
        return Path(path)
    try:
        from src.render.spatial_upscale import maybe_spatial_upscale_path

        return maybe_spatial_upscale_path(
            Path(path),
            target_w=int(settings.width),
            target_h=int(settings.height),
            mode=mode,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
        )
    except Exception:
        return Path(path)


def _ensure_rgba_np(pic: np.ndarray) -> np.ndarray:
    """
    MoviePy composites require matching channel counts; caption/facts overlays are RGBA.
    Still images and decoded video frames are often RGB — pad an opaque alpha channel.
    """
    if pic is None or not isinstance(pic, np.ndarray) or pic.ndim != 3:
        return pic
    c = int(pic.shape[2])
    if c == 4:
        return pic
    h, w = pic.shape[:2]
    if c == 3:
        alpha = np.full((h, w, 1), 255, dtype=pic.dtype)
        return np.concatenate([pic, alpha], axis=2)
    if c == 1:
        rgb = np.repeat(pic, 3, axis=2)
        alpha = np.full((h, w, 1), 255, dtype=pic.dtype)
        return np.concatenate([rgb, alpha], axis=2)
    return pic


def _rgb_u8_for_moviepy_imageclip(pic: np.ndarray) -> np.ndarray:
    """
    MoviePy 1.x ``drawing.blit`` expands masks to 3 channels and multiplies by ``im1``;
    if ``im1`` is RGBA (4 ch) while a separate alpha ``mask`` exists (common after
    ``ImageClip`` loads an RGBA PNG then ``fl_image``), blit raises a broadcast error.
    Keep composited layer frames as RGB; alpha stays on ``clip.mask`` when present.
    """
    p = _ensure_rgba_np(pic)
    return np.ascontiguousarray(p[:, :, :3])


def _video_clip_from_rgba_overlay_fn(
    overlay_fn: Callable[[float], np.ndarray],
    *,
    duration: float,
) -> VideoClip:
    """
    Turn a function that returns **RGBA** numpy frames into a MoviePy ``VideoClip`` with
    **RGB** pixels and a separate **mask** clip (alpha).

    ``ImageClip`` + ``set_make_frame`` cannot be used for animated RGBA: MoviePy keeps
    the mask from the *first* frame only, while ``make_frame(t)`` returns full RGBA —
    then ``drawing.blit`` multiplies a 3-channel mask with a 4-channel image and crashes.

    A small time-keyed cache avoids rendering the same overlay twice per timestamp for
    RGB and mask.
    """
    cache: dict[float, np.ndarray] = {}

    def rgba_at(t: float) -> np.ndarray:
        k = round(float(t), 5)
        if k not in cache:
            cache[k] = np.ascontiguousarray(_ensure_rgba_np(overlay_fn(t)))
        return cache[k]

    def make_rgb(t: float) -> np.ndarray:
        rgba = rgba_at(t)
        return rgba[:, :, :3].astype(np.uint8, copy=False)

    def make_mask(t: float) -> np.ndarray:
        rgba = rgba_at(t)
        return rgba[:, :, 3].astype(np.float32) / 255.0

    clip = VideoClip(make_rgb, duration=duration)
    mask_clip = VideoClip(make_mask, ismask=True, duration=duration)
    return clip.set_mask(mask_clip)


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


def pro_mode_frame_count(*, pro_clip_seconds: float, fps: int) -> int:
    """Frames to generate: round(pro_clip_seconds * fps), capped by AQUADUCT_PRO_MAX_FRAMES if set."""
    pc = max(0.05, float(pro_clip_seconds))
    fp = max(1, int(fps))
    n = max(1, round(pc * fp))
    cap_s = os.environ.get("AQUADUCT_PRO_MAX_FRAMES", "").strip()
    if cap_s.isdigit():
        n = min(n, max(1, int(cap_s)))
    return int(n)


def _ffmpeg_align_wav_to_duration(ffmpeg_exe: Path, in_wav: Path, out_wav: Path, dur_s: float) -> None:
    """Trim audio to dur_s, then pad with silence so output is exactly dur_s (seconds)."""
    d = max(0.1, float(dur_s))
    # atrim first (caps long narration), apad extends short audio to whole_dur
    fl = f"atrim=duration={d},asetpts=PTS-STARTPTS,apad=whole_dur={d}"
    cmd = [
        str(ffmpeg_exe),
        "-y",
        "-i",
        str(in_wav),
        "-af",
        fl,
        str(out_wav),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _pro_single_frame_clip(
    img_path: Path,
    *,
    duration: float,
    settings: VideoSettings,
    ffmpeg_dir: Path | None = None,
    cuda_device_index: int | None = None,
) -> ImageClip:
    fd = ffmpeg_dir if ffmpeg_dir is not None else _default_ffmpeg_dir()
    p = editor_maybe_spatial_upscale_path(
        Path(img_path),
        settings=settings,
        ffmpeg_dir=fd,
        cuda_device_index=cuda_device_index,
    )
    base = ImageClip(str(p)).set_duration(max(0.001, float(duration)))
    iw, ih = base.w, base.h
    l, t, r, b = _fit_crop_9x16(iw, ih, settings.width, settings.height)
    base = base.crop(x1=l, y1=t, x2=r, y2=b).resize((settings.width, settings.height))
    base = base.fl_image(_rgb_u8_for_moviepy_imageclip)
    return base


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

    wm = ImageClip(str(p)).set_duration(duration)
    wm = wm.fl_image(_rgb_u8_for_moviepy_imageclip)
    wm = wm.set_opacity(opacity)
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
    video_format: str | None = None,
    cuda_device_index: int | None = None,
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
    if (
        video_format_supports_facts_card(video_format)
        and (article_text or "").strip()
        and bool(getattr(settings, "facts_card_enabled", True))
    ):
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
    missing = [p for p in imgs if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing image file(s) for assembly: "
            + ", ".join(str(p) for p in missing[:8])
            + (" …" if len(missing) > 8 else "")
        )

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
                xfade_transition=str(getattr(settings, "xfade_transition", "fade") or "fade"),
            )
            base_mp4 = editor_maybe_spatial_upscale_path(
                base_mp4,
                settings=settings,
                ffmpeg_dir=ffmpeg_dir,
                cuda_device_index=cuda_device_index,
            )

            base = VideoFileClip(str(base_mp4)).set_duration(total_dur).resize((settings.width, settings.height))
            base = base.fl_image(_rgb_u8_for_moviepy_imageclip)

            def caption_overlay(global_t: float) -> np.ndarray:
                return overlay_fn(float(global_t))

            cap = _video_clip_from_rgba_overlay_fn(caption_overlay, duration=total_dur).set_position(
                ("center", "center")
            )
            wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=total_dur)
            layers = [base, cap] + ([wm] if wm is not None else [])
            # use_bgclip=True: first layer is full-size background; avoids RGB ColorClip + RGBA blit mismatch.
            final = CompositeVideoClip(layers, use_bgclip=True).set_audio(audio)

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
        img_u = editor_maybe_spatial_upscale_path(
            Path(img_path),
            settings=settings,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
        )
        base = ImageClip(str(img_u)).set_duration(dur)

        # Crop to 9:16 and resize, add subtle zoom
        iw, ih = base.w, base.h
        l, t, r, b = _fit_crop_9x16(iw, ih, settings.width, settings.height)
        base = base.crop(x1=l, y1=t, x2=r, y2=b).resize((settings.width, settings.height))
        base = base.fx(lambda c: c.resize(lambda tt: 1.00 + 0.03 * (tt / dur)))
        base = base.fl_image(_rgb_u8_for_moviepy_imageclip)

        # Audio segment
        a_seg = audio.subclip(t0, t0 + dur)

        def caption_overlay(local_t: float) -> np.ndarray:
            return overlay_fn(float(t0 + local_t))

        cap = _video_clip_from_rgba_overlay_fn(caption_overlay, duration=dur).set_position(("center", "center"))

        wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=dur)
        layers = [base, cap] + ([wm] if wm is not None else [])
        comp = CompositeVideoClip(layers, use_bgclip=True).set_audio(a_seg)

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


def assemble_pro_frame_sequence_then_concat(
    *,
    ffmpeg_dir: Path,
    settings: VideoSettings,
    images: list[Path],
    voice_wav: Path,
    captions_json: Path,
    out_final_mp4: Path,
    out_assets_dir: Path,
    timeline_seconds: float,
    background_music: Path | None = None,
    branding: BrandingSettings | None = None,
    article_text: str | None = None,
    topic_tags: list[str] | None = None,
    video_format: str | None = None,
    cuda_device_index: int | None = None,
) -> None:
    """
    One generated still per output frame at ``settings.fps``; total timeline ``timeline_seconds``.
    Voice is trimmed/padded to that duration; captions use the same timeline.
    """
    from debug import dprint

    T = max(0.1, float(timeline_seconds))
    dprint("editor", "assemble_pro_frame_sequence_then_concat", f"images={len(images)}", f"timeline={T}")
    out_final_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_assets_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = ensure_ffmpeg(ffmpeg_dir)
    configure_moviepy_ffmpeg(ffmpeg_exe)

    imgs = list(images) if images else []
    if not imgs:
        raise ValueError("No images provided for pro frame sequence.")
    missing = [p for p in imgs if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing image file(s) for pro assembly: "
            + ", ".join(str(p) for p in missing[:8])
            + (" …" if len(missing) > 8 else "")
        )

    aligned_wav = out_assets_dir / "voice_pro_timeline.wav"
    try:
        _ffmpeg_align_wav_to_duration(ffmpeg_exe, voice_wav, aligned_wav, T)
        audio_src = aligned_wav
    except Exception:
        audio_src = voice_wav

    audio = AudioFileClip(str(audio_src)).volumex(settings.voice_volume)
    if float(audio.duration) > T + 0.05:
        audio = audio.subclip(0, T)
    words = load_captions_json(captions_json)

    tags = list(topic_tags or [])
    facts_lines: list[str] | None = None
    if (
        video_format_supports_facts_card(video_format)
        and (article_text or "").strip()
        and bool(getattr(settings, "facts_card_enabled", True))
    ):
        facts_lines = pick_top_facts(extract_candidate_facts(article_text or ""), n=2) or None

    overlay_fn = _build_overlay_make_frame(
        words=words,
        settings=settings,
        branding=branding,
        topic_tags=tags,
        facts_lines=facts_lines,
        total_dur=T,
    )

    fps = max(1, int(settings.fps))
    frame_dur = 1.0 / float(fps)
    frame_clips = [
        _pro_single_frame_clip(
            Path(p),
            duration=frame_dur,
            settings=settings,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
        )
        for p in imgs
    ]
    base_video = concatenate_videoclips(frame_clips, method="compose")
    d_vid = float(base_video.duration)
    if d_vid < T - 1e-2:
        tail = _pro_single_frame_clip(
            Path(imgs[-1]),
            duration=max(frame_dur, T - d_vid),
            settings=settings,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
        )
        base_video = concatenate_videoclips([base_video, tail], method="compose")
    elif d_vid > T + 1e-2:
        base_video = base_video.subclip(0, T)

    def caption_overlay(global_t: float) -> np.ndarray:
        return overlay_fn(float(global_t))

    cap = _video_clip_from_rgba_overlay_fn(caption_overlay, duration=T).set_position(("center", "center"))
    wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=T)
    layers = [base_video, cap] + ([wm] if wm is not None else [])
    final = CompositeVideoClip(layers, use_bgclip=True).set_duration(T).set_audio(audio)

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
        fps=fps,
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
    video_format: str | None = None,
    clip_durations: list[float] | None = None,
    cuda_device_index: int | None = None,
) -> None:
    """
    Concats pre-generated MP4 clips into a final 9:16 video, applying the same word-by-word caption overlay
    and syncing each clip to a slice of the narration audio.

    ``clip_durations`` (in seconds, parallel to ``clips``) is preferred when provided; the editor uses
    each entry to slice both the video and the matching audio chunk. When omitted or any entry is
    missing/<=0, the editor reads the per-clip ``.meta.json`` sidecar (written by
    ``src.models.native_fps.write_clip_meta``) and finally falls back to ``VideoFileClip.duration``.
    Equal-chunk slicing is no longer used unless every source above fails.
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
    if (
        video_format_supports_facts_card(video_format)
        and (article_text or "").strip()
        and bool(getattr(settings, "facts_card_enabled", True))
    ):
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

    def _resolve_duration(idx: int, clip_path: Path, vsrc_dur: float) -> float:
        if clip_durations and idx < len(clip_durations):
            try:
                v = float(clip_durations[idx])
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
        try:
            from src.models.native_fps import clip_duration_seconds

            v = clip_duration_seconds(clip_path)
            if v and v > 0:
                return float(v)
        except Exception:  # pragma: no cover — meta layer best-effort
            pass
        if vsrc_dur and vsrc_dur > 0:
            return float(vsrc_dur)
        return max(0.25, total_dur / max(1, clip_count))

    resolved_durs: list[float] = []

    out_clips = []
    cursor = 0.0
    for idx, clip_path in enumerate(src, start=1):
        cp = editor_maybe_spatial_upscale_path(
            Path(clip_path),
            settings=settings,
            ffmpeg_dir=ffmpeg_dir,
            cuda_device_index=cuda_device_index,
        )
        vsrc = VideoFileClip(str(cp))
        v_dur = float(getattr(vsrc, "duration", 0.0) or 0.0)
        dur = _resolve_duration(idx - 1, clip_path, v_dur)
        dur = max(0.25, dur)
        resolved_durs.append(dur)

        t0 = cursor
        if t0 + dur > total_dur:
            dur = max(0.25, total_dur - t0)
        cursor = t0 + dur

        base = vsrc.subclip(0, min(dur, v_dur if v_dur > 0 else dur))
        base = base.resize((settings.width, settings.height)).fl_image(_rgb_u8_for_moviepy_imageclip)

        a_seg = audio.subclip(t0, t0 + dur)

        def _caption_overlay_factory(t_start: float, fn: Callable[[float], np.ndarray]) -> Callable[[float], np.ndarray]:
            def caption_overlay(local_t: float) -> np.ndarray:
                return fn(float(t_start + local_t))

            return caption_overlay

        cap = _video_clip_from_rgba_overlay_fn(
            _caption_overlay_factory(t0, overlay_fn), duration=dur
        ).set_position(("center", "center"))

        wm = _make_watermark_clip(branding=branding, out_w=settings.width, out_h=settings.height, duration=dur)
        layers = [base, cap] + ([wm] if wm is not None else [])
        comp = CompositeVideoClip(layers, use_bgclip=True).set_audio(a_seg)

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

