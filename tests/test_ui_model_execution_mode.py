from __future__ import annotations

import pytest


@pytest.mark.qt
def test_model_execution_mode_toggle_hides_download_button(patch_paths, write_ui_settings):
    """API mode on the Model tab hides the Hugging Face Download menu (local weights)."""
    pytest.importorskip("PyQt6.QtWidgets")
    write_ui_settings({"topic_tags": []})
    from PyQt6.QtWidgets import QApplication
    from UI.main_window import MainWindow

    if QApplication.instance() is None:
        _ = QApplication([])

    w = MainWindow()
    w.show()

    assert hasattr(w, "dl_menu_btn")
    assert hasattr(w, "model_execution_mode_combo")

    w.model_execution_mode_combo.setCurrentIndex(0)
    assert w.dl_menu_btn.isVisible()

    w.model_execution_mode_combo.setCurrentIndex(1)
    assert not w.dl_menu_btn.isVisible()

    w.model_execution_mode_combo.setCurrentIndex(0)
    assert w.dl_menu_btn.isVisible()
    w.close()
