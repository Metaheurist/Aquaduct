from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QWidget

from src.core.config import AppSettings

from UI.dialogs.image_playground_dialog import ImagePlaygroundDialog, resolve_image_target


class _FakeMain(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = AppSettings()
        self.worker = None
        self.tabs = None


@pytest.mark.usefixtures("patch_paths")
def test_image_playground_dialog_opens_and_closes(qapplication) -> None:
    parent = _FakeMain()
    dlg = ImagePlaygroundDialog(parent)
    dlg.show()
    try:
        assert dlg.isVisible()
        assert dlg.minimumWidth() >= 800
        assert dlg.minimumHeight() >= 520
        assert dlg.body_layout.count() > 0
        assert dlg._title_lbl.text() == "Image playground"
    finally:
        dlg.close()


@pytest.mark.usefixtures("patch_paths")
def test_resolve_image_target_local_requires_model(qapplication) -> None:
    w = _FakeMain()
    mode, label, key, err = resolve_image_target(w)
    assert mode == "local"
    assert err and "Model tab" in err
    assert not label
