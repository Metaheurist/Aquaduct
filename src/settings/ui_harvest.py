"""Harvest :class:`AppSettings` from the main window widgets."""
from __future__ import annotations

from typing import Any

from dataclasses import replace

from UI.services.brain_expand import script_llm_model_id_from_ui
from src.content.topic_constraints import sanitize_topic_tag_notes
from src.content.topics import normalize_video_format
from src.core.config import (
    MAX_CUSTOM_VIDEO_INSTRUCTIONS,
    ApiModelRuntimeSettings,
    ApiRoleConfig,
    AppSettings,
    BrandingSettings,
    PictureSettings,
    SeriesSettings,
    VideoSettings,
    default_api_models,
)


def collect_settings_from_ui(win: Any) -> AppSettings:

        if hasattr(win, "topics_mode_combo"):
            win._flush_topic_list_to_mode(str(win.topics_mode_combo.currentData() or "news"))

        fmt = (win.settings.video.width, win.settings.video.height)
        if hasattr(win, "format_combo"):
            try:
                d = win.format_combo.currentData()
                if isinstance(d, tuple) and len(d) == 2:
                    fmt = (int(d[0]), int(d[1]))
            except Exception:
                pass

        video = VideoSettings(
            width=int(fmt[0]),
            height=int(fmt[1]),
            fps=int(win.fps_spin.value()),
            microclip_min_s=float(win.min_clip_spin.value()),
            microclip_max_s=float(win.max_clip_spin.value()),
            music_volume=win.settings.video.music_volume,
            voice_volume=win.settings.video.voice_volume,
            images_per_video=int(win.images_spin.value()),
            export_microclips=bool(win.export_microclips_chk.isChecked()),
            bitrate_preset=win.bitrate_combo.currentText(),  # type: ignore[arg-type]
            # Video mode is always Pro; slideshow is disabled.
            use_image_slideshow=False,
            pro_mode=True,
            pro_clip_seconds=float(win.pro_clip_seconds_spin.value()) if hasattr(win, "pro_clip_seconds_spin") else 4.0,
            clips_per_video=int(win.clips_spin.value()) if hasattr(win, "clips_spin") else 3,
            clip_seconds=float(win.clip_seconds_spin.value()) if hasattr(win, "clip_seconds_spin") else 4.0,
            cleanup_images_after_run=bool(win.cleanup_images_chk.isChecked()) if hasattr(win, "cleanup_images_chk") else False,
            high_quality_topic_selection=bool(win.hq_topics_chk.isChecked()) if hasattr(win, "hq_topics_chk") else True,
            fetch_article_text=bool(win.fetch_article_chk.isChecked()) if hasattr(win, "fetch_article_chk") else True,
            llm_factcheck=bool(getattr(win.settings.video, "llm_factcheck", True)),
            prompt_conditioning=bool(win.prompt_cond_chk.isChecked()) if hasattr(win, "prompt_cond_chk") else True,
            story_multistage_enabled=bool(win.story_multistage_chk.isChecked()) if hasattr(win, "story_multistage_chk") else False,
            story_web_context=bool(win.story_web_chk.isChecked()) if hasattr(win, "story_web_chk") else False,
            story_reference_images=bool(win.story_refimg_chk.isChecked()) if hasattr(win, "story_refimg_chk") else False,
            resume_partial_pipeline=bool(win.resume_partial_chk.isChecked()) if hasattr(win, "resume_partial_chk") else False,
            seed_base=int(str(win.seed_base_input.text()).strip())
            if hasattr(win, "seed_base_input") and str(win.seed_base_input.text()).strip().lstrip("-").isdigit()
            else None,
            quality_retries=int(win.quality_retries_spin.value()) if hasattr(win, "quality_retries_spin") else 2,
            enable_motion=bool(win.enable_motion_chk.isChecked()) if hasattr(win, "enable_motion_chk") else True,
            transition_strength=str(win.transition_combo.currentData() or "low") if hasattr(win, "transition_combo") else "low",
            xfade_transition=str(win.xfade_transition_combo.currentData() or "fade")
            if hasattr(win, "xfade_transition_combo")
            else str(getattr(win.settings.video, "xfade_transition", "fade") or "fade"),
            audio_polish=str(win.audio_polish_combo.currentData() or "basic") if hasattr(win, "audio_polish_combo") else "basic",
            music_ducking=bool(win.music_ducking_chk.isChecked()) if hasattr(win, "music_ducking_chk") else True,
            music_ducking_amount=float(win.ducking_spin.value()) / 100.0 if hasattr(win, "ducking_spin") else float(getattr(win.settings.video, "music_ducking_amount", 0.7)),
            music_fade_s=float(win.music_fade_spin.value()) if hasattr(win, "music_fade_spin") else 1.2,
            sfx_mode=str(win.sfx_combo.currentData() or "off") if hasattr(win, "sfx_combo") else "off",
            captions_enabled=bool(win.captions_enabled_chk.isChecked()) if hasattr(win, "captions_enabled_chk") else True,
            caption_highlight_intensity=str(win.caption_highlight_combo.currentData() or "strong")
            if hasattr(win, "caption_highlight_combo")
            else "strong",
            caption_max_words=int(win.caption_max_words_spin.value()) if hasattr(win, "caption_max_words_spin") else 8,
            caption_vertical_anchor=str(win.caption_vertical_combo.currentData() or "bottom")
            if hasattr(win, "caption_vertical_combo")
            else str(getattr(win.settings.video, "caption_vertical_anchor", "bottom") or "bottom"),
            facts_card_enabled=bool(win.facts_card_chk.isChecked()) if hasattr(win, "facts_card_chk") else True,
            facts_card_position=str(win.facts_card_pos_combo.currentData() or "top_left")
            if hasattr(win, "facts_card_pos_combo")
            else "top_left",
            facts_card_duration=str(win.facts_card_dur_combo.currentData() or "short")
            if hasattr(win, "facts_card_dur_combo")
            else "short",
            platform_preset_id=(
                str(getattr(win, "_video_platform_preset_id", "") or "").strip()
                if hasattr(win, "_video_platform_preset_id")
                else str(getattr(win.settings.video, "platform_preset_id", "") or "")
            ),
            effects_preset_id=(
                str(getattr(win, "_effects_preset_id", "") or "").strip()
                if hasattr(win, "_effects_preset_id")
                else str(getattr(win.settings.video, "effects_preset_id", "") or "")
            ),
            smoothness_mode=(
                str(win.video_smoothness_combo.currentData() or "off")
                if hasattr(win, "video_smoothness_combo")
                else str(getattr(win.settings.video, "smoothness_mode", "off") or "off")
            ),
            smoothness_target_fps=int(getattr(win.settings.video, "smoothness_target_fps", 24) or 24),
            spatial_upscale_mode=(
                str(win.video_spatial_upscale_combo.currentData() or "off")
                if hasattr(win, "video_spatial_upscale_combo")
                else str(getattr(win.settings.video, "spatial_upscale_mode", "off") or "off")
            ),
            video_length_preset_id=(
                str(win.video_length_preset_combo.currentData() or "medium")
                if hasattr(win, "video_length_preset_combo")
                else str(getattr(win.settings.video, "video_length_preset_id", "medium") or "medium")
            ),
            video_scene_preset_id=(
                str(win.video_scene_preset_combo.currentData() or "balanced")
                if hasattr(win, "video_scene_preset_combo")
                else str(getattr(win.settings.video, "video_scene_preset_id", "balanced") or "balanced")
            ),
            video_fps_preset_id=(
                str(win.video_fps_preset_combo.currentData() or "standard_30")
                if hasattr(win, "video_fps_preset_combo")
                else str(getattr(win.settings.video, "video_fps_preset_id", "standard_30") or "standard_30")
            ),
            video_resolution_preset_id=(
                str(win.video_resolution_preset_combo.currentData() or "vertical_1080p")
                if hasattr(win, "video_resolution_preset_combo")
                else str(getattr(win.settings.video, "video_resolution_preset_id", "vertical_1080p") or "vertical_1080p")
            ),
            article_relevance_screen=bool(getattr(win.settings.video, "article_relevance_screen", True)),
        )

        branding = getattr(win.settings, "branding", BrandingSettings())
        if hasattr(win, "brand_theme_enable") and hasattr(win, "brand_palette_combo"):
            try:
                branding = BrandingSettings(
                    theme_enabled=bool(win.brand_theme_enable.isChecked()),
                    palette_id=str(win.brand_palette_combo.currentData() or "default"),
                    bg_enabled=bool(win.brand_bg_chk.isChecked()) if hasattr(win, "brand_bg_chk") else False,
                    bg_hex=str(win.brand_bg_hex.text()).strip() if hasattr(win, "brand_bg_hex") else branding.bg_hex,
                    panel_enabled=bool(win.brand_panel_chk.isChecked()) if hasattr(win, "brand_panel_chk") else False,
                    panel_hex=str(win.brand_panel_hex.text()).strip() if hasattr(win, "brand_panel_hex") else branding.panel_hex,
                    text_enabled=bool(win.brand_text_chk.isChecked()) if hasattr(win, "brand_text_chk") else False,
                    text_hex=str(win.brand_text_hex.text()).strip() if hasattr(win, "brand_text_hex") else branding.text_hex,
                    muted_enabled=bool(win.brand_muted_chk.isChecked()) if hasattr(win, "brand_muted_chk") else False,
                    muted_hex=str(win.brand_muted_hex.text()).strip() if hasattr(win, "brand_muted_hex") else branding.muted_hex,
                    accent_enabled=bool(win.brand_accent_chk.isChecked()) if hasattr(win, "brand_accent_chk") else False,
                    accent_hex=str(win.brand_accent_hex.text()).strip() if hasattr(win, "brand_accent_hex") else branding.accent_hex,
                    danger_enabled=bool(win.brand_danger_chk.isChecked()) if hasattr(win, "brand_danger_chk") else False,
                    danger_hex=str(win.brand_danger_hex.text()).strip() if hasattr(win, "brand_danger_hex") else branding.danger_hex,
                    watermark_enabled=bool(win.brand_watermark_enable.isChecked())
                    if hasattr(win, "brand_watermark_enable")
                    else bool(getattr(branding, "watermark_enabled", False)),
                    watermark_path=str(win.brand_watermark_path.text()).strip()
                    if hasattr(win, "brand_watermark_path")
                    else str(getattr(branding, "watermark_path", "")),
                    watermark_opacity=float(win.brand_watermark_opacity.value()) / 100.0
                    if hasattr(win, "brand_watermark_opacity")
                    else float(getattr(branding, "watermark_opacity", 0.22)),
                    watermark_scale=float(win.brand_watermark_scale.value()) / 100.0
                    if hasattr(win, "brand_watermark_scale")
                    else float(getattr(branding, "watermark_scale", 0.18)),
                    watermark_position=str(win.brand_watermark_pos.currentData() or "top_right")
                    if hasattr(win, "brand_watermark_pos")
                    else str(getattr(branding, "watermark_position", "top_right")),
                    video_style_enabled=bool(win.brand_video_style_enable.isChecked())
                    if hasattr(win, "brand_video_style_enable")
                    else bool(getattr(branding, "video_style_enabled", False)),
                    video_style_strength=str(win.brand_video_style_strength.currentData() or "subtle")
                    if hasattr(win, "brand_video_style_strength")
                    else str(getattr(branding, "video_style_strength", "subtle")),
                    photo_style_enabled=bool(win.brand_photo_style_enable.isChecked())
                    if hasattr(win, "brand_photo_style_enable")
                    else bool(getattr(branding, "photo_style_enabled", False)),
                    photo_frame_enabled=bool(win.brand_photo_frame_enable.isChecked())
                    if hasattr(win, "brand_photo_frame_enable")
                    else bool(getattr(branding, "photo_frame_enabled", False)),
                    photo_frame_width=int(win.brand_photo_frame_width.value())
                    if hasattr(win, "brand_photo_frame_width")
                    else int(getattr(branding, "photo_frame_width", 24)),
                    photo_paper_hex=str(win.brand_photo_paper_hex.text()).strip()
                    if hasattr(win, "brand_photo_paper_hex")
                    else str(getattr(branding, "photo_paper_hex", "#F2F0E9") or "#F2F0E9"),
                )
            except Exception:
                branding = getattr(win.settings, "branding", BrandingSettings())

        image_model_id = (
            str(win.img_combo.currentData()) if hasattr(win, "img_combo") else str(getattr(win.settings, "image_model_id", "") or "")
        )
        video_model_id = (
            str(win.vid_combo.currentData()) if hasattr(win, "vid_combo") else str(getattr(win.settings, "video_model_id", "") or "")
        )

        hf_tok = (
            str(win.api_hf_token_edit.text()).strip()
            if hasattr(win, "api_hf_token_edit")
            else str(getattr(win.settings, "hf_token", "") or "")
        )
        hf_en = (
            bool(win.api_hf_enabled_chk.isChecked())
            if hasattr(win, "api_hf_enabled_chk")
            else bool(getattr(win.settings, "hf_api_enabled", True))
        )
        fc_en = (
            bool(win.api_fc_enabled_chk.isChecked())
            if hasattr(win, "api_fc_enabled_chk")
            else bool(getattr(win.settings, "firecrawl_enabled", False))
        )
        fc_key = (
            str(win.api_fc_key_edit.text()).strip()
            if hasattr(win, "api_fc_key_edit")
            else str(getattr(win.settings, "firecrawl_api_key", "") or "")
        )
        el_en = (
            bool(win.api_el_enabled_chk.isChecked())
            if hasattr(win, "api_el_enabled_chk")
            else bool(getattr(win.settings, "elevenlabs_enabled", False))
        )
        el_key = (
            str(win.api_el_key_edit.text()).strip()
            if hasattr(win, "api_el_key_edit")
            else str(getattr(win.settings, "elevenlabs_api_key", "") or "")
        )

        tt_en = bool(win.api_tt_enabled_chk.isChecked()) if hasattr(win, "api_tt_enabled_chk") else bool(getattr(win.settings, "tiktok_enabled", False))
        tt_ck = str(win.api_tt_client_key.text()).strip() if hasattr(win, "api_tt_client_key") else str(getattr(win.settings, "tiktok_client_key", "") or "")
        tt_cs = str(win.api_tt_client_secret.text()).strip() if hasattr(win, "api_tt_client_secret") else str(getattr(win.settings, "tiktok_client_secret", "") or "")
        tt_ru = str(win.api_tt_redirect_uri.text()).strip() if hasattr(win, "api_tt_redirect_uri") else str(getattr(win.settings, "tiktok_redirect_uri", "") or "")
        tt_port = int(win.api_tt_oauth_port.value()) if hasattr(win, "api_tt_oauth_port") else int(getattr(win.settings, "tiktok_oauth_port", 8765))
        tt_at = str(win.settings.tiktok_access_token or "")  # refreshed via worker / OAuth only
        tt_rt = str(win.settings.tiktok_refresh_token or "")
        tt_exp = float(getattr(win.settings, "tiktok_token_expires_at", 0.0) or 0.0)
        tt_oid = str(getattr(win.settings, "tiktok_open_id", "") or "")
        tt_mode = (
            str(win.api_tt_pub_mode.currentData() or "inbox") if hasattr(win, "api_tt_pub_mode") else str(getattr(win.settings, "tiktok_publishing_mode", "inbox"))
        )
        if tt_mode not in ("inbox", "direct"):
            tt_mode = "inbox"
        tt_auto = bool(win.api_tt_auto_upload_chk.isChecked()) if hasattr(win, "api_tt_auto_upload_chk") else bool(getattr(win.settings, "tiktok_auto_upload_after_render", False))

        yt_en = bool(win.api_yt_enabled_chk.isChecked()) if hasattr(win, "api_yt_enabled_chk") else bool(getattr(win.settings, "youtube_enabled", False))
        yt_cid = str(win.api_yt_client_id.text()).strip() if hasattr(win, "api_yt_client_id") else str(getattr(win.settings, "youtube_client_id", "") or "")
        yt_sec = str(win.api_yt_client_secret.text()).strip() if hasattr(win, "api_yt_client_secret") else str(getattr(win.settings, "youtube_client_secret", "") or "")
        yt_ru = str(win.api_yt_redirect_uri.text()).strip() if hasattr(win, "api_yt_redirect_uri") else str(getattr(win.settings, "youtube_redirect_uri", "") or "")
        yt_port = int(win.api_yt_oauth_port.value()) if hasattr(win, "api_yt_oauth_port") else int(getattr(win.settings, "youtube_oauth_port", 8888))
        yt_at = str(win.settings.youtube_access_token or "")
        yt_rt = str(win.settings.youtube_refresh_token or "")
        yt_exp = float(getattr(win.settings, "youtube_token_expires_at", 0.0) or 0.0)
        yt_priv = (
            str(win.api_yt_privacy.currentData() or "private") if hasattr(win, "api_yt_privacy") else str(getattr(win.settings, "youtube_privacy_status", "private"))
        )
        if yt_priv not in ("public", "unlisted", "private"):
            yt_priv = "private"
        yt_shorts_tag = bool(win.api_yt_shorts_tag_chk.isChecked()) if hasattr(win, "api_yt_shorts_tag_chk") else bool(getattr(win.settings, "youtube_add_shorts_hashtag", True))
        yt_auto = bool(win.api_yt_auto_upload_chk.isChecked()) if hasattr(win, "api_yt_auto_upload_chk") else bool(getattr(win.settings, "youtube_auto_upload_after_render", False))

        vfmt = (
            normalize_video_format(str(win.video_format_combo.currentData() or "news"))
            if hasattr(win, "video_format_combo")
            else normalize_video_format(str(getattr(win.settings, "video_format", "news")))
        )
        topic_map = {str(k): list(v) for k, v in (win.settings.topic_tags_by_mode or {}).items()}

        mex = (
            str(win.model_execution_mode_combo.currentData() or "local")
            if hasattr(win, "model_execution_mode_combo")
            else str(getattr(win.settings, "model_execution_mode", "local") or "local")
        )
        if mex not in ("local", "api"):
            mex = "local"
        msm = (
            str(win.models_storage_mode_combo.currentData() or "default")
            if hasattr(win, "models_storage_mode_combo")
            else str(getattr(win.settings, "models_storage_mode", "default") or "default")
        )
        if msm not in ("default", "external"):
            msm = "default"
        mext = (
            str(win.models_external_path_edit.text()).strip()
            if hasattr(win, "models_external_path_edit")
            else str(getattr(win.settings, "models_external_path", "") or "")
        )
        api_openai_key = (
            str(win.api_gen_openai_key.text()).strip()
            if hasattr(win, "api_gen_openai_key")
            else str(getattr(win.settings, "api_openai_key", "") or "")
        )
        api_replicate_token = (
            str(win.api_gen_replicate_token.text()).strip()
            if hasattr(win, "api_gen_replicate_token")
            else str(getattr(win.settings, "api_replicate_token", "") or "")
        )
        if hasattr(win, "api_gen_llm_provider"):
            api_models = ApiModelRuntimeSettings(
                llm=ApiRoleConfig(
                    provider=str(win.api_gen_llm_provider.currentData() or "").strip(),
                    model=str(win.api_gen_llm_model.currentText() or "").strip(),
                    base_url=str(win.api_gen_llm_base.text()).strip() if hasattr(win, "api_gen_llm_base") else "",
                    org_id=str(win.api_gen_llm_org.text()).strip() if hasattr(win, "api_gen_llm_org") else "",
                    voice_id="",
                ),
                image=ApiRoleConfig(
                    provider=str(win.api_gen_image_provider.currentData() or "").strip(),
                    model=str(win.api_gen_image_model.currentText() or "").strip(),
                ),
                video=ApiRoleConfig(
                    provider=str(win.api_gen_video_provider.currentData() or "").strip(),
                    model=str(win.api_gen_video_model.currentText() or "").strip(),
                ),
                voice=ApiRoleConfig(
                    provider=str(win.api_gen_voice_provider.currentData() or "").strip(),
                    model=str(win.api_gen_voice_model.currentText() or "").strip(),
                    voice_id=str(win.api_gen_voice_id.text()).strip() if hasattr(win, "api_gen_voice_id") else "",
                ),
            )
        else:
            api_models = getattr(win.settings, "api_models", None) or default_api_models()

        mm = (
            str(win.media_mode_toggle.currentData() or "video").strip()
            if hasattr(win, "media_mode_toggle")
            else str(getattr(win.settings, "media_mode", "video") or "video").strip()
        )
        if mm not in ("video", "photo"):
            mm = "video"

        pic = getattr(win.settings, "picture", PictureSettings())
        try:
            if hasattr(win, "picture_template_combo"):
                d = win.picture_template_combo.currentData()
                if isinstance(d, tuple) and len(d) == 3:
                    pic = replace(pic, template_id=str(d[0]), width=int(d[1]), height=int(d[2]))
            if hasattr(win, "picture_output_type_combo"):
                pic = replace(pic, output_type=str(win.picture_output_type_combo.currentData() or "single_image"))  # type: ignore[arg-type]
            if hasattr(win, "picture_count_spin"):
                pic = replace(pic, image_count=int(win.picture_count_spin.value()))
            if hasattr(win, "picture_format_combo"):
                pic = replace(pic, picture_format=str(win.picture_format_combo.currentData() or "poster"))  # type: ignore[arg-type]
        except Exception:
            pic = getattr(win.settings, "picture", PictureSettings())

        if hasattr(win, "gpu_policy_toggle"):
            _gpu_mode = str(win.gpu_policy_toggle.currentData() or "auto")
        else:
            _gpu_mode = str(getattr(win.settings, "gpu_selection_mode", "auto") or "auto")
        _gpu_mode = (_gpu_mode or "auto").strip().lower()
        if _gpu_mode not in ("auto", "single"):
            _gpu_mode = "auto"
        _gpu_dev_idx = (
            int(win.gpu_device_combo.currentData())
            if hasattr(win, "gpu_device_combo") and win.gpu_device_combo.currentData() is not None
            else int(getattr(win.settings, "gpu_device_index", 0) or 0)
        )
        if hasattr(win, "multi_gpu_shard_combo") and win.multi_gpu_shard_combo.currentData() is not None:
            _mgsm = str(win.multi_gpu_shard_combo.currentData() or "off").strip().lower()
        else:
            _mgsm = str(getattr(win.settings, "multi_gpu_shard_mode", "off") or "off").strip().lower()
        if _mgsm not in ("off", "vram_first_auto"):
            _mgsm = "off"
        _rg_mon = getattr(win.settings, "resource_graph_monitor_gpu_index", None)
        _rg_split = bool(getattr(win.settings, "resource_graph_split_view", False))
        _rg_compact = bool(getattr(win.settings, "resource_graph_compact", True))

        def _quant_mode_from_ui(role_key: str, prefix: str, settings_attr: str) -> str:
            auto_chk = getattr(win, f"{prefix}_quant_auto_chk", None)
            slider = getattr(win, f"{prefix}_quant_slider", None)
            if auto_chk is None or slider is None:
                return str(getattr(win.settings, settings_attr, "auto") or "auto")
            modes = (getattr(win, "_quant_manual_modes", {}) or {}).get(role_key) or ()
            try:
                if auto_chk.isChecked() or not modes:
                    return "auto"
                i = max(0, min(int(slider.value()), len(modes) - 1))
                return str(modes[i])
            except Exception:
                return str(getattr(win.settings, settings_attr, "auto") or "auto")

        script_q = _quant_mode_from_ui("script", "llm", "script_quant_mode")
        image_q = _quant_mode_from_ui("image", "img", "image_quant_mode")
        video_q = _quant_mode_from_ui("video", "vid", "video_quant_mode")
        voice_q = _quant_mode_from_ui("voice", "voice", "voice_quant_mode")
        auto_q_down = (
            bool(win.auto_quant_downgrade_on_failure_chk.isChecked())
            if hasattr(win, "auto_quant_downgrade_on_failure_chk")
            else bool(getattr(win.settings, "auto_quant_downgrade_on_failure", False))
        )

        topic_notes_out = sanitize_topic_tag_notes(win._merge_topic_notes_edits_into_dict())

        _ser0 = getattr(win.settings, "series", None)
        _qty_spin = max(1, int(win.run_qty_spin.value()) if hasattr(win, "run_qty_spin") else 1)
        _ser_mode_ui = bool(win.series_mode_check.isChecked()) if hasattr(win, "series_mode_check") else bool(getattr(_ser0, "series_mode", False))
        _ss = (
            str(win.series_source_strategy_combo.currentData() or "auto")
            if hasattr(win, "series_source_strategy_combo")
            else str(getattr(_ser0, "source_strategy", "auto") or "auto")
        )
        if _ss not in ("auto", "lock_first", "fresh_per_ep"):
            _ss = "auto"
        series_out = SeriesSettings(
            series_mode=_ser_mode_ui and mm == "video",
            series_name=(
                str(win.series_name_edit.text()).strip()
                if hasattr(win, "series_name_edit")
                else str(getattr(_ser0, "series_name", "") or "")
            ),
            episode_count=_qty_spin if _ser_mode_ui and mm == "video" else 1,
            lock_style=(
                bool(win.series_lock_style_check.isChecked())
                if hasattr(win, "series_lock_style_check")
                else bool(getattr(_ser0, "lock_style", True))
            ),
            carry_recap=(
                bool(win.series_carry_recap_check.isChecked())
                if hasattr(win, "series_carry_recap_check")
                else bool(getattr(_ser0, "carry_recap", True))
            ),
            source_strategy=_ss,  # type: ignore[arg-type]
            continue_on_failure=(
                bool(win.series_continue_on_failure_check.isChecked())
                if hasattr(win, "series_continue_on_failure_check")
                else bool(getattr(_ser0, "continue_on_failure", False))
            ),
        )
        if mm != "video":
            series_out = replace(series_out, series_mode=False, episode_count=1)

        return AppSettings(
            topic_tags_by_mode=topic_map,
            topic_tag_notes=topic_notes_out,
            media_mode=mm,  # type: ignore[arg-type]
            video_format=vfmt,
            model_execution_mode=mex,  # type: ignore[arg-type]
            models_storage_mode=msm,  # type: ignore[arg-type]
            models_external_path=mext,
            api_models=api_models,
            api_openai_key=api_openai_key,
            api_replicate_token=api_replicate_token,
            prefer_gpu=bool(win.prefer_gpu_chk.isChecked()) if hasattr(win, "prefer_gpu_chk") else bool(getattr(win.settings, "prefer_gpu", True)),
            try_llm_4bit=bool(getattr(win.settings, "try_llm_4bit", True)),
            try_sdxl_turbo=bool(getattr(win.settings, "try_sdxl_turbo", True)),
            script_quant_mode=script_q,  # type: ignore[arg-type]
            image_quant_mode=image_q,  # type: ignore[arg-type]
            video_quant_mode=video_q,  # type: ignore[arg-type]
            voice_quant_mode=voice_q,  # type: ignore[arg-type]
            auto_quant_downgrade_on_failure=auto_q_down,
            background_music_path=str(win.music_path.text()).strip(),
            hf_token=hf_tok,
            hf_api_enabled=hf_en,
            firecrawl_enabled=fc_en,
            firecrawl_api_key=fc_key,
            elevenlabs_enabled=el_en,
            elevenlabs_api_key=el_key,
            tiktok_enabled=tt_en,
            tiktok_client_key=tt_ck,
            tiktok_client_secret=tt_cs,
            tiktok_redirect_uri=tt_ru or "http://127.0.0.1:8765/callback/",
            tiktok_oauth_port=tt_port,
            tiktok_access_token=tt_at,
            tiktok_refresh_token=tt_rt,
            tiktok_token_expires_at=tt_exp,
            tiktok_open_id=tt_oid,
            tiktok_publishing_mode=tt_mode,  # type: ignore[arg-type]
            tiktok_auto_upload_after_render=tt_auto,
            youtube_enabled=yt_en,
            youtube_client_id=yt_cid,
            youtube_client_secret=yt_sec,
            youtube_redirect_uri=yt_ru or "http://127.0.0.1:8888/callback/",
            youtube_oauth_port=yt_port,
            youtube_access_token=yt_at,
            youtube_refresh_token=yt_rt,
            youtube_token_expires_at=yt_exp,
            youtube_privacy_status=yt_priv,  # type: ignore[arg-type]
            youtube_add_shorts_hashtag=yt_shorts_tag,
            youtube_auto_upload_after_render=yt_auto,
            tutorial_completed=bool(getattr(win.settings, "tutorial_completed", False)),
            advanced_tabs=dict(getattr(win.settings, "advanced_tabs", None) or {}),
            gpu_selection_mode=_gpu_mode,  # type: ignore[arg-type]
            gpu_device_index=_gpu_dev_idx,
            multi_gpu_shard_mode=_mgsm,  # type: ignore[arg-type]
            resource_graph_monitor_gpu_index=_rg_mon,
            resource_graph_split_view=_rg_split,
            resource_graph_compact=_rg_compact,
            personality_id=str(win.personality_combo.currentData()) if hasattr(win, "personality_combo") else getattr(win.settings, "personality_id", "auto"),
            art_style_preset_id=(
                str(win.art_style_preset_combo.currentData())
                if hasattr(win, "art_style_preset_combo")
                else str(getattr(win.settings, "art_style_preset_id", "balanced") or "balanced")
            ),
            active_character_ids=(
                tuple(win.character_tag_picker.get_ordered_ids())
                if hasattr(win, "character_tag_picker")
                else tuple(getattr(win.settings, "active_character_ids", ()) or ())
            ),
            active_character_id=(
                (win.character_tag_picker.get_ordered_ids()[0] if win.character_tag_picker.get_ordered_ids() else "")
                if hasattr(win, "character_tag_picker")
                else str(win.character_combo.currentData()) if hasattr(win, "character_combo") else str(getattr(win.settings, "active_character_id", "") or "")
            ),
            auto_save_generated_cast=(
                bool(win.auto_save_generated_cast_check.isChecked())
                if hasattr(win, "auto_save_generated_cast_check")
                else bool(getattr(win.settings, "auto_save_generated_cast", True))
            ),
            run_content_mode=(
                "custom"
                if hasattr(win, "run_content_custom_radio") and win.run_content_custom_radio.isChecked()
                else "preset"
            ),
            custom_video_instructions=(
                (win.custom_instructions_edit.toPlainText()[:MAX_CUSTOM_VIDEO_INSTRUCTIONS])
                if hasattr(win, "custom_instructions_edit")
                else str(getattr(win.settings, "custom_video_instructions", "") or "")[:MAX_CUSTOM_VIDEO_INSTRUCTIONS]
            ),
            llm_model_id=script_llm_model_id_from_ui(win),
            image_model_id=image_model_id,
            video_model_id=video_model_id,
            voice_model_id=str(win.voice_combo.currentData()) if hasattr(win, "voice_combo") else win.settings.voice_model_id,
            allow_nsfw=bool(win.allow_nsfw_chk.isChecked()) if hasattr(win, "allow_nsfw_chk") else bool(getattr(win.settings, "allow_nsfw", False)),
            video=video,
            picture=pic,
            branding=branding,
            series=series_out,
        )

