"""Tab-level tests for UI modernization (2026 polish pass)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QTabWidget, QWidget


class _WinStub(QWidget):
    """Minimal QWidget host for attach_* tab builders in unit tests."""

    def __getattr__(self, name: str):
        if name.startswith("_"):

            def _noop(*_a, **_k):
                return None

            return _noop
        raise AttributeError(name)


@pytest.mark.qt
def test_apply_media_mode_ui_toggles_branding_sections(qapplication):
    from UI.main_window import MainWindow
    from src.core.config import AppSettings

    host = MagicMock()
    host.settings = replace(AppSettings(), media_mode="video")
    host.tabs = QTabWidget()
    host.brand_video_style_section = MagicMock()
    host.brand_watermark_section = MagicMock()
    host.brand_photo_section = MagicMock()

    MainWindow._apply_media_mode_ui(host)
    host.brand_video_style_section.setVisible.assert_called_with(True)
    host.brand_watermark_section.setVisible.assert_called_with(True)
    host.brand_photo_section.setVisible.assert_called_with(False)

    host.brand_video_style_section.reset_mock()
    host.brand_watermark_section.reset_mock()
    host.brand_photo_section.reset_mock()
    host.settings = replace(host.settings, media_mode="photo")
    MainWindow._apply_media_mode_ui(host)
    host.brand_video_style_section.setVisible.assert_called_with(False)
    host.brand_watermark_section.setVisible.assert_called_with(False)
    host.brand_photo_section.setVisible.assert_called_with(True)


@pytest.mark.qt
def test_branding_tab_section_containers(qapplication, patch_paths, write_ui_settings):
    write_ui_settings({"topic_tags": []})
    from UI.tabs.branding_tab import attach_branding_tab
    from src.core.config import AppSettings

    win = _WinStub()
    win.tabs = QTabWidget()
    win.settings = AppSettings()
    attach_branding_tab(win)
    assert hasattr(win, "brand_video_style_section")
    assert hasattr(win, "brand_photo_section")
    assert hasattr(win, "brand_watermark_section")
    assert hasattr(win, "brand_watermark_browse_btn")


@pytest.mark.qt
def test_topics_tab_chip_layout(qapplication, patch_paths, write_ui_settings):
    from UI.tabs.topics_tab import attach_topics_tab
    from src.core.config import AppSettings
    from UI.widgets.flow_layout import FlowLayout

    win = _WinStub()
    win.tabs = QTabWidget()
    win.settings = AppSettings()
    attach_topics_tab(win)
    assert hasattr(win, "tag_chips_layout")
    assert hasattr(win, "topic_selected_note_edit")
    assert isinstance(win.tag_chips_layout, FlowLayout)


def test_settings_tab_no_install_deps_button_in_source():
    from pathlib import Path

    text = Path("UI/tabs/settings_tab.py").read_text(encoding="utf-8")
    assert "install_deps_btn" not in text
    assert "models_storage_mode_combo" in text


@pytest.mark.qt
def test_library_tab_side_by_side_cards(qapplication, patch_paths, write_ui_settings):
    from UI.tabs.library_tab import attach_library_tab
    from src.core.config import AppSettings

    win = _WinStub()
    win.tabs = QTabWidget()
    win.settings = AppSettings()
    attach_library_tab(win)
    media = win._library_media_card
    parent = media.parentWidget()
    assert parent is not None
    assert parent.layout() is not None
    assert parent.layout().count() == 2


@pytest.mark.qt
def test_api_tab_generation_panel_tooltip(qapplication, patch_paths, write_ui_settings):
    from UI.tabs.api_tab import attach_api_tab
    from src.core.config import AppSettings

    win = _WinStub()
    win.tabs = QTabWidget()
    win.settings = AppSettings()
    attach_api_tab(win)
    assert win.generation_api_panel.toolTip()
