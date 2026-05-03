from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.app_dirs import application_data_dir, mark_path_hidden
from src.render.ffmpeg_slideshow import sanitize_xfade_transition
from src.core.config import (
    MAX_CUSTOM_VIDEO_INSTRUCTIONS,
    ApiModelRuntimeSettings,
    ApiRoleConfig,
    AppSettings,
    BrandingSettings,
    GpuSelectionMode,
    ModelExecutionMode,
    MultiGpuShardMode,
    PictureSettings,
    VideoSettings,
    VIDEO_FORMATS,
    VideoFormat,
    default_api_models,
    default_topic_tags_by_mode,
)


def settings_path() -> Path:
    return application_data_dir() / "ui_settings.json"


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


def _norm_run_content_mode(s: Any) -> str:
    t = str(s or "preset").strip().lower()
    return t if t in ("preset", "custom") else "preset"


def _sanitize_custom_instructions(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    return s[:MAX_CUSTOM_VIDEO_INSTRUCTIONS]


def _norm_model_execution_mode(s: Any) -> ModelExecutionMode:
    t = str(s or "local").strip().lower()
    return t if t in ("local", "api") else "local"


def _norm_models_storage_mode(s: Any) -> str:
    t = str(s or "default").strip().lower()
    return t if t in ("default", "external") else "default"


def _norm_gpu_selection_mode(s: Any) -> GpuSelectionMode:
    t = str(s or "auto").strip().lower()
    return t if t in ("auto", "single") else "auto"


def _norm_multi_gpu_shard_mode(s: Any) -> MultiGpuShardMode:
    t = str(s or "off").strip().lower()
    return t if t in ("off", "vram_first_auto") else "off"


def _norm_quant_mode(s: Any) -> str:
    t = str(s or "auto").strip().lower()
    if t in ("auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"):
        return t
    if t in ("4bit", "nf4", "bnb4"):
        return "nf4_4bit"
    if t in ("8bit", "bnb8", "int-8"):
        return "int8"
    if t in ("offload", "cpu", "cpu-offload"):
        return "cpu_offload"
    return "auto"


def _parse_api_role(raw: Any) -> ApiRoleConfig:
    if not isinstance(raw, dict):
        return ApiRoleConfig()
    return ApiRoleConfig(
        provider=str(raw.get("provider", "") or ""),
        model=str(raw.get("model", "") or ""),
        base_url=str(raw.get("base_url", "") or ""),
        org_id=str(raw.get("org_id", "") or ""),
        voice_id=str(raw.get("voice_id", "") or ""),
    )


def _parse_api_models(raw: Any) -> ApiModelRuntimeSettings:
    base = default_api_models()
    if not isinstance(raw, dict):
        return base
    return ApiModelRuntimeSettings(
        llm=_parse_api_role(raw.get("llm")),
        image=_parse_api_role(raw.get("image")),
        video=_parse_api_role(raw.get("video")),
        voice=_parse_api_role(raw.get("voice")),
    )


def _sanitize_topic_tag_notes_for_settings(raw: Any) -> dict[str, str]:
    """Coerce persisted ``topic_tag_notes`` into ``{tag_lower: note}``.

    Defers to :func:`src.content.topic_constraints.sanitize_topic_tag_notes`
    so the validation logic stays in one place; if the import path fails
    (e.g. during install bootstrap) we still return ``{}`` instead of
    crashing the load.
    """
    try:
        from src.content.topic_constraints import sanitize_topic_tag_notes

        return sanitize_topic_tag_notes(raw)
    except Exception:
        return {}


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
    except Exception as e:
        try:
            from debug import dprint

            dprint("config", "load_settings failed", str(p), repr(e))
        except Exception:
            pass
        return AppSettings()

    return app_settings_from_dict(data)


def app_settings_from_dict(data: Any) -> AppSettings:
    """Build AppSettings from a dict (same shape as ``ui_settings.json`` or a CLI merge payload)."""
    if not isinstance(data, dict):
        return AppSettings()

    video_raw = data.get("video", {}) if isinstance(data, dict) else {}
    try:
        from src.render.video_quality_presets import (
            apply_video_presets,
            migrate_legacy_video_settings,
        )

        video_raw = apply_video_presets(migrate_legacy_video_settings(dict(video_raw)))
    except Exception:
        pass
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
        pro_mode=bool(video_raw.get("pro_mode", False)),
        pro_clip_seconds=float(video_raw.get("pro_clip_seconds", 4.0)),
        clips_per_video=int(video_raw.get("clips_per_video", 3)),
        clip_seconds=float(video_raw.get("clip_seconds", 4.0)),
        cleanup_images_after_run=bool(video_raw.get("cleanup_images_after_run", False)),
        high_quality_topic_selection=bool(video_raw.get("high_quality_topic_selection", True)),
        fetch_article_text=bool(video_raw.get("fetch_article_text", True)),
        llm_factcheck=bool(video_raw.get("llm_factcheck", True)),
        prompt_conditioning=bool(video_raw.get("prompt_conditioning", True)),
        story_multistage_enabled=bool(video_raw.get("story_multistage_enabled", False)),
        story_web_context=bool(video_raw.get("story_web_context", False)),
        story_reference_images=bool(video_raw.get("story_reference_images", False)),
        resume_partial_pipeline=bool(video_raw.get("resume_partial_pipeline", False)),
        seed_base=(int(video_raw.get("seed_base")) if str(video_raw.get("seed_base", "")).strip().lstrip("-").isdigit() else None),
        quality_retries=int(video_raw.get("quality_retries", 2)),
        enable_motion=bool(video_raw.get("enable_motion", True)),
        transition_strength=str(video_raw.get("transition_strength", "low"))
        if str(video_raw.get("transition_strength", "low")) in ("off", "low", "med")
        else "low",
        xfade_transition=sanitize_xfade_transition(str(video_raw.get("xfade_transition", "fade"))),
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
        platform_preset_id=str(video_raw.get("platform_preset_id", "") or ""),
        effects_preset_id=str(video_raw.get("effects_preset_id", "") or ""),
        smoothness_mode=str(video_raw.get("smoothness_mode", "off") or "off")
        if str(video_raw.get("smoothness_mode", "off")) in ("off", "ffmpeg", "rife")
        else "off",
        smoothness_target_fps=int(video_raw.get("smoothness_target_fps", 24) or 24),
        spatial_upscale_mode=str(video_raw.get("spatial_upscale_mode", "off") or "off")
        if str(video_raw.get("spatial_upscale_mode", "off") or "off") in ("off", "auto")
        else "off",
        video_length_preset_id=str(video_raw.get("video_length_preset_id", "medium") or "medium"),
        video_scene_preset_id=str(video_raw.get("video_scene_preset_id", "balanced") or "balanced"),
        video_fps_preset_id=str(video_raw.get("video_fps_preset_id", "standard_30") or "standard_30"),
        video_resolution_preset_id=str(video_raw.get("video_resolution_preset_id", "vertical_1080p") or "vertical_1080p"),
        article_relevance_screen=bool(video_raw.get("article_relevance_screen", True)),
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
        photo_style_enabled=bool(branding_raw.get("photo_style_enabled", False)),
        photo_frame_enabled=bool(branding_raw.get("photo_frame_enabled", False)),
        photo_frame_width=int(branding_raw.get("photo_frame_width", 24)),
        photo_paper_hex=str(branding_raw.get("photo_paper_hex", "#F2F0E9") or "#F2F0E9"),
    )

    topic_map = (
        _sanitize_topic_tags_map(data.get("topic_tags_by_mode")) if isinstance(data, dict) else default_topic_tags_by_mode()
    )
    legacy_flat = _sanitize_tags(data.get("topic_tags", [])) if isinstance(data, dict) else []
    if legacy_flat and not (topic_map.get("news") or []):
        topic_map = {**topic_map, "news": legacy_flat}

    media_mode = str(data.get("media_mode", "video") or "video").strip().lower() if isinstance(data, dict) else "video"
    if media_mode not in ("video", "photo"):
        media_mode = "video"

    video_format = _norm_video_format(data.get("video_format")) if isinstance(data, dict) else "news"
    api_models = _parse_api_models(data.get("api_models")) if isinstance(data, dict) else default_api_models()
    model_execution_mode = _norm_model_execution_mode(data.get("model_execution_mode")) if isinstance(data, dict) else "local"
    models_storage_mode = _norm_models_storage_mode(data.get("models_storage_mode")) if isinstance(data, dict) else "default"
    models_external_path = str(data.get("models_external_path", "") or "") if isinstance(data, dict) else ""

    picture_raw = data.get("picture", {}) if isinstance(data, dict) else {}
    if not isinstance(picture_raw, dict):
        picture_raw = {}
    pic_out = str(picture_raw.get("output_type", "single_image") or "single_image").strip()
    if pic_out not in ("single_image", "image_set", "layouted"):
        pic_out = "single_image"
    pic_fmt = str(picture_raw.get("picture_format", "poster") or "poster").strip()
    if pic_fmt not in ("poster", "newspaper", "comic"):
        pic_fmt = "poster"
    picture = PictureSettings(
        template_id=str(picture_raw.get("template_id", "vertical_1080") or "vertical_1080"),
        width=int(picture_raw.get("width", 1080)),
        height=int(picture_raw.get("height", 1920)),
        output_type=pic_out,  # type: ignore[arg-type]
        image_count=int(picture_raw.get("image_count", 6)),
        picture_format=pic_fmt,  # type: ignore[arg-type]
    )

    # Quant modes (per role). Migration: if script mode absent, map legacy try_llm_4bit.
    _script_raw = data.get("script_quant_mode", None)
    if _script_raw is None:
        _script_raw = "nf4_4bit" if bool(data.get("try_llm_4bit", True)) else "fp16"
    script_q = _norm_quant_mode(_script_raw)
    image_q = _norm_quant_mode(data.get("image_quant_mode", "auto"))
    video_q = _norm_quant_mode(data.get("video_quant_mode", "auto"))
    voice_q = _norm_quant_mode(data.get("voice_quant_mode", "auto"))

    return AppSettings(
        topic_tags_by_mode=topic_map,
        topic_tag_notes=_sanitize_topic_tag_notes_for_settings(data.get("topic_tag_notes"))
        if isinstance(data, dict)
        else {},
        media_mode=media_mode,  # type: ignore[arg-type]
        video_format=video_format,
        model_execution_mode=model_execution_mode,
        models_storage_mode=models_storage_mode,  # type: ignore[arg-type]
        models_external_path=models_external_path,
        api_models=api_models,
        api_openai_key=str(data.get("api_openai_key", "")) if isinstance(data, dict) else "",
        api_replicate_token=str(data.get("api_replicate_token", "")) if isinstance(data, dict) else "",
        prefer_gpu=bool(data.get("prefer_gpu", True)) if isinstance(data, dict) else True,
        try_llm_4bit=bool(data.get("try_llm_4bit", True)) if isinstance(data, dict) else True,
        try_sdxl_turbo=bool(data.get("try_sdxl_turbo", True)) if isinstance(data, dict) else True,
        script_quant_mode=script_q,  # type: ignore[arg-type]
        image_quant_mode=image_q,  # type: ignore[arg-type]
        video_quant_mode=video_q,  # type: ignore[arg-type]
        voice_quant_mode=voice_q,  # type: ignore[arg-type]
        auto_quant_downgrade_on_failure=bool(data.get("auto_quant_downgrade_on_failure", True))
        if isinstance(data, dict)
        else True,
        background_music_path=str(data.get("background_music_path", "")) if isinstance(data, dict) else "",
        hf_token=str(data.get("hf_token", "")) if isinstance(data, dict) else "",
        hf_api_enabled=bool(data.get("hf_api_enabled", True)) if isinstance(data, dict) else True,
        firecrawl_enabled=bool(data.get("firecrawl_enabled", False)) if isinstance(data, dict) else False,
        firecrawl_api_key=str(data.get("firecrawl_api_key", "")) if isinstance(data, dict) else "",
        elevenlabs_enabled=bool(data.get("elevenlabs_enabled", False)) if isinstance(data, dict) else False,
        elevenlabs_api_key=str(data.get("elevenlabs_api_key", "")) if isinstance(data, dict) else "",
        personality_id=str(data.get("personality_id", "auto")) if isinstance(data, dict) else "auto",
        art_style_preset_id=str(data.get("art_style_preset_id", "balanced") or "balanced")
        if isinstance(data, dict)
        else "balanced",
        active_character_id=str(data.get("active_character_id", "")) if isinstance(data, dict) else "",
        auto_save_generated_cast=bool(data.get("auto_save_generated_cast", True))
        if isinstance(data, dict)
        else True,
        run_content_mode=_norm_run_content_mode(data.get("run_content_mode")) if isinstance(data, dict) else "preset",  # type: ignore[arg-type]
        custom_video_instructions=_sanitize_custom_instructions(data.get("custom_video_instructions"))
        if isinstance(data, dict)
        else "",
        llm_model_id=str(data.get("llm_model_id", "")) if isinstance(data, dict) else "",
        image_model_id=str(data.get("image_model_id", "")) if isinstance(data, dict) else "",
        video_model_id=str(data.get("video_model_id", "")) if isinstance(data, dict) else "",
        voice_model_id=str(data.get("voice_model_id", "")) if isinstance(data, dict) else "",
        allow_nsfw=bool(data.get("allow_nsfw", False)) if isinstance(data, dict) else False,
        video=video,
        picture=picture,
        branding=branding,
        tiktok_enabled=bool(data.get("tiktok_enabled", False)) if isinstance(data, dict) else False,
        tiktok_client_key=str(data.get("tiktok_client_key", "")) if isinstance(data, dict) else "",
        tiktok_client_secret=str(data.get("tiktok_client_secret", "")) if isinstance(data, dict) else "",
        tiktok_redirect_uri=str(data.get("tiktok_redirect_uri", "http://127.0.0.1:8765/callback/"))
        if isinstance(data, dict)
        else "http://127.0.0.1:8765/callback/",
        tiktok_oauth_port=int(data.get("tiktok_oauth_port", 8765)) if isinstance(data, dict) else 8765,
        tiktok_access_token=str(data.get("tiktok_access_token", "")) if isinstance(data, dict) else "",
        tiktok_refresh_token=str(data.get("tiktok_refresh_token", "")) if isinstance(data, dict) else "",
        tiktok_token_expires_at=float(data.get("tiktok_token_expires_at") or 0) if isinstance(data, dict) else 0.0,
        tiktok_open_id=str(data.get("tiktok_open_id", "")) if isinstance(data, dict) else "",
        tiktok_publishing_mode=str(data.get("tiktok_publishing_mode", "inbox"))
        if isinstance(data, dict) and str(data.get("tiktok_publishing_mode")) in ("inbox", "direct")
        else "inbox",
        tiktok_auto_upload_after_render=bool(data.get("tiktok_auto_upload_after_render", False))
        if isinstance(data, dict)
        else False,
        youtube_enabled=bool(data.get("youtube_enabled", False)) if isinstance(data, dict) else False,
        youtube_client_id=str(data.get("youtube_client_id", "")) if isinstance(data, dict) else "",
        youtube_client_secret=str(data.get("youtube_client_secret", "")) if isinstance(data, dict) else "",
        youtube_redirect_uri=str(data.get("youtube_redirect_uri", "") or "http://127.0.0.1:8888/callback/")
        if isinstance(data, dict)
        else "http://127.0.0.1:8888/callback/",
        youtube_oauth_port=int(data.get("youtube_oauth_port", 8888)) if isinstance(data, dict) else 8888,
        youtube_access_token=str(data.get("youtube_access_token", "")) if isinstance(data, dict) else "",
        youtube_refresh_token=str(data.get("youtube_refresh_token", "")) if isinstance(data, dict) else "",
        youtube_token_expires_at=float(data.get("youtube_token_expires_at") or 0) if isinstance(data, dict) else 0.0,
        youtube_privacy_status=str(data.get("youtube_privacy_status", "private"))
        if isinstance(data, dict) and str(data.get("youtube_privacy_status")) in ("public", "unlisted", "private")
        else "private",
        youtube_add_shorts_hashtag=bool(data.get("youtube_add_shorts_hashtag", True)) if isinstance(data, dict) else True,
        youtube_auto_upload_after_render=bool(data.get("youtube_auto_upload_after_render", False))
        if isinstance(data, dict)
        else False,
        tutorial_completed=bool(data.get("tutorial_completed", False)) if isinstance(data, dict) else False,
        gpu_selection_mode=_norm_gpu_selection_mode(data.get("gpu_selection_mode")) if isinstance(data, dict) else "auto",
        gpu_device_index=int(data.get("gpu_device_index", 0)) if isinstance(data, dict) else 0,
        multi_gpu_shard_mode=(
            _norm_multi_gpu_shard_mode(data.get("multi_gpu_shard_mode")) if isinstance(data, dict) else "off"
        ),
        resource_graph_monitor_gpu_index=(
            int(data["resource_graph_monitor_gpu_index"])
            if isinstance(data, dict)
            and data.get("resource_graph_monitor_gpu_index") is not None
            and str(data.get("resource_graph_monitor_gpu_index", "")).strip().lstrip("-").isdigit()
            else None
        ),
        resource_graph_split_view=bool(data.get("resource_graph_split_view", False)) if isinstance(data, dict) else False,
        resource_graph_compact=bool(data.get("resource_graph_compact", True)) if isinstance(data, dict) else True,
        skip_cuda_cpu_torch_mismatch_prompt=bool(data.get("skip_cuda_cpu_torch_mismatch_prompt", False))
        if isinstance(data, dict)
        else False,
    )


def save_settings(settings: AppSettings) -> bool:
    """
    Persist settings to ``ui_settings.json``. Uses a temp file + ``os.replace`` (atomic on Windows)
    and retries on ``PermissionError`` (OneDrive, antivirus, or another Aquaduct instance).

    Returns True if the file was written; False if all attempts failed (callers can continue in-memory).
    """
    from debug import dprint

    p = settings_path()
    d = asdict(settings)
    for k in (
        "resource_retry_resolution_scale",
        "resource_retry_frames_scale",
        "recovery_swapped_voice_model_id",
        "recovery_swapped_video_model_id",
        "recovery_swapped_image_model_id",
        "resume_partial_project_directory",
        "_force_cpu_diffusion",
    ):
        d.pop(k, None)
    payload = json.dumps(d, indent=2, ensure_ascii=False)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        dprint("config", "save_settings", f"mkdir failed: {e}")
        return False

    tmp = p.parent / f".ui_settings_{os.getpid()}.tmp"
    last_err: BaseException | None = None
    for attempt in range(6):
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, p)
            try:
                mark_path_hidden(p)
            except Exception:
                pass
            dprint("config", "save_settings", str(p))
            return True
        except (PermissionError, OSError) as e:
            last_err = e
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            if attempt < 5:
                time.sleep(0.05 * (2**attempt))
    dprint("config", "save_settings", f"FAILED after retries: {last_err!r}")
    return False

