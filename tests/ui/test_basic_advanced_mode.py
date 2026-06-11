"""Per-tab Basic/Advanced persistence and harvest invariance."""

from __future__ import annotations

from dataclasses import replace

import pytest


@pytest.mark.qt
def test_segmented_picker_renders_shell(qtbot, qapplication):
    from PyQt6.QtWidgets import QToolButton

    from UI.widgets.segmented_picker import SegmentOption, SegmentedPicker

    picker = SegmentedPicker(
        [SegmentOption("Basic", "basic"), SegmentOption("Advanced", "advanced")],
        object_name_shell="TestSegmentedPickerShell",
    )
    qtbot.addWidget(picker)
    picker.show()
    qapplication.processEvents()
    assert picker.sizeHint().width() > 80
    buttons = picker.findChildren(QToolButton)
    assert len(buttons) == 2
    assert any(b.text() == "Basic" for b in buttons)
    assert any(b.text() == "Advanced" for b in buttons)


@pytest.mark.qt
def test_advanced_tabs_persist_roundtrip(qtbot, qapplication, tmp_path, monkeypatch):
    from src.core.config import AppSettings
    from src.settings import ui_settings
    from UI.widgets.basic_advanced import is_tab_advanced, set_tab_advanced

    class _Win:
        settings = AppSettings()

    win = _Win()
    assert not is_tab_advanced(win.settings, "pipeline")
    set_tab_advanced(win, "pipeline", True, persist=False)
    assert is_tab_advanced(win.settings, "pipeline")

    path = tmp_path / "ui_settings.json"
    monkeypatch.setattr(ui_settings, "settings_path", lambda: path)
    win.settings = replace(win.settings, advanced_tabs={"video": True, "api": False})
    assert ui_settings.save_settings(win.settings)

    loaded = ui_settings.load_settings()
    assert loaded.advanced_tabs.get("video") is True
    assert loaded.advanced_tabs.get("api") is False


@pytest.mark.qt
def test_harvest_invariant_when_advanced_hidden(qtbot, monkeypatch):
    """collect_settings_from_ui output must not depend on Advanced visibility."""
    from src.settings.ui_harvest import collect_settings_from_ui

    try:
        from UI.main_window import MainWindow
    except Exception as exc:
        pytest.skip(f"MainWindow unavailable: {exc}")

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    win = MainWindow()
    qtbot.addWidget(win)

    if hasattr(win, "_attach_deferred_tabs"):
        try:
            win._attach_deferred_tabs()
        except Exception:
            pass

    if not hasattr(win, "_tab_advanced_sections") or not hasattr(win, "fps_spin"):
        pytest.skip("deferred tabs not fully attached")

    before = collect_settings_from_ui(win)

    for sections in win._tab_advanced_sections.values():
        for w in sections:
            if w is not None:
                w.setVisible(True)

    after_show = collect_settings_from_ui(win)

    for sections in win._tab_advanced_sections.values():
        for w in sections:
            if w is not None:
                w.setVisible(False)

    after_hide = collect_settings_from_ui(win)

    assert before.video_format == after_show.video_format == after_hide.video_format
    assert before.run_content_mode == after_show.run_content_mode == after_hide.run_content_mode
    assert before.advanced_tabs == after_show.advanced_tabs == after_hide.advanced_tabs
