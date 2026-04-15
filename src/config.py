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


@dataclass(frozen=True)
class AppSettings:
    topic_tags: list[str]
    prefer_gpu: bool = True
    try_llm_4bit: bool = True
    try_sdxl_turbo: bool = True
    background_music_path: str = ""
    llm_model_id: str = ""
    image_model_id: str = ""
    voice_model_id: str = ""
    video: VideoSettings = VideoSettings()


def safe_title_to_dirname(title: str) -> str:
    # Conservative Windows-safe slug
    cleaned = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else " " for ch in title)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:80].replace(" ", "_")

