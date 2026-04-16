from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import (
    AppSettings,
    BrandingSettings,
    VideoSettings,
    VIDEO_FORMATS,
    VideoFormat,
    default_topic_tags_by_mode,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def settings_path() -> Path:
    return _root() / "ui_settings.json"


def _sanitize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    out: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = " ".join(t.split()).strip()
        if not t:
            continue
        if t not in out:
            out.append(t)
    return out[:50]


def _norm_video_format(s: Any) -> VideoFormat:
    t = str(s or "news").strip().lower()
    return t if t in VIDEO_FORMATS else "news"


def _sanitize_topic_tags_map(raw: Any) -> dict[str, list[str]]:
    merged = default_topic_tags_by_mode()
    if not isinstance(raw, dict):
        return merged
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        kk = k.strip().lower()
        if kk not in VIDEO_FORMATS:
            continue
        merged[kk] = _sanitize_tags(v)
    return merged


def load_settings() -> AppSettings:
    p = settings_path()
    if not p.exists():
        return AppSettings()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()

    video_raw = data.get("video", {}) if isinstance(data, dict) else {}
    video = VideoSettings(
        width=int(video_raw.get("width", 1080)),
        height=int(video_raw.get("height", 1920)),
        fps=int(video_raw.get("fps", 30)),
        microclip_min_s=float(video_raw.get("microclip_min_s", 3.5)),
        microclip_max_s=float(video_raw.get("microclip_max_s", 7.5)),
        music_volume=float(video_raw.get("music_volume", 0.08)),
        voice_volume=float(video_raw.get("voice_volume", 1.0)),
        images_per_video=int(video_raw.get("images_per_video", 8)),
        export_microclips=bool(video_raw.get("export_microclips", True)),
        bitrate_preset=str(video_raw.get("bitrate_preset", "med")) if video_raw.get("bitrate_preset") in ("low", "med", "high") else "med",
        use_image_slideshow=bool(video_raw.get("use_image_slideshow", True)),
        clips_per_video=int(video_raw.get("clips_per_video", 3)),
        clip_seconds=float(video_raw.get("clip_seconds", 4.0)),
        cleanup_images_after_run=bool(video_raw.get("cleanup_images_after_run", False)),
        high_quality_topic_selection=bool(video_raw.get("high_quality_topic_selection", True)),
        fetch_article_text=bool(video_raw.get("fetch_article_text", True)),
        llm_factcheck=bool(video_raw.get("llm_factcheck", True)),
        prompt_conditioning=bool(video_raw.get("prompt_conditioning", True)),
        seed_base=(int(video_raw.get("seed_base")) if str(video_raw.get("seed_base", "")).strip().lstrip("-").isdigit() else None),
        quality_retries=int(video_raw.get("quality_retries", 2)),
        enable_motion=bool(video_raw.get("enable_motion", True)),
        transition_strength=str(video_raw.get("transition_strength", "low"))
        if str(video_raw.get("transition_strength", "low")) in ("off", "low", "med")
        else "low",
        audio_polish=str(video_raw.get("audio_polish", "basic"))
        if str(video_raw.get("audio_polish", "basic")) in ("off", "basic", "strong")
        else "basic",
        music_ducking=bool(video_raw.get("music_ducking", True)),
        music_ducking_amount=float(video_raw.get("music_ducking_amount", 0.7)),
        music_fade_s=float(video_raw.get("music_fade_s", 1.2)),
        sfx_mode=str(video_raw.get("sfx_mode", "off")) if str(video_raw.get("sfx_mode", "off")) in ("off", "subtle") else "off",
        captions_enabled=bool(video_raw.get("captions_enabled", True)),
        caption_highlight_intensity=str(video_raw.get("caption_highlight_intensity", "strong"))
        if str(video_raw.get("caption_highlight_intensity", "strong")) in ("subtle", "strong")
        else "strong",
        caption_max_words=int(video_raw.get("caption_max_words", 8)),
        facts_card_enabled=bool(video_raw.get("facts_card_enabled", True)),
        facts_card_position=str(video_raw.get("facts_card_position", "top_left"))
        if str(video_raw.get("facts_card_position", "top_left")) in ("top_left", "top_right")
        else "top_left",
        facts_card_duration=str(video_raw.get("facts_card_duration", "short"))
        if str(video_raw.get("facts_card_duration", "short")) in ("short", "long")
        else "short",
    )

    branding_raw = data.get("branding", {}) if isinstance(data, dict) else {}
    branding = BrandingSettings(
        theme_enabled=bool(branding_raw.get("theme_enabled", False)),
        palette_id=str(branding_raw.get("palette_id", "default")),
        bg_enabled=bool(branding_raw.get("bg_enabled", False)),
        bg_hex=str(branding_raw.get("bg_hex", "#0F0F10")),
        panel_enabled=bool(branding_raw.get("panel_enabled", False)),
        panel_hex=str(branding_raw.get("panel_hex", "#0B0B0F")),
        text_enabled=bool(branding_raw.get("text_enabled", False)),
        text_hex=str(branding_raw.get("text_hex", "#FFFFFF")),
        muted_enabled=bool(branding_raw.get("muted_enabled", False)),
        muted_hex=str(branding_raw.get("muted_hex", "#B7B7C2")),
        accent_enabled=bool(branding_raw.get("accent_enabled", False)),
        accent_hex=str(branding_raw.get("accent_hex", "#25F4EE")),
        danger_enabled=bool(branding_raw.get("danger_enabled", False)),
        danger_hex=str(branding_raw.get("danger_hex", "#FE2C55")),
        watermark_enabled=bool(branding_raw.get("watermark_enabled", False)),
        watermark_path=str(branding_raw.get("watermark_path", "")),
        watermark_opacity=float(branding_raw.get("watermark_opacity", 0.22)),
        watermark_scale=float(branding_raw.get("watermark_scale", 0.18)),
        watermark_position=str(branding_raw.get("watermark_position", "top_right"))
        if str(branding_raw.get("watermark_position", "top_right"))
        in ("top_left", "top_right", "bottom_left", "bottom_right", "center")
        else "top_right",
        video_style_enabled=bool(branding_raw.get("video_style_enabled", False)),
        video_style_strength=str(branding_raw.get("video_style_strength", "subtle"))
        if str(branding_raw.get("video_style_strength", "subtle")) in ("subtle", "strong")
        else "subtle",
    )

    topic_map = (
        _sanitize_topic_tags_map(data.get("topic_tags_by_mode")) if isinstance(data, dict) else default_topic_tags_by_mode()
    )
    legacy_flat = _sanitize_tags(data.get("topic_tags", [])) if isinstance(data, dict) else []
    if legacy_flat and not (topic_map.get("news") or []):
        topic_map = {**topic_map, "news": legacy_flat}

    video_format = _norm_video_format(data.get("video_format")) if isinstance(data, dict) else "news"

    return AppSettings(
        topic_tags_by_mode=topic_map,
        video_format=video_format,
        prefer_gpu=bool(data.get("prefer_gpu", True)) if isinstance(data, dict) else True,
        try_llm_4bit=bool(data.get("try_llm_4bit", True)) if isinstance(data, dict) else True,
        try_sdxl_turbo=bool(data.get("try_sdxl_turbo", True)) if isinstance(data, dict) else True,
        background_music_path=str(data.get("background_music_path", "")) if isinstance(data, dict) else "",
        hf_token=str(data.get("hf_token", "")) if isinstance(data, dict) else "",
        hf_api_enabled=bool(data.get("hf_api_enabled", True)) if isinstance(data, dict) else True,
        firecrawl_enabled=bool(data.get("firecrawl_enabled", False)) if isinstance(data, dict) else False,
        firecrawl_api_key=str(data.get("firecrawl_api_key", "")) if isinstance(data, dict) else "",
        personality_id=str(data.get("personality_id", "auto")) if isinstance(data, dict) else "auto",
        llm_model_id=str(data.get("llm_model_id", "")) if isinstance(data, dict) else "",
        image_model_id=str(data.get("image_model_id", "")) if isinstance(data, dict) else "",
        video_model_id=str(data.get("video_model_id", "")) if isinstance(data, dict) else "",
        voice_model_id=str(data.get("voice_model_id", "")) if isinstance(data, dict) else "",
        video=video,
        branding=branding,
    )


def save_settings(settings: AppSettings) -> None:
    from debug import dprint

    p = settings_path()
    payload = asdict(settings)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    dprint("config", "save_settings", str(p))

