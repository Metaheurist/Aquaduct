"""ThemedSwitch API parity with QCheckBox."""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_themed_switch_toggle_and_signal(qtbot, qapplication):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from UI.widgets.themed_switch import ThemedSwitch

    sw = ThemedSwitch("Test")
    qtbot.addWidget(sw)
    sw.show()
    qapplication.processEvents()

    toggled: list[bool] = []
    sw.toggled.connect(toggled.append)

    assert not sw.isChecked()
    QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
    qapplication.processEvents()
    assert sw.isChecked()
    assert toggled == [True]

    sw.setChecked(False)
    assert not sw.isChecked()


@pytest.mark.qt
def test_themed_switch_animation_is_owned_by_switch(qtbot, qapplication):
    from PyQt6.QtTest import QTest

    from UI.widgets.themed_switch import ThemedSwitch

    sw = ThemedSwitch("Owned")
    qtbot.addWidget(sw)
    sw.setChecked(True)
    anim = sw._anim
    assert anim is not None
    assert anim.parent() is sw

    destroyed: list[bool] = []
    anim.destroyed.connect(lambda *_: destroyed.append(True))
    sw.setChecked(False)
    sw.deleteLater()
    QTest.qWait(200)
    qapplication.processEvents()
    assert destroyed
