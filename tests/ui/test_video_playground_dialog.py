from __future__ import annotations

import dataclasses

import pytest
from PyQt6.QtWidgets import QWidget

from src.core.config import ApiRoleConfig, AppSettings, default_api_models

from UI.dialogs.video_playground_dialog import VideoPlaygroundDialog, resolve_video_target


class _FakeMain(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = AppSettings()
        self.worker = None
        self.tabs = None


@pytest.mark.usefixtures("patch_paths")
def test_video_playground_dialog_opens_and_closes(qapplication) -> None:
    parent = _FakeMain()
    dlg = VideoPlaygroundDialog(parent)
    dlg.show()
    try:
        assert dlg.isVisible()
        assert dlg.minimumWidth() >= 800
        assert dlg.minimumHeight() >= 520
        assert dlg.body_layout.count() > 0
        assert dlg._title_lbl.text() == "Video playground"
    finally:
        dlg.close()


@pytest.mark.usefixtures("patch_paths")
def test_resolve_video_target_local_requires_model(qapplication) -> None:
    w = _FakeMain()
    mode, label, key, err = resolve_video_target(w)
    assert mode == "local"
    assert err and "Model tab" in err
    assert not label


@pytest.mark.usefixtures("patch_paths")
def test_resolve_video_target_local_ok(monkeypatch, qapplication) -> None:
    w = _FakeMain()
    monkeypatch.setattr("UI.dialogs.video_playground_dialog.is_api_mode", lambda _s: False)
    monkeypatch.setattr("UI.dialogs.video_playground_dialog.video_model_id_from_ui", lambda _win: "org/repo")

    mode, label, key, err = resolve_video_target(w)
    assert mode == "local"
    assert err is None
    assert "org/repo" in label
    assert key == "org/repo"


@pytest.mark.usefixtures("patch_paths")
def test_resolve_video_target_api_requires_key(monkeypatch, qapplication) -> None:
    w = _FakeMain()
    am = dataclasses.replace(
        default_api_models(),
        video=ApiRoleConfig(provider="replicate", model="m"),
    )
    w.settings = dataclasses.replace(w.settings, api_models=am)
    monkeypatch.setattr("UI.dialogs.video_playground_dialog.is_api_mode", lambda _s: True)
    monkeypatch.setattr("UI.dialogs.video_playground_dialog.provider_has_key", lambda _s, _p: False)

    mode, label, key, err = resolve_video_target(w)
    assert mode == "api"
    assert err and "API key" in err
    assert not label


@pytest.mark.usefixtures("patch_paths")
def test_resolve_video_target_api_ok(monkeypatch, qapplication) -> None:
    w = _FakeMain()
    am = dataclasses.replace(
        default_api_models(),
        video=ApiRoleConfig(provider="replicate", model="m"),
    )
    w.settings = dataclasses.replace(w.settings, api_models=am)
    monkeypatch.setattr("UI.dialogs.video_playground_dialog.is_api_mode", lambda _s: True)
    monkeypatch.setattr("UI.dialogs.video_playground_dialog.provider_has_key", lambda _s, _p: True)

    mode, label, key, err = resolve_video_target(w)
    assert mode == "api"
    assert err is None
    assert key == "m"
    assert "replicate" in label


@pytest.mark.usefixtures("patch_paths")
def test_video_playground_prompt_counter_updates(qapplication) -> None:
    parent = _FakeMain()
    dlg = VideoPlaygroundDialog(parent)
    dlg.show()
    try:
        assert "/" in dlg._prompt_limit_lbl.text()
        dlg._prompt.setPlainText("abc")
        assert dlg._prompt_limit_lbl.text().startswith("3 /")
    finally:
        dlg.close()