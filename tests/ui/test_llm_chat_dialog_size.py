from __future__ import annotations

import dataclasses

import pytest
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from UI.dialogs.llm_chat_dialog import LLMChatDialog
from src.core.config import AppSettings, LLMChatGeometry


class _FakeMain(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = AppSettings()


@pytest.mark.usefixtures("patch_paths")
def test_llm_chat_dialog_minimum_and_initial_resize(qapplication) -> None:
    parent = _FakeMain()
    parent.setGeometry(100, 100, 1200, 900)
    dlg = LLMChatDialog(parent)
    assert dlg.minimumWidth() >= 720
    assert dlg.minimumHeight() >= 600
    dlg.show()
    try:
        assert dlg.width() >= 720
        assert dlg.height() >= 600
    finally:
        dlg.close()


@pytest.mark.usefixtures("patch_paths")
def test_llm_chat_dialog_persists_geometry_on_close(monkeypatch, qapplication, patch_paths) -> None:
    captured: list[AppSettings] = []

    def capture_save(settings: AppSettings) -> None:
        captured.append(settings)

    monkeypatch.setattr("UI.dialogs.llm_chat_dialog.save_settings", capture_save)

    parent = _FakeMain()
    parent.setGeometry(100, 100, 1200, 900)
    dlg = LLMChatDialog(parent)
    dlg.show()
    # First showEvent runs _apply_initial_geometry(); resize after so closeEvent sees intended values.
    dlg.resize(801, 702)
    dlg.move(150, 250)
    try:
        pass
    finally:
        dlg.close()

    assert captured, "save_settings should run from closeEvent"
    geo = captured[-1].llm_chat_geometry
    assert geo.width == 801
    assert geo.height == 702
    assert geo.x == 150
    assert geo.y == 250


@pytest.mark.usefixtures("patch_paths")
def test_llm_chat_dialog_restores_saved_geometry(qapplication, patch_paths) -> None:
    parent = _FakeMain()
    saved = LLMChatGeometry(width=830, height=610, x=12, y=14)
    parent.settings = dataclasses.replace(parent.settings, llm_chat_geometry=saved)
    dlg = LLMChatDialog(parent)
    dlg.show()
    try:
        scr = QGuiApplication.primaryScreen()
        assert scr is not None
        ag = scr.availableGeometry()
        exp_w = max(dlg.minimumWidth(), min(830, ag.width() - 24))
        exp_h = max(dlg.minimumHeight(), min(610, ag.height() - 24))
        assert dlg.width() == exp_w
        assert dlg.height() == exp_h
        exp_x = max(ag.left(), min(12, ag.right() - dlg.width() + 1))
        exp_y = max(ag.top(), min(14, ag.bottom() - dlg.height() + 1))
        assert dlg.x() == exp_x
        assert dlg.y() == exp_y
    finally:
        dlg.close()
