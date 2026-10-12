from __future__ import annotations

import pytest


@pytest.mark.qt
def test_model_execution_mode_toggle_hides_download_button(built_main_window):
    """API mode on the Model tab hides the Hugging Face Download menu (local weights)."""
    w = built_main_window({"topic_tags": [], "model_execution_mode": "local"})

    assert hasattr(w, "dl_menu_btn")
    assert hasattr(w, "model_execution_mode_combo")

    model_idx = next((i for i in range(w.tabs.count()) if w.tabs.tabText(i).strip() == "Model"), -1)
    assert model_idx >= 0
    w.tabs.setCurrentIndex(model_idx)

    w.model_execution_mode_combo.setCurrentIndex(0)
    assert w.dl_menu_btn.isVisible()

    w.model_execution_mode_combo.setCurrentIndex(1)
    assert not w.dl_menu_btn.isVisible()

    w.model_execution_mode_combo.setCurrentIndex(0)
    assert w.dl_menu_btn.isVisible()
