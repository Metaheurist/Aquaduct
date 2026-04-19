from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from src.content.brain import VideoPackage
from src.core.config import AppSettings, BrandingSettings


@runtime_checkable
class GenerationFacade(Protocol):
    """Single entry for script package generation — local transformers vs OpenAI (API mode)."""

    def generate_script_package(
        self,
        *,
        settings: AppSettings,
        model_id: str = "",
        items: list[dict[str, str]] | None = None,
        topic_tags: list[str] | None = None,
        personality_id: str = "neutral",
        branding: BrandingSettings | None = None,
        character_context: str | None = None,
        on_llm_task: Callable[[str, int, str], None] | None = None,
        creative_brief: str | None = None,
        video_format: str = "news",
        try_llm_4bit: bool = True,
        article_excerpt: str | None = None,
        supplement_context: str = "",
    ) -> VideoPackage: ...


class _LocalGenerationFacade:
    def generate_script_package(
        self,
        *,
        settings: AppSettings,
        model_id: str = "",
        items: list[dict[str, str]] | None = None,
        topic_tags: list[str] | None = None,
        personality_id: str = "neutral",
        branding: BrandingSettings | None = None,
        character_context: str | None = None,
        on_llm_task: Callable[[str, int, str], None] | None = None,
        creative_brief: str | None = None,
        video_format: str = "news",
        try_llm_4bit: bool = True,
        article_excerpt: str | None = None,
        supplement_context: str = "",
    ) -> VideoPackage:
        from src.content.brain import generate_script

        assert isinstance(settings, AppSettings)
        mid = str(model_id or "").strip()
        if not mid:
            raise RuntimeError("Local script generation requires a script (LLM) model id.")
        return generate_script(
            model_id=mid,
            items=list(items or []),
            topic_tags=topic_tags,
            personality_id=personality_id,
            branding=branding,
            character_context=character_context,
            on_llm_task=on_llm_task,
            creative_brief=creative_brief,
            video_format=video_format,
            try_llm_4bit=try_llm_4bit,
            article_excerpt=article_excerpt,
            supplement_context=supplement_context,
        )


class _ApiGenerationFacade:
    def generate_script_package(
        self,
        *,
        settings: AppSettings,
        model_id: str = "",
        items: list[dict[str, str]] | None = None,
        topic_tags: list[str] | None = None,
        personality_id: str = "neutral",
        branding: BrandingSettings | None = None,
        character_context: str | None = None,
        on_llm_task: Callable[[str, int, str], None] | None = None,
        creative_brief: str | None = None,
        video_format: str = "news",
        try_llm_4bit: bool = True,
        article_excerpt: str | None = None,
        supplement_context: str = "",
    ) -> VideoPackage:
        from src.content.brain_api import generate_script_openai

        assert isinstance(settings, AppSettings)
        _ = model_id, try_llm_4bit  # API routing uses settings.api_models, not local HF ids.
        return generate_script_openai(
            settings=settings,
            items=list(items or []),
            topic_tags=topic_tags,
            personality_id=personality_id,
            branding=branding,
            character_context=character_context,
            creative_brief=creative_brief,
            video_format=video_format,
            article_excerpt=article_excerpt,
            supplement_context=supplement_context,
            on_llm_task=on_llm_task,
        )


def get_generation_facade(settings: AppSettings) -> GenerationFacade:
    from src.runtime.model_backend import is_api_mode

    if is_api_mode(settings):
        return _ApiGenerationFacade()
    return _LocalGenerationFacade()
