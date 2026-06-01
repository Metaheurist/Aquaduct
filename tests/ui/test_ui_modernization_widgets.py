"""Unit tests for UI modernization widgets (2026 polish pass)."""

from __future__ import annotations

import pytest


def _mouse_click(qapplication, widget) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    qapplication.processEvents()


@pytest.mark.qt
def test_flow_layout_wraps_to_second_row(qapplication):
    from PyQt6.QtWidgets import QLabel, QWidget

    from UI.widgets.flow_layout import FlowLayout

    host = QWidget()
    host.setFixedWidth(120)
    lay = FlowLayout(host, h_spacing=4, v_spacing=4)
    labels = []
    for text in ("alpha", "beta", "gamma"):
        lbl = QLabel(text)
        lbl.setFixedSize(60, 24)
        lbl.show()
        labels.append(lbl)
        lay.addWidget(lbl)
    host.show()
    qapplication.processEvents()
    h_narrow = lay.heightForWidth(120)
    h_wide = lay.heightForWidth(400)
    assert h_narrow > h_wide


@pytest.mark.qt
def test_two_column_row_stretch_ratios(qapplication):
    from PyQt6.QtWidgets import QLabel

    from UI.widgets.two_column import two_column_row

    left = QLabel("L")
    right = QLabel("R")
    row = two_column_row(left, right, ratio=(2, 1))
    hlay = row.layout()
    assert hlay is not None
    assert hlay.stretch(0) == 2
    assert hlay.stretch(1) == 1


@pytest.mark.qt
def test_topic_chip_select_signal(qtbot, qapplication):
    from UI.widgets.topic_chip import TopicChip

    selected: list[str] = []
    chip = TopicChip("climate", is_selected=False)
    qtbot.addWidget(chip)
    chip.selected.connect(selected.append)

    _mouse_click(qapplication, chip._pill)
    assert selected == ["climate"]
    chip.set_selected(True)
    assert chip._pill.isChecked()


@pytest.mark.qt
def test_topic_chip_remove_via_toolbutton(qtbot, qapplication):
    from PyQt6.QtWidgets import QToolButton

    from UI.widgets.topic_chip import TopicChip

    removed: list[str] = []
    chip = TopicChip("news")
    qtbot.addWidget(chip)
    chip.removed.connect(removed.append)
    rm = chip.findChild(QToolButton)
    assert rm is not None
    _mouse_click(qapplication, rm)
    assert removed == ["news"]


@pytest.mark.qt
def test_character_card_emits_selected(qtbot, qapplication):
    from src.content.characters_store import Character

    from UI.widgets.character_card import CharacterCard

    c = Character(id="c1", name="Host", identity="Friendly anchor")
    picked: list[str] = []
    card = CharacterCard(c)
    qtbot.addWidget(card)
    card.selected.connect(picked.append)
    _mouse_click(qapplication, card)
    assert picked == ["c1"]


@pytest.mark.qt
def test_status_glyph_label_and_set_text(qapplication):
    from PyQt6.QtWidgets import QLabel

    from UI.widgets.tab_sections import status_glyph_label, status_glyph_set_text

    row = status_glyph_label("check", "Ready", color_token="accent")
    text_w = row.layout().itemAt(1).widget()
    assert isinstance(text_w, QLabel)
    assert text_w.text() == "Ready"
    status_glyph_set_text(row, "Missing deps", kind="warning", color_token="danger")
    assert row.layout().itemAt(1).widget().text() == "Missing deps"


@pytest.mark.qt
def test_toolbar_svg_icon_kinds_non_null(qapplication):
    from UI.widgets.toolbar_svg_icons import ToolbarIconKind, pixmap_toolbar, qicon_toolbar

    kinds: list[ToolbarIconKind] = [
        "check",
        "cross",
        "dot",
        "half",
        "warning",
        "info",
        "chevron_right",
        "chevron_down",
        "arrow_left",
        "arrow_right",
        "sparkles",
        "pause",
        "play",
    ]
    for kind in kinds:
        pm = pixmap_toolbar(kind, "#25F4EE", size=16)
        assert not pm.isNull(), kind
        icon = qicon_toolbar(kind, "#25F4EE", 16)
        assert not icon.isNull(), kind


def test_load_heartbeat_ram_warning_has_no_glyph():
    from src.runtime import load_heartbeat as lb

    lb.set_load_heartbeat_notice("Still loading x — 10s elapsed; host RSS≈1.0 GiB; host free RAM low (~2.0 GiB free, ~95% used) …")
    footer = lb.get_load_heartbeat_footer_text(max_age_s=30.0)
    assert "⚠" not in footer
    assert "host free RAM low" in footer
