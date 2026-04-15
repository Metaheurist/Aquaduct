from __future__ import annotations

import pytest


@pytest.mark.qt
def test_branding_tab_live_applies_preset_theme(qtbot, patch_paths, write_ui_settings):
    # Start with defaults so MainWindow builds normally.
    write_ui_settings({"topic_tags": []})
    from PyQt6.QtWidgets import QApplication
    from UI.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()

    app = QApplication.instance()
    assert app is not None
    # Branding tab attaches and applies default stylesheet at least once.
    assert "#0F0F10" in (app.styleSheet() or "")

    # Enable theme overrides and select Ocean preset.
    w.brand_theme_enable.setChecked(True)
    idx = w.brand_palette_combo.findData("ocean")
    assert idx >= 0
    w.brand_palette_combo.setCurrentIndex(idx)

    # Ocean bg should be present after live apply.
    assert "#07161C" in (app.styleSheet() or "")


@pytest.mark.qt
def test_branding_tab_video_style_controls_enable(qtbot, patch_paths, write_ui_settings):
    write_ui_settings({"topic_tags": []})
    from UI.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()

    # Strength dropdown should be disabled until video style is enabled.
    assert w.brand_video_style_strength.isEnabled() is False
    w.brand_video_style_enable.setChecked(True)
    assert w.brand_video_style_strength.isEnabled() is True
    # Can select strong
    idx = w.brand_video_style_strength.findData("strong")
    assert idx >= 0
    w.brand_video_style_strength.setCurrentIndex(idx)

