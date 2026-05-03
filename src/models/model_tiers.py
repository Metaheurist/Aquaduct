from __future__ import annotations

"""Model capability tiers for local HF models and API provider/model pairs.

Tiers (ordered by typical capability / resource use, not strict):
- pro    — Flagship / heaviest / best default for quality when you have the hardware or budget
- standard — Balanced default
- lite   — Fastest or smallest footprint
"""

# Stable ids (settings / comparisons)
TIER_PRO = "pro"
TIER_STANDARD = "standard"
TIER_LITE = "lite"


def tier_label(tier_id: str) -> str:
    s = (tier_id or "").strip().lower()
    if s == TIER_PRO:
        return "Pro"
    if s == TIER_STANDARD:
        return "Standard"
    if s == TIER_LITE:
        return "Lite"
    return tier_id or "—"


def tier_badge(tier_id: str) -> str:
    """Short tag for combobox lines, e.g. [Pro]."""
    return f"[{tier_label(tier_id)}]"


def tier_sort_rank(tier_id: str) -> int:
    """Sort key: Lite → Standard → Pro (for grouped dropdowns)."""
    s = (tier_id or "").strip().lower()
    if s == TIER_LITE:
        return 0
    if s == TIER_STANDARD:
        return 1
    if s == TIER_PRO:
        return 2
    return 1


# --- Local (Hugging Face repo_id) — must cover every model_options() repo_id -----------------

_LOCAL_TIER: dict[str, str] = {
    # Script
    "Qwen/Qwen3-14B": TIER_STANDARD,
    "Sao10K/Fimbulvetr-11B-v2": TIER_LITE,
    "meta-llama/Llama-3.1-8B-Instruct": TIER_LITE,
    "Qwen/Qwen2.5-7B-Instruct": TIER_LITE,
    "sophosympatheia/Midnight-Miqu-70B-v1.5": TIER_PRO,
    "deepseek-ai/DeepSeek-V3": TIER_PRO,
    # Image
    "black-forest-labs/FLUX.1.1-pro-ultra": TIER_PRO,
    "black-forest-labs/FLUX.1-dev": TIER_PRO,
    "black-forest-labs/FLUX.1-schnell": TIER_LITE,
    "stabilityai/stable-diffusion-3.5-large": TIER_PRO,
    "stabilityai/stable-diffusion-3.5-medium": TIER_STANDARD,
    "stabilityai/stable-diffusion-3.5-large-turbo": TIER_LITE,
    # Video
    "Wan-AI/Wan2.2-T2V-A14B-Diffusers": TIER_STANDARD,
        "genmo/mochi-1-preview": TIER_STANDARD,
    "THUDM/CogVideoX-5b": TIER_LITE,
    "Tencent/HunyuanVideo": TIER_PRO,
    "Lightricks/LTX-2": TIER_PRO,
    # Voice
    "hexgrad/Kokoro-82M": TIER_LITE,
    "OpenMOSS-Team/MOSS-VoiceGenerator": TIER_PRO,
}


def local_tier_for_repo(repo_id: str) -> str:
    rid = str(repo_id or "").strip()
    return _LOCAL_TIER.get(rid, TIER_STANDARD)


# --- API: tier by provider + model id (user text is normalized) -------------------------------

def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def api_tier_for_model(provider_id: str, model_id: str) -> str:
    """
    Return tier for a named API model under a catalog provider.
    Unknown combinations default to Standard; Replicate / custom slugs are heuristics.
    """
    p, m = _norm(provider_id), _norm(model_id)
    if not p:
        return TIER_STANDARD

    # Replicate: image / video by model name pattern
    if p == "replicate":
        if ("flux" in m and "schnell" in m) or m.endswith("schnell"):
            return TIER_LITE
        if "sdxl" in m:
            return TIER_STANDARD
        return TIER_STANDARD

    if p == "google_ai_studio":
        if "flash-lite" in m:
            return TIER_LITE
        if "-pro" in m and "flash" not in m:
            return TIER_PRO
        return TIER_STANDARD

    if p == "siliconflow":
        if "schnell" in m:
            return TIER_LITE
        if "large" in m or "flux" in m:
            return TIER_PRO
        return TIER_STANDARD

    if p == "kling":
        if "kling-v3" in m or "master" in m or m == "kling-v2-master":
            return TIER_PRO
        return TIER_STANDARD

    if p == "magic_hour":
        if m in ("default", "kling-3.0", "ltx-2", "wan-2.2", "seedance"):
            return TIER_PRO
        return TIER_STANDARD

    if p == "inworld":
        if "mini" in m:
            return TIER_LITE
        if "max" in m:
            return TIER_PRO
        return TIER_STANDARD

    if p == "openai":
        if m in ("gpt-4o",) or m.startswith("gpt-4o-") and "mini" not in m:
            return TIER_PRO
        if m in ("dall-e-3",) or m == "tts-1-hd":
            return TIER_PRO
        if "mini" in m or m in ("dall-e-2", "tts-1"):
            return TIER_LITE
        if m.startswith("gpt-4o-mini") or m.startswith("gpt-3.5"):
            return TIER_STANDARD
        return TIER_STANDARD

    if p == "groq":
        if "70b" in m or "mixtral" in m or "8x" in m or "qwen3" in m:
            return TIER_PRO
        if "8b" in m or "instant" in m:
            return TIER_LITE
        return TIER_STANDARD

    if p in ("together", "nebius"):
        if "72" in m or "70" in m or "qwen3" in m:
            return TIER_PRO
        return TIER_STANDARD

    if p == "mistral":
        if "large" in m:
            return TIER_PRO
        if "small" in m or "nemo" in m:
            return TIER_STANDARD
        return TIER_STANDARD

    if p == "openrouter":
        if "claude" in m or ("4o" in m and "mini" not in m):
            return TIER_PRO
        if "mini" in m or "gpt-4o-mini" in m:
            return TIER_LITE
        return TIER_STANDARD

    if p == "deepseek":
        if "reasoner" in m:
            return TIER_PRO
        return TIER_STANDARD

    if p == "xai":
        return TIER_PRO

    if p == "fireworks":
        if "70" in m or "72" in m or "qwen3" in m:
            return TIER_PRO
        return TIER_STANDARD

    if p == "cerebras":
        if "70" in m or "3.3" in m:
            return TIER_PRO
        if "8b" in m:
            return TIER_LITE
        return TIER_STANDARD

    if p == "elevenlabs":
        if "turbo" in m:
            return TIER_STANDARD
        return TIER_PRO

    return TIER_STANDARD
