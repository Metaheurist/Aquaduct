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
    # When set, LLM role uses OpenAI-compatible chat/completions at this base (Bearer from env_key_names / saved OpenAI key field).
    openai_compatible_base_url: str | None = None


# Placeholder slugs — UI may also accept free-text model ids (Replicate version strings).
# Order matters: the first match per role in this tuple is the top entry in the Model/API dropdowns.
PROVIDERS: tuple[ApiProviderSpec, ...] = (
    # --- Recommended defaults (API mode) — env keys: GEMINI_API_KEY, SILICONFLOW_API_KEY, MAGIC_HOUR_API_KEY, INWORLD_API_KEY ---
    ApiProviderSpec(
        id="google_ai_studio",
        display_name="Google AI Studio (Gemini) — large context, ~1.5k req/day (free)",
        roles=("llm",),
        env_key_names=("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("gemini-2.0-flash", "gemini-1.5-pro", "gemini-2.5-flash-preview-05-20"),
        openai_compatible_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    ),
    ApiProviderSpec(
        id="siliconflow",
        display_name="SiliconFlow (Flux, SD3, …) — daily free credits",
        roles=("image",),
        env_key_names=("SILICONFLOW_API_KEY", "OPENAI_API_KEY"),
        model_slugs=(
            "black-forest-labs/FLUX.1-schnell",
            "stabilityai/stable-diffusion-3-5-large",
        ),
    ),
    ApiProviderSpec(
        id="magic_hour",
        display_name="Magic Hour — generative video API, ~100 credits/day (free)",
        roles=("video",),
        env_key_names=("MAGIC_HOUR_API_KEY", "MAGICHOUR_API_KEY"),
        model_slugs=("default", "ltx-2", "wan-2.2", "seedance", "kling-3.0", "kling-1.6"),
    ),
    ApiProviderSpec(
        id="inworld",
        display_name="Inworld — low-latency TTS (free tier)",
        roles=("voice",),
        env_key_names=("INWORLD_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("inworld-tts-1.5-max", "inworld-tts-1.5-mini"),
    ),
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
        openai_compatible_base_url=None,
    ),
    # OpenAI Chat Completions–compatible hosts (script LLM / brain-expand only; same Bearer patterns as OpenAI).
    ApiProviderSpec(
        id="groq",
        display_name="Groq",
        roles=("llm",),
        env_key_names=("GROQ_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"),
        openai_compatible_base_url="https://api.groq.com/openai/v1",
    ),
    ApiProviderSpec(
        id="together",
        display_name="Together AI",
        roles=("llm",),
        env_key_names=("TOGETHER_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"),
        openai_compatible_base_url="https://api.together.xyz/v1",
    ),
    ApiProviderSpec(
        id="mistral",
        display_name="Mistral AI",
        roles=("llm",),
        env_key_names=("MISTRAL_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("mistral-small-latest", "mistral-large-latest", "open-mistral-nemo"),
        openai_compatible_base_url="https://api.mistral.ai/v1",
    ),
    ApiProviderSpec(
        id="openrouter",
        display_name="OpenRouter",
        roles=("llm",),
        env_key_names=("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-pro-1.5"),
        openai_compatible_base_url="https://openrouter.ai/api/v1",
    ),
    ApiProviderSpec(
        id="deepseek",
        display_name="DeepSeek",
        roles=("llm",),
        env_key_names=("DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("deepseek-chat", "deepseek-reasoner"),
        openai_compatible_base_url="https://api.deepseek.com",
    ),
    ApiProviderSpec(
        id="xai",
        display_name="xAI (Grok)",
        roles=("llm",),
        env_key_names=("XAI_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("grok-2-latest", "grok-2-vision-latest"),
        openai_compatible_base_url="https://api.x.ai/v1",
    ),
    ApiProviderSpec(
        id="fireworks",
        display_name="Fireworks AI",
        roles=("llm",),
        env_key_names=("FIREWORKS_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("accounts/fireworks/models/llama-v3p3-70b-instruct", "accounts/fireworks/models/qwen2p5-72b-instruct"),
        openai_compatible_base_url="https://api.fireworks.ai/inference/v1",
    ),
    ApiProviderSpec(
        id="cerebras",
        display_name="Cerebras",
        roles=("llm",),
        env_key_names=("CEREBRAS_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("llama3.1-8b", "llama-3.3-70b"),
        openai_compatible_base_url="https://api.cerebras.ai/v1",
    ),
    ApiProviderSpec(
        id="nebius",
        display_name="Nebius AI Studio",
        roles=("llm",),
        env_key_names=("NEBIUS_API_KEY", "OPENAI_API_KEY"),
        model_slugs=("meta-llama/Meta-Llama-3.1-70B-Instruct", "Qwen/Qwen2.5-72B-Instruct"),
        openai_compatible_base_url="https://api.studio.nebius.ai/v1",
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
    if role == "llm" and provider_id == "google_ai_studio":
        return ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-2.5-flash-preview-05-20"]
    if role == "llm" and p.openai_compatible_base_url:
        return list(p.model_slugs)
    if role == "image" and provider_id == "openai":
        return ["dall-e-3", "dall-e-2"]
    if role == "image" and provider_id == "siliconflow":
        return ["black-forest-labs/FLUX.1-schnell", "stabilityai/stable-diffusion-3-5-large"]
    if role == "video" and provider_id == "magic_hour":
        return ["default", "ltx-2", "wan-2.2", "seedance", "kling-3.0", "kling-1.6"]
    if role == "voice" and provider_id == "openai":
        return ["tts-1", "tts-1-hd"]
    if role == "voice" and provider_id == "elevenlabs":
        return list(p.model_slugs)
    if role == "voice" and provider_id == "inworld":
        return ["inworld-tts-1.5-max", "inworld-tts-1.5-mini"]
    return list(p.model_slugs)


def uses_openai_chat_protocol_for_llm(provider_id: str) -> bool:
    """True when script LLM calls use :class:`src.platform.openai_client.OpenAIClient` (chat/completions)."""
    spec = provider_by_id(provider_id)
    if not spec or "llm" not in spec.roles:
        return False
    if spec.id == "openai":
        return True
    return bool(spec.openai_compatible_base_url)


def default_openai_compatible_base_url_for_llm(provider_id: str) -> str | None:
    spec = provider_by_id(provider_id)
    if not spec:
        return None
    return spec.openai_compatible_base_url
