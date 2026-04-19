from __future__ import annotations

from unittest.mock import patch

from src.content.brain import ScriptSegment, VideoPackage
from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings
from src.runtime.generation_facade import get_generation_facade


def _pkg() -> VideoPackage:
    return VideoPackage(
        title="T",
        description="D",
        hashtags=["#x"],
        hook="h",
        segments=[ScriptSegment("n", "v")],
        cta="c",
    )


def test_local_facade_calls_generate_script():
    app = AppSettings(model_execution_mode="local", llm_model_id="org/llm")
    pkg = _pkg()
    with patch("src.content.brain.generate_script", return_value=pkg) as gs:
        out = get_generation_facade(app).generate_script_package(
            settings=app,
            model_id="org/llm",
            items=[{"title": "a", "url": "", "source": "t"}],
            topic_tags=["x"],
            personality_id="neutral",
            video_format="news",
        )
    assert out.title == "T"
    gs.assert_called_once()
    assert gs.call_args.kwargs["model_id"] == "org/llm"


def test_local_facade_requires_model_id():
    app = AppSettings(model_execution_mode="local")
    with patch("src.content.brain.generate_script") as gs:
        try:
            get_generation_facade(app).generate_script_package(
                settings=app,
                model_id="",
                items=[{"title": "a", "url": "", "source": "t"}],
            )
        except RuntimeError as e:
            assert "LLM" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
    gs.assert_not_called()


def test_api_facade_calls_generate_script_openai():
    app = AppSettings(
        model_execution_mode="api",
        api_openai_key="sk-test",
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
            image=ApiRoleConfig(provider="openai", model="dall-e-3"),
            voice=ApiRoleConfig(provider="openai", model="tts-1"),
        ),
    )
    pkg = _pkg()
    with patch("src.content.brain_api.generate_script_openai", return_value=pkg) as go:
        out = get_generation_facade(app).generate_script_package(
            settings=app,
            model_id="ignored",
            items=[{"title": "a", "url": "", "source": "t"}],
            topic_tags=None,
            personality_id="neutral",
            video_format="news",
        )
    assert out is pkg
    go.assert_called_once()
    assert go.call_args.kwargs["settings"] is app
