"""Basic|Advanced mode on optional tabs and API cloud presets."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


@dataclass
class _MockSettings:
    advanced_tabs: dict[str, bool] = field(default_factory=dict)
    branding: object = None
    media_mode: str = "video"


def _make_mock_win():
    from PyQt6.QtWidgets import QTabWidget

    class _MockWin:
        def __init__(self) -> None:
            self.settings = _MockSettings()
            self.tabs = QTabWidget()
            self._tab_advanced_sections: dict[str, list] = {}

    return _MockWin()


@pytest.mark.qt
def test_tasks_tab_registers_advanced_sections(qtbot, qapplication):
    from UI.tabs.tasks_tab import attach_tasks_tab
    from UI.widgets.basic_advanced import is_tab_advanced

    win = _make_mock_win()
    win._tasks_refresh = lambda: None
    win._on_tasks_pause_toggle = lambda: None
    win._on_tasks_stop = lambda: None
    win._tasks_open_folder = lambda: None
    win._tasks_play_video = lambda: None
    win._tasks_copy_caption = lambda: None
    win._tasks_approve_selected = lambda: None
    win._tasks_mark_posted_manual = lambda: None
    win._tasks_upload_tiktok = lambda: None
    win._tasks_upload_youtube = lambda: None
    win._tasks_remove_selected = lambda: None
    qtbot.addWidget(win.tabs)
    attach_tasks_tab(win)
    qapplication.processEvents()
    assert "tasks" in win._tab_advanced_sections
    assert len(win._tab_advanced_sections["tasks"]) >= 2
    assert not is_tab_advanced(win.settings, "tasks")


@pytest.mark.qt
def test_api_cloud_preset_grid_on_panel(qtbot, qapplication):
    from UI.services.api_model_widgets import build_generation_api_panel
    from src.core.config import AppSettings

    class _Win:
        settings = AppSettings()

    win = _Win()
    panel = build_generation_api_panel(win)
    qtbot.addWidget(panel)
    grid = getattr(win, "_api_cloud_presets", None)
    assert grid is not None
    assert grid.currentData() in ("gemini_free", "openai", "replicate", "budget")
    grid.setCurrentData("openai")
    assert str(win.api_gen_llm_provider.currentData() or "") == "openai"
