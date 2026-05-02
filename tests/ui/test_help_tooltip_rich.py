from __future__ import annotations

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QHelpEvent, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QListView

from UI.help.tutorial_links import (
    _rich_help_tooltip_text,
    help_tooltip_rich,
    help_tooltip_rich_unless_already,
)


def test_help_tooltip_rich_emits_html_and_topic_url() -> None:
    html = help_tooltip_rich("Hello & world.\nLine two.", "welcome", slide=2)
    assert html.strip().lower().startswith("<html")
    assert "topic://welcome?slide=2" in html
    assert "Hello &amp; world." in html


def test_help_tooltip_rich_default_slide_zero() -> None:
    html = help_tooltip_rich("x", "run", slide=None)
    assert "topic://run?slide=0" in html


def test_help_tooltip_rich_unless_already_plain_wraps_once() -> None:
    wrapped = help_tooltip_rich_unless_already("Line1\nLine2", "models", slide=0)
    assert wrapped.startswith("<html")
    assert "&lt;html" not in wrapped
    assert "Line1" in wrapped
    assert "topic://models" in wrapped


def test_help_tooltip_rich_unless_already_skips_double_wrap() -> None:
    inner = help_tooltip_rich("Body", "models", slide=2)
    again = help_tooltip_rich_unless_already(inner, "models", slide=0)
    assert again == inner
    assert "&lt;body" not in again


def test_rich_help_tooltip_text_reads_tool_tip_role_on_viewport(qapplication) -> None:
    """Combo/list popups: HTML lives on the model item; hover target is often the viewport."""
    html = help_tooltip_rich("Line1\nLine2", "models", slide=0)
    m = QStandardItemModel()
    item = QStandardItem("row")
    item.setToolTip(html)
    m.appendRow(item)

    lv = QListView()
    lv.setModel(m)
    lv.resize(320, 120)
    lv.show()
    QApplication.processEvents()

    idx = m.index(0, 0)
    rect = lv.visualRect(idx)
    assert rect.width() > 0 and rect.height() > 0
    center_vp = rect.center()
    gpos = lv.viewport().mapToGlobal(center_vp)
    ev = QHelpEvent(QEvent.Type.ToolTip, center_vp, gpos)
    resolved = _rich_help_tooltip_text(lv.viewport(), ev)
    assert resolved.strip().lower().startswith("<html")
    assert "topic://models" in resolved
    assert "Line1" in resolved
