from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")
pytestmark = pytest.mark.qt


def test_toast_fades_out_and_deletes_itself(qtbot) -> None:
    from PyQt6.QtWidgets import QWidget

    from UI.widgets.toast import _Toast, show_toast

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    show_toast(host, "Saved", msec=600)
    assert host.findChildren(_Toast)
    qtbot.waitUntil(lambda: not host.findChildren(_Toast), timeout=3000)


def test_toast_pending_fade_out_survives_host_destruction(qtbot) -> None:
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QWidget

    from UI.widgets.toast import show_toast

    host = QWidget()
    host.resize(400, 300)
    show_toast(host, "Saved", msec=600)
    host.deleteLater()
    QTest.qWait(1000)
