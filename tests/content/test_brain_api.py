from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.content.character_presets import CharacterAutoPreset
from src.content.brain_api import (
    expand_custom_field_text_openai,
    expand_custom_video_instructions_openai,
    generate_character_from_preset_openai,
    generate_script_openai,
)
from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings


def _minimal_app() -> AppSettings:
    return AppSettings(
        model_execution_mode="api",
        api_openai_key="sk-test",
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
        ),
    )


def test_generate_script_openai_parses_json_package():
    app = _minimal_app()
    raw_json = (
        '{"title":"T","description":"D","hashtags":["#Shorts"],'
        '"hook":"h","segments":[{"narration":"n1","visual_prompt":"v1","on_screen_text":null}],'
        '"cta":"c"}'
    )
    fake = MagicMock()
    fake.chat_completion_text.return_value = raw_json
    with patch("src.content.brain_api.build_openai_client_from_settings", return_value=fake):
        pkg = generate_script_openai(
            settings=app,
            items=[{"title": "News", "url": "https://x", "source": "test"}],
            topic_tags=["tech"],
            personality_id="neutral",
            branding=None,
            character_context=None,
            creative_brief=None,
            video_format="news",
            article_excerpt="",
        )
    assert pkg.title == "T"
    assert len(pkg.segments) == 1
    assert pkg.segments[0].narration == "n1"
    fake.chat_completion_text.assert_called_once()


def test_expand_custom_video_instructions_openai():
    app = _minimal_app()
    fake = MagicMock()
    fake.chat_completion_text.return_value = "  Expanded brief here.  "
    with patch("src.content.brain_api.build_openai_client_from_settings", return_value=fake):
        out = expand_custom_video_instructions_openai(
            settings=app,
            raw_instructions="make it funny",
            video_format="news",
            personality_id="neutral",
        )
    assert "Expanded" in out


def test_generate_character_from_preset_openai_parses_json():
    app = _minimal_app()
    raw = (
        '{"name":"Alex","identity":"Warm host.","visual_style":"Studio lighting, casual blazer.",'
        '"negatives":"blur, watermark","use_default_voice":true}'
    )
    fake = MagicMock()
    fake.chat_completion_text.return_value = raw
    preset = CharacterAutoPreset(
        id="test",
        label="Host",
        llm_directive="Friendly explainer.",
    )
    with patch("src.content.brain_api.build_openai_client_from_settings", return_value=fake):
        fields = generate_character_from_preset_openai(settings=app, preset=preset, extra_notes="")
    assert fields.name == "Alex"
    assert "Warm" in fields.identity
    fake.chat_completion_text.assert_called_once()


def test_expand_custom_field_text_openai():
    app = _minimal_app()
    fake = MagicMock()
    fake.chat_completion_text.return_value = "Better label text"
    with patch("src.content.brain_api.build_openai_client_from_settings", return_value=fake):
        out = expand_custom_field_text_openai(settings=app, field_label="Title", seed="x")
    assert out == "Better label text"
