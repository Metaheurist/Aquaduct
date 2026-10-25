from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")
pytestmark = pytest.mark.qt


def test_library_search_refills_once_after_typing_pauses(built_main_window, qtbot, monkeypatch) -> None:
    import UI.tabs.library_tab as library_tab

    calls: list[int] = []
    real_scan = library_tab.scan_finished_videos

    def _counting_scan(path):  # noqa: ANN001
        calls.append(1)
        return real_scan(path)

    monkeypatch.setattr(library_tab, "scan_finished_videos", _counting_scan)
    w = built_main_window()
    calls.clear()

    for text in ("c", "ca", "cat"):
        w.library_search_edit.setText(text)
    assert calls == []
    qtbot.waitUntil(lambda: len(calls) >= 1, timeout=3000)
    from PyQt6.QtTest import QTest

    QTest.qWait(400)
    assert len(calls) == 1
