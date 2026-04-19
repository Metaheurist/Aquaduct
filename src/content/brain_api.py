from __future__ import annotations

from typing import Callable

from src.content.brain import (
    VideoPackage,
    _prompt_for_creative_brief,
    _prompt_for_items,
    _supplement_context_block,
    clip_article_excerpt,
    get_personality_by_id,
    video_package_from_llm_output,
)
from src.core.config import AppSettings, BrandingSettings
from src.platform.openai_client import OpenAIClient, build_openai_client_from_settings

SCRIPT_JSON_SYSTEM = (
    "You are an expert short-form vertical video writer. "
    "Return ONLY valid JSON for a VideoPackage: keys title, description, hashtags (array of strings), "
    "hook, segments (array of {narration, visual_prompt, on_screen_text}), cta. "
    "No markdown, no code fences, no commentary."
)


def _llm_model(settings: AppSettings) -> str:
    am = getattr(settings, "api_models", None)
    llm = getattr(am, "llm", None) if am is not None else None
    m = str(getattr(llm, "model", "") or "").strip()
    return m or "gpt-4o-mini"


def generate_script_openai(
    *,
    settings: AppSettings,
    items: list[dict[str, str]],
    topic_tags: list[str] | None,
    personality_id: str,
    branding: BrandingSettings | None,
    character_context: str | None,
    creative_brief: str | None,
    video_format: str,
    article_excerpt: str | None,
    supplement_context: str = "",
    on_llm_task: Callable[[str, int, str], None] | None = None,
) -> VideoPackage:
    personality = get_personality_by_id(personality_id)
    ex = clip_article_excerpt(article_excerpt)
    if creative_brief is not None and str(creative_brief).strip():
        prompt = _prompt_for_creative_brief(
            expanded_brief=str(creative_brief),
            topic_tags=topic_tags,
            video_format=str(video_format or "news"),
            personality=personality,
            branding=branding,
            character_context=character_context,
            article_excerpt=ex,
        )
    else:
        prompt = _prompt_for_items(
            items,
            topic_tags,
            personality,
            branding=branding,
            character_context=character_context,
            video_format=str(video_format or "news"),
            article_excerpt=ex,
        )
    sup = (supplement_context or "").strip()
    if sup:
        prompt = prompt + _supplement_context_block(sup)

    if on_llm_task:
        on_llm_task("llm_generate", 10, "Calling OpenAI (API mode)…")
    client = build_openai_client_from_settings(settings)
    raw = client.chat_completion_text(
        model=_llm_model(settings),
        system=SCRIPT_JSON_SYSTEM,
        user=prompt,
        json_mode=True,
    )
    if on_llm_task:
        on_llm_task("llm_generate", 100, "Script JSON received")
    return video_package_from_llm_output(raw)


def expand_custom_video_instructions_openai(
    *,
    settings: AppSettings,
    raw_instructions: str,
    video_format: str,
    personality_id: str,
    on_llm_task: Callable[[str, int, str], None] | None = None,
) -> str:
    if on_llm_task:
        on_llm_task("llm_generate", 5, "Expanding brief (OpenAI)…")
    client = build_openai_client_from_settings(settings)
    p = get_personality_by_id(personality_id)
    user = (
        f"Video format: {video_format}\n"
        f"Tone: {p.label}\n\n"
        "Expand and tighten this creator brief into a richer creative brief (plain text, no JSON):\n\n"
        f"{raw_instructions.strip()[:8000]}"
    )
    out = client.chat_completion_text(
        model=_llm_model(settings),
        system="You help short-form video creators. Output improved plain-text instructions only.",
        user=user,
        json_mode=False,
    )
    if on_llm_task:
        on_llm_task("llm_generate", 100, "Brief expanded")
    return (out or "").strip() or raw_instructions.strip()


def expand_custom_field_text_openai(
    *,
    settings: AppSettings,
    field_label: str,
    seed: str,
) -> str:
    client = build_openai_client_from_settings(settings)
    user = f"Field: {field_label}\n\nImprove this text (plain output only, no quotes):\n\n{(seed or '').strip()[:12000]}"
    return client.chat_completion_text(
        model=_llm_model(settings),
        system="You improve UI field text for a video app. Output only the revised text.",
        user=user,
        json_mode=False,
    ).strip()
