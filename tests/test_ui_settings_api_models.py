from __future__ import annotations

import json

from src.core.config import ApiModelRuntimeSettings, ApiRoleConfig, AppSettings
from src.settings.ui_settings import load_settings, save_settings


def test_save_roundtrip_api_models(tmp_path, monkeypatch):
    from src.settings import ui_settings as us

    p = tmp_path / "ui_settings.json"
    monkeypatch.setattr(us, "settings_path", lambda: p)

    s = AppSettings(
        model_execution_mode="api",
        api_openai_key="sk-test",
        api_replicate_token="r8_test",
        api_models=ApiModelRuntimeSettings(
            llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini", base_url="", org_id=""),
            image=ApiRoleConfig(provider="openai", model="dall-e-3"),
            video=ApiRoleConfig(provider="replicate", model="ver123"),
            voice=ApiRoleConfig(provider="openai", model="tts-1", voice_id="alloy"),
        ),
    )
    assert save_settings(s) is True
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw.get("model_execution_mode") == "api"
    assert raw.get("api_openai_key") == "sk-test"
    am = raw.get("api_models")
    assert isinstance(am, dict)
    assert am["llm"]["provider"] == "openai"
    assert am["voice"]["voice_id"] == "alloy"

    loaded = load_settings()
    assert loaded.model_execution_mode == "api"
    assert loaded.api_openai_key == "sk-test"
    assert loaded.api_models.llm.model == "gpt-4o-mini"


def test_load_tolerates_extra_keys(tmp_path, monkeypatch):
    from src.settings import ui_settings as us

    p = tmp_path / "ui_settings.json"
    p.write_text(
        json.dumps(
            {
                "model_execution_mode": "local",
                "api_models": {"llm": {"provider": "openai", "model": "x", "future_key": 1}},
                "unknown_top_level": {"nested": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(us, "settings_path", lambda: p)
    s = load_settings()
    assert s.model_execution_mode == "local"
    assert s.api_models.llm.provider == "openai"
