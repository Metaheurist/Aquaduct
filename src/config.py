from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Paths:
    root: Path
    data_dir: Path
    news_cache_dir: Path
    runs_dir: Path
    videos_dir: Path
    models_dir: Path
    cache_dir: Path
    ffmpeg_dir: Path


def get_paths() -> Paths:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    news_cache_dir = data_dir / "news_cache"
    runs_dir = root / "runs"
    videos_dir = root / "videos"
    models_dir = root / "models"
    cache_dir = root / ".cache"
    ffmpeg_dir = cache_dir / "ffmpeg"

    return Paths(
        root=root,
        data_dir=data_dir,
        news_cache_dir=news_cache_dir,
        runs_dir=runs_dir,
        videos_dir=videos_dir,
        models_dir=models_dir,
        cache_dir=cache_dir,
        ffmpeg_dir=ffmpeg_dir,
    )


@dataclass(frozen=True)
class Models:
    llm_id: str
    sdxl_turbo_id: str
    kokoro_id: str


def get_models() -> Models:
    return Models(
        llm_id="meta-llama/Llama-3.2-3B-Instruct",
        sdxl_turbo_id="stabilityai/sdxl-turbo",
        kokoro_id="hexgrad/Kokoro-82M",
    )


@dataclass(frozen=True)
class VideoSettings:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    microclip_min_s: float = 3.5
    microclip_max_s: float = 7.5
    music_volume: float = 0.08
    voice_volume: float = 1.0
    images_per_video: int = 8
    export_microclips: bool = True
    bitrate_preset: Literal["low", "med", "high"] = "med"
    # If true, generate images and stitch into micro-clips (current default).
    # If false, try generating actual video clips using a video model, then concat.
    use_image_slideshow: bool = True
    clips_per_video: int = 3
    clip_seconds: float = 4.0
    cleanup_images_after_run: bool = False
    # Content-quality toggles (v1 defaults on)
    high_quality_topic_selection: bool = True
    fetch_article_text: bool = True
    llm_factcheck: bool = True
    prompt_conditioning: bool = True
    # Visual quality controls
    seed_base: int | None = None
    quality_retries: int = 2
    enable_motion: bool = True
    transition_strength: Literal["off", "low", "med"] = "low"

    # Audio polish (v1)
    audio_polish: Literal["off", "basic", "strong"] = "basic"
    music_ducking: bool = True
    music_ducking_amount: float = 0.7
    music_fade_s: float = 1.2
    sfx_mode: Literal["off", "subtle"] = "off"

    # Captions + on-screen facts (retention / clarity)
    captions_enabled: bool = True
    caption_highlight_intensity: Literal["subtle", "strong"] = "strong"
    caption_max_words: int = 8
    facts_card_enabled: bool = True
    facts_card_position: Literal["top_left", "top_right"] = "top_left"
    facts_card_duration: Literal["short", "long"] = "short"


@dataclass(frozen=True)
class BrandingSettings:
    # Theme (optional overrides)
    theme_enabled: bool = False
    palette_id: str = "default"  # default | tiktok | ocean | sunset | mono | custom

    bg_enabled: bool = False
    bg_hex: str = "#0F0F10"

    panel_enabled: bool = False
    panel_hex: str = "#0B0B0F"

    text_enabled: bool = False
    text_hex: str = "#FFFFFF"

    muted_enabled: bool = False
    muted_hex: str = "#B7B7C2"

    accent_enabled: bool = False
    accent_hex: str = "#25F4EE"

    danger_enabled: bool = False
    danger_hex: str = "#FE2C55"

    # Watermark (optional)
    watermark_enabled: bool = False
    watermark_path: str = ""
    watermark_opacity: float = 0.22
    watermark_scale: float = 0.18  # fraction of output width
    watermark_position: Literal["top_left", "top_right", "bottom_left", "bottom_right", "center"] = "top_right"

    # Video style (optional): apply palette to prompts + captions
    video_style_enabled: bool = False
    video_style_strength: Literal["subtle", "strong"] = "subtle"


@dataclass(frozen=True)
class AppSettings:
    topic_tags: list[str]
    prefer_gpu: bool = True
    try_llm_4bit: bool = True
    try_sdxl_turbo: bool = True
    background_music_path: str = ""
    hf_token: str = ""  # optional: Hugging Face access token for gated repos / API calls
    personality_id: str = "auto"
    llm_model_id: str = ""
    image_model_id: str = ""
    video_model_id: str = ""  # optional: separate clip model (e.g., img→vid) when paired with keyframe image model
    voice_model_id: str = ""
    video: VideoSettings = VideoSettings()
    branding: BrandingSettings = BrandingSettings()


def safe_title_to_dirname(title: str) -> str:
    # Conservative Windows-safe slug
    cleaned = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else " " for ch in title)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:80].replace(" ", "_")

