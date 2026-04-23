from __future__ import annotations

import pytest

from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings, VideoSettings, default_api_models
from src.runtime import model_backend as mb


def test_is_api_mode_false_by_default():
    assert not mb.is_api_mode(AppSettings())
    assert not mb.is_api_mode(None)


def test_is_api_mode_true():
    s = AppSettings(model_execution_mode="api")
    assert mb.is_api_mode(s)


def test_effective_openai_api_key_env_wins(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    s = AppSettings(api_openai_key="sk-saved")
    assert mb.effective_openai_api_key(s) == "sk-from-env"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_effective_openai_api_key_saved_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = AppSettings(api_openai_key="sk-saved")
    assert mb.effective_openai_api_key(s) == "sk-saved"


def test_effective_replicate_token_either_env_key(monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.delenv("REPLICATE_API_KEY", raising=False)
    monkeypatch.setenv("REPLICATE_API_KEY", "tok-alt")
    s = AppSettings(api_replicate_token="")
    assert mb.effective_replicate_api_token(s) == "tok-alt"
    monkeypatch.delenv("REPLICATE_API_KEY", raising=False)


def test_role_filled():
    assert not mb.role_filled(ApiRoleConfig())
    assert mb.role_filled(ApiRoleConfig(provider="openai", model="gpt-4o-mini"))


def test_provider_has_key_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not mb.provider_has_key(AppSettings(), "openai")
    assert mb.provider_has_key(AppSettings(api_openai_key="sk-x"), "openai")


def test_effective_llm_api_key_groq_env(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = AppSettings(api_openai_key="sk-shared")
    assert mb.effective_llm_api_key(s, "groq") == "sk-shared"
    monkeypatch.setenv("GROQ_API_KEY", "gsk-env")
    assert mb.effective_llm_api_key(s, "groq") == "gsk-env"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def test_provider_has_key_groq(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not mb.provider_has_key(AppSettings(api_openai_key=""), "groq")
    assert mb.provider_has_key(AppSettings(api_openai_key="gsk-x"), "groq")


def test_api_preflight_errors_empty_when_local():
    s = AppSettings(model_execution_mode="local")
    assert mb.api_preflight_errors(s) == []


def test_api_preflight_errors_missing_role_config():
    s = AppSettings(
        model_execution_mode="api",
        api_models=default_api_models(),
    )
    errs = mb.api_preflight_errors(s)
    assert len(errs) >= 3
    assert any("LLM" in e for e in errs)


def test_api_preflight_photo_only_needs_llm_and_image():
    am = ApiModelRuntimeSettings(
        llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
        image=ApiRoleConfig(provider="openai", model="dall-e-3"),
        voice=ApiRoleConfig(provider="", model=""),
        video=ApiRoleConfig(provider="", model=""),
    )
    s = AppSettings(model_execution_mode="api", media_mode="photo", api_openai_key="sk-x", api_models=am)
    assert mb.api_preflight_errors(s) == []


def test_api_preflight_errors_missing_key_with_roles_filled(monkeypatch):
    # Ensure env does not satisfy OpenAI (some dev machines export OPENAI_API_KEY globally).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    am = ApiModelRuntimeSettings(
        llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
        image=ApiRoleConfig(provider="openai", model="dall-e-3"),
        voice=ApiRoleConfig(provider="openai", model="tts-1"),
        video=ApiRoleConfig(),
    )
    s = AppSettings(model_execution_mode="api", api_models=am, api_openai_key="")
    errs = mb.api_preflight_errors(s)
    assert any("missing api key" in e.lower() for e in errs)


def test_api_preflight_motion_without_pro_errors():
    v = VideoSettings(use_image_slideshow=False, pro_mode=False)
    am = ApiModelRuntimeSettings(
        llm=ApiRoleConfig(provider="openai", model="m"),
        image=ApiRoleConfig(provider="openai", model="m"),
        voice=ApiRoleConfig(provider="openai", model="m"),
    )
    s = AppSettings(model_execution_mode="api", video=v, api_openai_key="k", api_models=am)
    errs = mb.api_preflight_errors(s)
    assert any("slideshow" in e.lower() or "replicate" in e.lower() for e in errs)


def test_assert_api_runtime_ready_raises():
    s = AppSettings(model_execution_mode="api", api_models=default_api_models())
    with pytest.raises(RuntimeError, match="API mode is not ready"):
        mb.assert_api_runtime_ready(s)


def test_resolve_model_execution_mode():
    assert mb.resolve_model_execution_mode(AppSettings()) == "local"
    assert mb.resolve_model_execution_mode(AppSettings(model_execution_mode="api")) == "api"
    assert mb.resolve_model_execution_mode(AppSettings(model_execution_mode="bogus")) == "local"


def test_resolve_local_vs_api():
    assert mb.resolve_local_vs_api(None) == "local"
    assert mb.resolve_local_vs_api(AppSettings(model_execution_mode="api")) == "api"


def test_api_role_ready():
    s = AppSettings(model_execution_mode="local", api_openai_key="sk-x")
    assert not mb.api_role_ready(s, "llm")
    s_api = AppSettings(
        model_execution_mode="api",
        api_openai_key="sk-x",
        api_models=ApiModelRuntimeSettings(llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini")),
    )
    assert mb.api_role_ready(s_api, "llm")
    assert not mb.api_role_ready(s_api, "image")
