"""Tests for visual Basic-mode primitives."""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_quantity_stepper_exposes_harvest_spin(qtbot):
    from UI.widgets.visual_primitives import QuantityStepper

    stepper = QuantityStepper(minimum=1, maximum=10, value=3)
    qtbot.addWidget(stepper)
    spin = stepper.spin()
    assert spin.value() == 3
    stepper.setValue(7)
    assert spin.value() == 7


@pytest.mark.qt
def test_preset_card_grid_current_data(qtbot):
    from UI.widgets.visual_primitives import PresetCard, PresetCardGrid

    grid = PresetCardGrid(
        [PresetCard("a", "Alpha"), PresetCard("b", "Beta")],
        default_id="b",
    )
    qtbot.addWidget(grid)
    assert grid.currentData() == "b"
    grid.setCurrentData("a")
    assert grid.currentData() == "a"


@pytest.mark.qt
def test_swatch_grid_syncs_index(qtbot):
    from UI.widgets.visual_primitives import SwatchGrid, SwatchOption

    grid = SwatchGrid(
        [
            SwatchOption("default", "Default", "#25F4EE"),
            SwatchOption("ocean", "Ocean", "#4A90D9"),
        ],
        default_id="default",
    )
    qtbot.addWidget(grid)
    grid.setCurrentData("ocean")
    assert grid.currentData() == "ocean"


@pytest.mark.qt
def test_tile_svg_icons_render(qapplication):
    from UI.widgets.tile_svg_icons import TileIconKind, pixmap_tile, qicon_tile

    kinds: list[TileIconKind] = [
        "news",
        "cartoon",
        "poster",
        "phone_vertical",
        "star",
        "minus",
        "plus",
        "more",
    ]
    for kind in kinds:
        pm = pixmap_tile(kind, "#25F4EE", size=24)
        assert not pm.isNull(), kind
        icon = qicon_tile(kind, "#25F4EE", 20)
        assert not icon.isNull(), kind


@pytest.mark.qt
def test_option_tiles_use_svg_cards(qtbot):
    from UI.widgets.option_tiles import OptionTiles, TileOption

    tiles = OptionTiles(
        [TileOption("News", "news", icon="news", subtitle="Headlines")],
        columns=1,
    )
    qtbot.addWidget(tiles)
    assert tiles.currentData() == "news"


@pytest.mark.qt
def test_step_card_adds_children(qtbot):
    from PyQt6.QtWidgets import QLabel

    from UI.widgets.visual_primitives import StepCard

    card = StepCard(1, "Test step", subtitle="Hint")
    lbl = QLabel("body")
    card.addWidget(lbl)
    qtbot.addWidget(card)
    assert len(card.findChildren(QLabel)) >= 2
