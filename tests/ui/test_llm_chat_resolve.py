"""Tests for LLM chat target resolution (no Qt widgets required for settings-only cases)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from UI.dialogs.llm_chat_dialog import resolve_chat_target
from src.core.config import ApiRoleConfig, AppSettings, default_api_models


def test_resolve_chat_target_api_missing_key() -> None:
    st = AppSettings()
    st = replace(st, model_execution_mode="api")
    st = replace(st, api_models=default_api_models())
    st = replace(
        st,
        api_models=replace(
            st.api_models,
            llm=ApiRoleConfig(provider="openai", model="gpt-4o-mini"),
        ),
    )
    # No secrets / keys on mock settings — provider_has_key should fail
    win = MagicMock()
    win.settings = st
    mode, label, key, err = resolve_chat_target(win)
    assert mode == "api"
    assert err
    assert "key" in err.lower() or "missing" in err.lower()


def test_resolve_chat_target_local_uses_settings_when_no_combo() -> None:
    st = AppSettings()
    st = replace(st, llm_model_id="org/Some-Model")
    win = MagicMock()
    win.settings = st
    del win.llm_combo  # attribute missing
    mode, label, key, err = resolve_chat_target(win)
    assert err is None
    assert mode == "local"
    assert key == "org/Some-Model"
    assert "Some-Model" in label


def test_resolve_chat_target_local_prefers_combo_data() -> None:
    st = AppSettings()
    st = replace(st, llm_model_id="settings/repo")
    win = MagicMock()
    win.settings = st
    combo = MagicMock()
    combo.currentData.return_value = "combo/repo"
    win.llm_combo = combo
    mode, _label, key, err = resolve_chat_target(win)
    assert err is None
    assert key == "combo/repo"
    assert mode == "local"
