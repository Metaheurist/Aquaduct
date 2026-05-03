"""Token / character budgets for the LLM chat composer (local + API script models)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.config import AppSettings

# Conservative mapping from UTF-8 length to tokenizer tokens (mixed CJK/Latin).
CHARS_PER_TOKEN_EST = 3.5
MIN_MESSAGE_CHARS = 64
MAX_MESSAGE_CHARS_CAP = 120_000
RESERVE_COMPLETION_TOKENS = 1024
# Rough overhead for _format_local_prompt tail ("Reply as Assistant…") and role labels.
LOCAL_FORMAT_OVERHEAD_TOKENS = 48


def _rough_token_est(*parts: str) -> int:
    n = sum(len(p or "") for p in parts)
    if n <= 0:
        return 0
    return max(1, int(n / CHARS_PER_TOKEN_EST))


def local_llm_chat_context_tokens(model_key: str, settings: AppSettings) -> int:
    """Aligns with script inference profiles + optional low-VRAM prefill cap."""
    raw = (os.environ.get("AQUADUCT_LLM_MAX_INPUT_TOKENS") or "").strip()
    if raw.isdigit():
        return max(256, min(int(raw), 100_000))
    from src.models.inference_profiles import pick_script_profile, resolve_effective_vram_gb

    v = resolve_effective_vram_gb(kind="script", settings=settings)
    sp = pick_script_profile((model_key or "").strip(), v)
    ctx = int(sp.max_input_tokens)
    try:
        from src.content.brain import _llm_max_input_tokens_cap_from_vram

        vcap = _llm_max_input_tokens_cap_from_vram()
        if vcap is not None:
            ctx = min(ctx, vcap)
    except Exception:
        pass
    return max(256, ctx)


def api_llm_chat_context_tokens(provider: str, model: str) -> int:
    """Published-ish context sizes; conservative when unknown (custom OpenRouter ids, etc.)."""
    p, m = (provider or "").strip().lower(), (model or "").strip().lower()
    if not m and not p:
        return 32_768
    if p == "google_ai_studio" or "gemini" in m:
        if "2.5" in m or "2.0" in m:
            return 1_048_576
        return 128_000
    if p == "openai":
        if "o1" in m or "o3" in m:
            return 200_000
        return 128_000
    if p == "groq":
        if "70" in m or "qwen3" in m or "32b" in m:
            return 32_768
        return 8192
    if p in ("together", "nebius"):
        return 131_072
    if p == "fireworks":
        return 131_072
    if p == "mistral":
        return 128_000
    if p == "openrouter":
        return 128_000
    if p == "deepseek":
        return 64_000
    if p == "xai":
        return 131_072
    if p == "cerebras":
        return 8192
    return 32_768


def llm_chat_context_token_budget(*, mode: str, model_key: str, settings: AppSettings) -> int:
    mode = (mode or "").strip().lower()
    if mode == "api":
        am = getattr(settings, "api_models", None)
        llm = getattr(am, "llm", None) if am is not None else None
        prov = str(getattr(llm, "provider", "") or "").strip().lower() if llm else ""
        mdl = str(getattr(llm, "model", "") or "").strip() if llm else (model_key or "").strip()
        return max(2048, api_llm_chat_context_tokens(prov, mdl or model_key))
    return local_llm_chat_context_tokens(model_key, settings)


def history_chars_for_budget(messages: list[dict[str, str]], *, max_messages: int) -> str:
    """Concatenate rolled history text for length estimation (same order as chat)."""
    tail = messages[-max_messages:] if messages else []
    chunks: list[str] = []
    for m in tail:
        if str(m.get("role", "")) in ("user", "assistant"):
            chunks.append(str(m.get("content", "")))
    return "".join(chunks)


def trim_messages_to_budget(
    messages: list[dict[str, str]],
    *,
    system_prompt: str,
    context_tokens: int,
    max_new_tokens: int,
    reserve: int = 64,
    format_overhead_tokens: int = LOCAL_FORMAT_OVERHEAD_TOKENS,
) -> list[dict[str, str]]:
    """
    Keep the newest user/assistant turns that fit under the context budget.

    Estimates token use with ``_rough_token_est``; drops oldest turns first.
    """
    room = max(0, context_tokens - max_new_tokens - reserve - format_overhead_tokens)
    used = _rough_token_est(system_prompt)
    kept_from_end: list[dict[str, str]] = []
    for m in reversed(messages):
        role = str(m.get("role", ""))
        if role not in ("user", "assistant"):
            continue
        body = str(m.get("content", ""))
        est = _rough_token_est(body)
        if used + est > room and kept_from_end:
            break
        kept_from_end.append({"role": role, "content": body})
        used += est
    kept_from_end.reverse()
    return kept_from_end


def effective_max_new_tokens_for_chat(
    *,
    mode: str,
    model_key: str,
    settings: AppSettings,
    cap: int = 256,
) -> int:
    """Caps chat decode length to the script profile when using a local model."""
    mode = (mode or "").strip().lower()
    if mode == "api":
        return min(1024, max(64, cap))
    try:
        from src.models.inference_profiles import pick_script_profile, resolve_effective_vram_gb

        v = resolve_effective_vram_gb(kind="script", settings=settings)
        sp = pick_script_profile((model_key or "").strip(), v)
        return min(int(sp.max_new_tokens), cap)
    except Exception:
        return cap


def composer_char_limit(
    *,
    mode: str,
    model_key: str,
    settings: AppSettings,
    system_prompt: str,
    messages: list[dict[str, str]],
    max_history_messages: int,
) -> tuple[int, int]:
    """
    Returns (max_chars_for_next_user_message, nominal_context_token_budget).

    Estimates prompt tokens already consumed by system + rolled transcript, reserves
    space for a completion, and converts remaining token room to a character cap.
    """
    ctx = llm_chat_context_token_budget(mode=mode, model_key=model_key, settings=settings)
    hist_concat = history_chars_for_budget(messages, max_messages=max_history_messages)
    used_tokens = _rough_token_est(system_prompt, hist_concat) + LOCAL_FORMAT_OVERHEAD_TOKENS
    room = ctx - RESERVE_COMPLETION_TOKENS - used_tokens
    raw_chars = int(max(0, room) * CHARS_PER_TOKEN_EST)
    cap = min(MAX_MESSAGE_CHARS_CAP, max(MIN_MESSAGE_CHARS, raw_chars))
    return cap, ctx
