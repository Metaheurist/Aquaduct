from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ModelExecutionMode = Literal["local", "api"]
ModelsStorageMode = Literal["default", "external"]
QuantMode = Literal["auto", "bf16", "fp16", "int8", "nf4_4bit", "cpu_offload"]

from .app_dirs import application_data_dir, installation_dir

# Pipeline + per-mode topic lists use the same IDs.
VideoFormat = Literal["news", "cartoon", "explainer", "unhinged", "creepypasta", "health_advice"]

VIDEO_FORMATS: tuple[str, ...] = ("news", "cartoon", "explainer", "unhinged", "creepypasta", "health_advice")

RunContentMode = Literal["preset", "custom"]

# High-level UI/pipeline mode (separate from model execution Local/API).
MediaMode = Literal["video", "photo"]

# Local CUDA: Auto = LLM on compute-heuristic GPU, diffusion on max VRAM; Single = pin one GPU.
GpuSelectionMode = Literal["auto", "single"]

# Intra-stage multi-GPU (requires Auto policy + optional toggle; favors lower peak VRAM per card).
MultiGpuShardMode = Literal["off", "vram_first_auto"]

PictureOutputType = Literal["single_image", "image_set", "layouted"]
PictureFormat = Literal["poster", "newspaper", "comic"]


@dataclass(frozen=True)
class PictureSettings:
    template_id: str = "vertical_1080"
    width: int = 1080
    height: int = 1920
    output_type: PictureOutputType = "single_image"
    image_count: int = 6
    picture_format: PictureFormat = "poster"


def video_format_supports_facts_card(video_format: str | None) -> bool:
    """Whether the Key facts on-screen card may appear for this pipeline mode."""
    v = str(video_format or "news").strip().lower()
    return v in ("news", "explainer", "health_advice")

# Max stored length for Run tab custom instructions (ui_settings + RAM)
MAX_CUSTOM_VIDEO_INSTRUCTIONS: int = 8000

# How many headline candidates to load for the script LLM (multi-story arcs, contrast, outlets)
SCRIPT_HEADLINE_FETCH_LIMIT: int = 8

# Trimmed article body passed into script prompts (characters)
ARTICLE_EXCERPT_MAX_CHARS: int = 6000


def default_topic_tags_by_mode() -> dict[str, list[str]]:
    return {m: [] for m in VIDEO_FORMATS}


@dataclass(frozen=True)
class Paths:
    # Install / repo root (dev) or folder with the .exe (frozen)—not writable data root.
    root: Path
    # ``.Aquaduct_data``: models, runs, cache, ui_settings.json, etc.
    app_data_dir: Path
    data_dir: Path
    news_cache_dir: Path
    runs_dir: Path
    videos_dir: Path
    # Photo pipeline outputs (per-project folders with ``final.png`` + ``assets/``).
    pictures_dir: Path
    models_dir: Path
    cache_dir: Path
    ffmpeg_dir: Path


def media_output_root(paths: Paths, media_mode: str | None) -> Path:
    """Where finished media projects are stored: ``videos/`` vs ``pictures/``."""
    mm = str(media_mode or "video").strip().lower()
    return paths.pictures_dir if mm == "photo" else paths.videos_dir


def get_paths() -> Paths:
    root = installation_dir()
    ada = application_data_dir()
    data_dir = ada / "data"
    news_cache_dir = data_dir / "news_cache"
    runs_dir = ada / "runs"
    videos_dir = ada / "videos"
    pictures_dir = ada / "pictures"
    models_dir = ada / "models"
    cache_dir = ada / ".cache"
    ffmpeg_dir = cache_dir / "ffmpeg"

    return Paths(
        root=root,
        app_data_dir=ada,
        data_dir=data_dir,
        news_cache_dir=news_cache_dir,
        runs_dir=runs_dir,
        videos_dir=videos_dir,
        pictures_dir=pictures_dir,
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
        llm_id="Qwen/Qwen3-14B",
        sdxl_turbo_id="black-forest-labs/FLUX.1-schnell",
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
    # Pro mode (slideshow only): generate round(pro_clip_seconds * fps) frames, one per output frame; see editor.
    pro_mode: bool = False
    pro_clip_seconds: float = 4.0
    clips_per_video: int = 3
    clip_seconds: float = 4.0
    cleanup_images_after_run: bool = False
    # Content-quality toggles (v1 defaults on)
    high_quality_topic_selection: bool = True
    fetch_article_text: bool = True
    llm_factcheck: bool = True
    prompt_conditioning: bool = True
    # Multi-stage script LLM + optional Firecrawl context / reference images (Video tab)
    story_multistage_enabled: bool = False
    story_web_context: bool = False
    story_reference_images: bool = False
    # When True, ``run_checkpoint.json`` guides skipping completed coarse stages after a crash (artifacts + fingerprints).
    resume_partial_pipeline: bool = False
    # Visual quality controls
    seed_base: int | None = None
    quality_retries: int = 2
    enable_motion: bool = True
    transition_strength: Literal["off", "low", "med"] = "low"
    # FFmpeg xfade transition name (see `src/ffmpeg_slideshow.sanitize_xfade_transition`).
    xfade_transition: str = "fade"

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

    # Last selected platform template id (empty = Custom); see `src/video_platform_presets.py`
    platform_preset_id: str = ""
    # Last selected Effects tab template id (empty = Custom); see `src/effects_presets.py`
    effects_preset_id: str = ""


@dataclass(frozen=True)
class ApiRoleConfig:
    """Per-role API routing (OpenAI, Replicate, ElevenLabs voice, etc.)."""

    provider: str = ""
    model: str = ""
    base_url: str = ""
    org_id: str = ""
    voice_id: str = ""


@dataclass(frozen=True)
class ApiModelRuntimeSettings:
    llm: ApiRoleConfig = field(default_factory=ApiRoleConfig)
    image: ApiRoleConfig = field(default_factory=ApiRoleConfig)
    video: ApiRoleConfig = field(default_factory=ApiRoleConfig)
    voice: ApiRoleConfig = field(default_factory=ApiRoleConfig)


def default_api_models() -> ApiModelRuntimeSettings:
    return ApiModelRuntimeSettings(
        llm=ApiRoleConfig(),
        image=ApiRoleConfig(),
        video=ApiRoleConfig(),
        voice=ApiRoleConfig(),
    )


@dataclass(frozen=True)
class BrandingSettings:
    # Theme (optional overrides)
    theme_enabled: bool = False
    palette_id: str = "default"  # preset key in UI.theme.PRESET_PALETTES (+ custom)

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

    # Photo style (optional): affects still prompts + layout rendering
    photo_style_enabled: bool = False
    photo_frame_enabled: bool = False
    photo_frame_width: int = 24
    # Used as a paper-like background tint for layouts (poster/newspaper/comic).
    photo_paper_hex: str = "#F2F0E9"


@dataclass(frozen=True)
class AppSettings:
    topic_tags_by_mode: dict[str, list[str]] = field(default_factory=default_topic_tags_by_mode)
    media_mode: MediaMode = "video"
    video_format: VideoFormat = "news"
    prefer_gpu: bool = True
    try_llm_4bit: bool = True
    try_sdxl_turbo: bool = True
    #: Quantization / precision policy for local models (per role). ``auto`` uses effective VRAM per role.
    script_quant_mode: QuantMode = "auto"
    image_quant_mode: QuantMode = "auto"
    video_quant_mode: QuantMode = "auto"
    voice_quant_mode: QuantMode = "auto"
    #: Local runs: on load/inference failure (not only OOM), step quantization down one notch for that role and retry.
    auto_quant_downgrade_on_failure: bool = True
    background_music_path: str = ""
    hf_token: str = ""  # optional: Hugging Face access token for gated repos / API calls
    hf_api_enabled: bool = True  # when False, saved token is not applied to HF_TOKEN (soft opt-out)
    firecrawl_enabled: bool = False
    firecrawl_api_key: str = ""
    elevenlabs_enabled: bool = False
    elevenlabs_api_key: str = ""  # optional cloud TTS; see docs/integrations/elevenlabs.md
    personality_id: str = "auto"
    active_character_id: str = ""  # empty = no character; see data/characters.json
    #: Visual diffusion style (see ``src.settings.art_style_presets``); img2img continuity uses last frames.
    art_style_preset_id: str = "balanced"
    run_content_mode: RunContentMode = "preset"  # preset = news cache + topics; custom = user instructions
    custom_video_instructions: str = ""  # used when run_content_mode == "custom"
    #: ``local`` = Hugging Face / local inference; ``api`` = HTTP providers (see ``api_models``).
    model_execution_mode: ModelExecutionMode = "local"
    #: ``default`` = ``.Aquaduct_data/models``; ``external`` = separate folder (see ``models_external_path``).
    models_storage_mode: ModelsStorageMode = "default"
    models_external_path: str = ""
    api_models: ApiModelRuntimeSettings = field(default_factory=default_api_models)
    #: Keys for cloud generation (also mirrored on API tab). Prefer env: OPENAI_API_KEY, REPLICATE_API_TOKEN when set.
    api_openai_key: str = ""
    api_replicate_token: str = ""
    llm_model_id: str = ""
    image_model_id: str = ""
    video_model_id: str = ""  # optional: separate clip model (e.g., img→vid) when paired with keyframe image model
    voice_model_id: str = ""
    allow_nsfw: bool = False  # allow NSFW content (disable safety checker)
    video: VideoSettings = VideoSettings()
    picture: PictureSettings = PictureSettings()
    branding: BrandingSettings = BrandingSettings()
    # TikTok Content Posting API (OAuth + optional upload). See docs/integrations/tiktok.md
    tiktok_enabled: bool = False
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = "http://127.0.0.1:8765/callback/"
    tiktok_oauth_port: int = 8765
    tiktok_access_token: str = ""
    tiktok_refresh_token: str = ""
    tiktok_token_expires_at: float = 0.0  # unix time; 0 = unknown/expired
    tiktok_open_id: str = ""
    # inbox = send to TikTok app inbox (video.upload); direct = publish (requires video.publish + review)
    tiktok_publishing_mode: Literal["inbox", "direct"] = "inbox"
    tiktok_auto_upload_after_render: bool = False
    # YouTube Data API v3 (OAuth + optional upload / Shorts). See docs/integrations/youtube.md
    youtube_enabled: bool = False
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://127.0.0.1:8888/callback/"
    youtube_oauth_port: int = 8888
    youtube_access_token: str = ""
    youtube_refresh_token: str = ""
    youtube_token_expires_at: float = 0.0
    youtube_privacy_status: Literal["public", "unlisted", "private"] = "private"
    youtube_add_shorts_hashtag: bool = True
    youtube_auto_upload_after_render: bool = False
    #: Set True after the user dismisses the first-run tutorial (stored in ``ui_settings.json``).
    tutorial_completed: bool = False
    #: Multi-GPU: ``auto`` uses max-VRAM GPU for diffusion and heuristic-fast GPU for LLM; ``single`` pins ``gpu_device_index``.
    gpu_selection_mode: GpuSelectionMode = "auto"
    #: Experimental: intra-model VRAM-first sharding with Auto + ``>=`` 2 CUDA devices (honors curated registry + quant gates).
    multi_gpu_shard_mode: MultiGpuShardMode = "off"
    #: Used when ``gpu_selection_mode == "single"`` (CUDA ordinal, must exist).
    gpu_device_index: int = 0
    #: Resource graph: which GPU index to chart (None = default 0).
    resource_graph_monitor_gpu_index: int | None = None
    #: Resource graph: last Monitor dropdown choice was “Split view — all GPUs” (one VRAM sparkline per CUDA GPU).
    resource_graph_split_view: bool = False
    #: Resource graph: compact (mini) title-bar layout and smaller sparklines; ``False`` = expanded detail.
    resource_graph_compact: bool = True
    #: When True, skip the startup dialog that offers CUDA PyTorch if the user chose "Don't ask again".
    skip_cuda_cpu_torch_mismatch_prompt: bool = False
    #: Diffusion pipelines: force CPU execution (crash-resilience ladder last resort).
    _force_cpu_diffusion: bool = False
    # Ephemeral retry scalars — stripped in ``save_settings()``; reset each fresh run.
    resource_retry_resolution_scale: float = 1.0
    resource_retry_frames_scale: float = 1.0
    #: Last-resort: render diffusion on CPU (very slow).
    cpu_render_last_resort: bool = True
    #: Variant swap ladder (filled during retry_stage when applicable).
    recovery_swapped_voice_model_id: str = ""
    recovery_swapped_video_model_id: str = ""
    recovery_swapped_image_model_id: str = ""
    #: Ephemeral: when set, ``run_once`` may skip script LLM stages and bind outputs to this project folder (not saved).
    resume_partial_project_directory: str = ""


def safe_title_to_dirname(title: str) -> str:
    # Conservative Windows-safe slug
    cleaned = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else " " for ch in title)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:80].replace(" ", "_")

