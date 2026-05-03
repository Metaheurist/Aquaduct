"""Rehydrate frozen series ``AppSettings`` snapshots with live credentials."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.core.config import AppSettings
from src.settings.ui_settings import app_settings_from_dict
from src.series.store import strip_lock_first_from_snapshot

_EPHEMERAL_FROM_LIVE: tuple[str, ...] = (
    "hf_token",
    "hf_api_enabled",
    "api_openai_key",
    "api_replicate_token",
    "api_models",
    "firecrawl_enabled",
    "firecrawl_api_key",
    "elevenlabs_enabled",
    "elevenlabs_api_key",
    "tiktok_access_token",
    "tiktok_refresh_token",
    "tiktok_token_expires_at",
    "tiktok_open_id",
    "youtube_access_token",
    "youtube_refresh_token",
    "youtube_token_expires_at",
)


def rehydrate_settings_from_series_snapshot(*, live: AppSettings, snapshot: dict[str, Any]) -> AppSettings:
    """Build ``AppSettings`` from a series JSON snapshot; overlay secrets from ``live`` UI settings."""
    cleaned = strip_lock_first_from_snapshot(snapshot)
    base = app_settings_from_dict(cleaned)
    patch = {k: getattr(live, k) for k in _EPHEMERAL_FROM_LIVE if hasattr(live, k)}
    return replace(base, **patch)


def merge_unlocked_style_from_live(*, base: AppSettings, live: AppSettings) -> AppSettings:
    """When ``lock_style`` is off, overlay visual/voice/model choices from the live UI."""
    return replace(
        base,
        art_style_preset_id=live.art_style_preset_id,
        image_model_id=live.image_model_id,
        video_model_id=live.video_model_id,
        voice_model_id=live.voice_model_id,
        llm_model_id=live.llm_model_id,
        branding=live.branding,
        active_character_id=live.active_character_id,
        personality_id=live.personality_id,
    )
