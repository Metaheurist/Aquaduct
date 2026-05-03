from __future__ import annotations

import pytest


@pytest.mark.qt
def test_run_tab_includes_nsfw_video_format(qapplication, patch_paths, write_ui_settings) -> None:
    write_ui_settings({"topic_tags": []})
    from UI.main_window import MainWindow

    w = MainWindow()
    combo = w.video_format_combo
    ids = [combo.itemData(i) for i in range(combo.count())]
    assert "nsfw" in ids


@pytest.mark.qt
def test_nsfw_video_format_keeps_auto_upload_enabled_when_session_guardrail_bypass_env(monkeypatch: pytest.MonkeyPatch, qapplication, patch_paths, write_ui_settings) -> None:
    monkeypatch.setenv("AQUADUCT_DEV_DISABLE_CONTENT_GUARDRAILS", "1")
    write_ui_settings({"topic_tags": []})
    from UI.main_window import MainWindow

    w = MainWindow()
    ix = w.video_format_combo.findData("nsfw")
    assert ix >= 0
    w.video_format_combo.setCurrentIndex(ix)
    assert w.api_tt_auto_upload_chk.isEnabled() is True
    assert w.api_yt_auto_upload_chk.isEnabled() is True


@pytest.mark.qt
def test_nsfw_video_format_disables_auto_upload_toggles(qapplication, patch_paths, write_ui_settings) -> None:
    write_ui_settings({"topic_tags": []})
    from UI.main_window import MainWindow

    w = MainWindow()
    ix = w.video_format_combo.findData("nsfw")
    assert ix >= 0
    w.video_format_combo.setCurrentIndex(ix)
    assert w.api_tt_auto_upload_chk.isEnabled() is False
    assert w.api_yt_auto_upload_chk.isEnabled() is False
    w.video_format_combo.setCurrentIndex(0)
    assert w.api_tt_auto_upload_chk.isEnabled() is True
    assert w.api_yt_auto_upload_chk.isEnabled() is True
