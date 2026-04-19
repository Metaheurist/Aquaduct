from __future__ import annotations

import pytest


@pytest.mark.qt
def test_model_execution_mode_toggle_data_and_index():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        _ = QApplication([])

    from UI.model_execution_toggle import ModelExecutionModeToggle

    t = ModelExecutionModeToggle()
    assert t.currentData() == "local"
    assert t.currentIndex() == 0
    t.setCurrentIndex(1)
    assert t.currentData() == "api"
    assert t.currentIndex() == 1
    t.setCurrentIndex(0)
    assert t.currentData() == "local"
