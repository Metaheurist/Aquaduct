"""Episode recap for series bible — LLM when available, deterministic fallback."""

from __future__ import annotations

import re

from src.content.llm_session import dispose_llm_holder, new_llm_holder
from src.core.config import AppSettings


def fallback_recap_from_script(script_text: str) -> str:
    """Use first two + last two sentence-like units when the LLM path fails."""
    text = (script_text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 4:
        clip = " ".join(parts)
        return clip[:1200]
    return (parts[0] + " " + parts[1] + " … " + parts[-2] + " " + parts[-1]).strip()[:1200]


def _api_llm_model_id(settings: AppSettings) -> str:
    am = getattr(settings, "api_models", None)
    llm = getattr(am, "llm", None) if am is not None else None
    m = str(getattr(llm, "model", "") or "").strip()
    return m or "gpt-4o-mini"


def summarize_episode_for_series_bible(
    *,
    app: AppSettings,
    script_text: str,
    episode_title: str,
    llm_model_id: str,
    llm_cuda_device_index: int | None,
) -> str:
    """Target ~80–160 words; never raises — returns fallback on any failure."""
    st = (script_text or "").strip()
    if not st:
        return ""
    recap = ""
    try:
        from src.runtime.model_backend import is_api_mode

        if is_api_mode(app):
            try:
                from src.platform.openai_client import build_openai_client_from_settings

                client = build_openai_client_from_settings(app)
                user = (
                    f"Episode title: {episode_title or 'Untitled'}\n\n"
                    f"Full script:\n{st[:14000]}\n\n"
                    "Write ONE plain-text recap paragraph of 80–160 words for multi-episode continuity. "
                    "Cover plot beats, character actions, and open threads. No markdown, no quotes around output."
                )
                recap = client.chat_completion_text(
                    model=_api_llm_model_id(app),
                    system="You write tight continuity recaps for a vertical video series.",
                    user=user,
                    json_mode=False,
                )
                recap = (recap or "").strip()
            except Exception:
                recap = ""
            if len(recap) >= 40:
                return recap[:8000]
            return fallback_recap_from_script(st)

        from src.content.brain import _infer_text_with_optional_holder

        mid = (llm_model_id or "").strip()
        if not mid:
            return fallback_recap_from_script(st)
        holder = new_llm_holder()
        try:
            prompt = (
                "Write ONE plain-text recap paragraph of 80–160 words for a vertical video series bible. "
                "Cover plot beats, character actions, and open threads. No markdown.\n\n"
                f"Episode title: {episode_title or 'Untitled'}\n\nScript:\n{st[:14000]}"
            )
            raw = _infer_text_with_optional_holder(
                mid,
                prompt,
                llm_holder=holder,
                on_llm_task=None,
                max_new_tokens=400,
                try_llm_4bit=bool(getattr(app, "try_llm_4bit", True)),
                llm_cuda_device_index=llm_cuda_device_index,
                inference_settings=app,
            )
            recap = (raw or "").strip()
        finally:
            dispose_llm_holder(holder)
    except Exception:
        recap = ""

    if len(recap) >= 40:
        return recap[:8000]
    return fallback_recap_from_script(st)
