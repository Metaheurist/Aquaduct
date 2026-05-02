"""Curated smaller-model swaps for crash-recovery ladders (VRAM / host RAM)."""

from __future__ import annotations

from dataclasses import replace

from src.core.config import AppSettings

from src.models.quantization import QuantRole
from src.speech.tts_kokoro_moss import KOKORO_HUB, PYTTSX3_FALLBACK_REPO


def _norm_hub(repo: str) -> str:
    return repo.strip().lower().replace("\\", "/")


_LL_ALIASES: dict[str, tuple[str, ...]] = {
    "qwen/qwen3-14b": ("Qwen/Qwen3-8B", "Qwen/Qwen2.5-14B-Instruct", "Qwen/Qwen2.5-7B-Instruct"),
    "qwen/qwen2.5-14b-instruct": ("Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-3B-Instruct"),
    "meta-llama/meta-llama-3-8b-instruct": ("mistralai/Mistral-7B-Instruct-v0.3",),
}

_IMG_ALIASES: dict[str, tuple[str, ...]] = {
    "black-forest-labs/flux.1-dev": (
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-3.5-medium",
    ),
    "stabilityai/stable-diffusion-3.5-large": ("stabilityai/stable-diffusion-3.5-medium",),
}

_VID_ALIASES: dict[str, tuple[str, ...]] = {
    "wan-ai/wan2.2-t2v-a14b-diffusers": (
        "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        "Lightricks/ltx-video",
    ),
    "thudm/cogvideox-5b": ("THUDM/CogVideoX-2b",),
}

_VOICE_ALIASES: dict[str, tuple[str, ...]] = {
    "openmoss-team/moss-voicegenerator": (KOKORO_HUB,),
    _norm_hub(KOKORO_HUB): (PYTTSX3_FALLBACK_REPO,),
}


def next_smaller_repo_id(role: QuantRole | str, repo_id: str) -> str | None:
    r = str(role or "").strip().lower()
    rid = _norm_hub(repo_id)
    table: dict[str, tuple[str, ...]]
    if r == "script":
        table = _LL_ALIASES
    elif r == "image":
        table = _IMG_ALIASES
    elif r == "video":
        table = _VID_ALIASES
    elif r == "voice":
        table = _VOICE_ALIASES
    else:
        return None

    cand = table.get(rid)
    return cand[0] if cand else None


def apply_variant_swap(settings: AppSettings, *, role: QuantRole | str, new_repo: str) -> AppSettings:
    """Return replaced settings swapping the targeted model field."""
    r = str(role or "").strip().lower()
    nr = str(new_repo or "").strip()
    if not nr:
        return settings
    if r == "script":
        return replace(settings, llm_model_id=nr)
    if r == "image":
        return replace(settings, image_model_id=nr)
    if r == "video":
        return replace(settings, video_model_id=nr)
    if r == "voice":
        return replace(settings, voice_model_id=nr)
    return settings

