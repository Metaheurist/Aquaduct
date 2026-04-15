from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import AppSettings, VideoSettings


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


def load_settings() -> AppSettings:
    p = settings_path()
    if not p.exists():
        return AppSettings(topic_tags=[])
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings(topic_tags=[])

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
    )

    return AppSettings(
        topic_tags=_sanitize_tags(data.get("topic_tags", [])) if isinstance(data, dict) else [],
        prefer_gpu=bool(data.get("prefer_gpu", True)) if isinstance(data, dict) else True,
        try_llm_4bit=bool(data.get("try_llm_4bit", True)) if isinstance(data, dict) else True,
        try_sdxl_turbo=bool(data.get("try_sdxl_turbo", True)) if isinstance(data, dict) else True,
        background_music_path=str(data.get("background_music_path", "")) if isinstance(data, dict) else "",
        llm_model_id=str(data.get("llm_model_id", "")) if isinstance(data, dict) else "",
        image_model_id=str(data.get("image_model_id", "")) if isinstance(data, dict) else "",
        video_model_id=str(data.get("video_model_id", "")) if isinstance(data, dict) else "",
        voice_model_id=str(data.get("voice_model_id", "")) if isinstance(data, dict) else "",
        video=video,
    )


def save_settings(settings: AppSettings) -> None:
    p = settings_path()
    payload = asdict(settings)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

