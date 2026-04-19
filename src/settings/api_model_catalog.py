from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RoleId = Literal["llm", "image", "video", "voice"]


@dataclass(frozen=True)
class ApiProviderSpec:
    id: str
    display_name: str
    roles: tuple[RoleId, ...]
    env_key_names: tuple[str, ...]
    model_slugs: tuple[str, ...]


# Placeholder slugs — UI may also accept free-text model ids (Replicate version strings).
PROVIDERS: tuple[ApiProviderSpec, ...] = (
    ApiProviderSpec(
        id="openai",
        display_name="OpenAI",
        roles=("llm", "image", "video", "voice"),
        env_key_names=("OPENAI_API_KEY",),
        model_slugs=(
            "gpt-4o-mini",
            "gpt-4o",
            "dall-e-3",
            "dall-e-2",
            "tts-1",
            "tts-1-hd",
        ),
    ),
    ApiProviderSpec(
        id="replicate",
        display_name="Replicate",
        roles=("image", "video"),
        env_key_names=("REPLICATE_API_TOKEN", "REPLICATE_API_KEY"),
        model_slugs=(
            "black-forest-labs/flux-schnell",
            "stability-ai/sdxl",
        ),
    ),
    ApiProviderSpec(
        id="elevenlabs",
        display_name="ElevenLabs",
        roles=("voice",),
        env_key_names=("ELEVENLABS_API_KEY",),
        model_slugs=("eleven_multilingual_v2", "eleven_turbo_v2_5"),
    ),
)


def providers_for_role(role: RoleId) -> list[ApiProviderSpec]:
    return [p for p in PROVIDERS if role in p.roles]


def provider_by_id(pid: str) -> ApiProviderSpec | None:
    s = str(pid or "").strip().lower()
    for p in PROVIDERS:
        if p.id == s:
            return p
    return None


def default_models_for_provider(provider_id: str, role: RoleId) -> list[str]:
    p = provider_by_id(provider_id)
    if not p:
        return []
    # Prefer role-appropriate defaults from shared slug list (best-effort).
    if role == "llm" and provider_id == "openai":
        return ["gpt-4o-mini", "gpt-4o"]
    if role == "image" and provider_id == "openai":
        return ["dall-e-3", "dall-e-2"]
    if role == "voice" and provider_id == "openai":
        return ["tts-1", "tts-1-hd"]
    if role == "voice" and provider_id == "elevenlabs":
        return list(p.model_slugs)
    return list(p.model_slugs)
