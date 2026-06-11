from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from UI.help.tutorial_links import help_tooltip_rich
from UI.theme import token
from UI.widgets.basic_advanced import register_advanced_sections
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox
from UI.widgets.option_tiles import OptionTiles, TileOption
from UI.widgets.tab_scaffold import make_tab_root
from UI.widgets.visual_primitives import PresetCard, PresetCardGrid, QuantityStepper, StepCard


def attach_picture_tab(win) -> None:
    """Photo-mode settings with visual Basic controls and harvest-compatible hidden shims."""
    w = QWidget()
    root_lay = QVBoxLayout(w)
    root_lay.setContentsMargins(0, 0, 0, 0)

    inner_root, _, _, il = make_tab_root(
        title="Picture",
        intro_text="Canvas, output type, and layout for photo runs.",
        tab_id="picture",
        win=win,
        basic_advanced=True,
    )

    # Hidden harvest shims (main_window._apply_picture_settings_to_ui reads these).
    win.picture_template_combo = NoWheelComboBox()
    win.picture_template_combo.addItem("Vertical 9:16 - 1080×1920 (default)", ("vertical_1080", 1080, 1920))
    win.picture_template_combo.addItem("Vertical 9:16 - 720×1280", ("vertical_720", 720, 1280))
    win.picture_template_combo.addItem("Square 1:1 - 1080×1080", ("square_1080", 1080, 1080))
    win.picture_template_combo.addItem("Landscape 16:9 - 1920×1080", ("landscape_1080", 1920, 1080))
    win.picture_template_combo.setVisible(False)

    win.picture_output_type_combo = NoWheelComboBox()
    win.picture_output_type_combo.addItem("Single final image (PNG)", "single_image")
    win.picture_output_type_combo.addItem("Image pack (N images)", "image_set")
    win.picture_output_type_combo.addItem("Layouted design (poster/newspaper/comic)", "layouted")
    win.picture_output_type_combo.setVisible(False)

    win.picture_count_spin = NoWheelSpinBox()
    win.picture_count_spin.setRange(1, 32)
    win.picture_count_spin.setValue(6)
    win.picture_count_spin.setVisible(False)

    win.picture_format_combo = NoWheelComboBox()
    win.picture_format_combo.addItem("Poster", "poster")
    win.picture_format_combo.addItem("Newspaper", "newspaper")
    win.picture_format_combo.addItem("Comic", "comic")
    win.picture_format_combo.setVisible(False)

    step_canvas = StepCard(1, "Canvas", subtitle="Aspect ratio and resolution")
    _canvas_cards = [
        PresetCard("vertical_1080", "Vertical", "1080×1920", icon="phone_vertical", recommended=True),
        PresetCard("vertical_720", "Vertical HD", "720×1280", icon="phone_vertical"),
        PresetCard("square_1080", "Square", "1080×1080", icon="square"),
        PresetCard("landscape_1080", "Landscape", "1920×1080", icon="landscape"),
    ]
    win._picture_canvas_picker = PresetCardGrid(_canvas_cards, columns=2, default_id="vertical_1080")
    step_canvas.addWidget(win._picture_canvas_picker)
    il.addWidget(step_canvas)

    step_out = StepCard(2, "Output", subtitle="Single image, pack, or layout")
    _out_cards = [
        PresetCard("single_image", "Single", "One PNG", icon="image"),
        PresetCard("image_set", "Pack", "N images", icon="images"),
        PresetCard("layouted", "Layout", "Poster / paper / comic", icon="layout"),
    ]
    win._picture_output_picker = PresetCardGrid(_out_cards, columns=3, default_id="single_image")
    step_out.addWidget(win._picture_output_picker)

    win._picture_count_stepper = QuantityStepper(minimum=1, maximum=32, value=6, presets=(3, 6, 12))
    step_out.addWidget(win._picture_count_stepper)

    _pf_tiles = [
        TileOption("Poster", "poster", icon="poster", subtitle="Bold"),
        TileOption("Newspaper", "newspaper", icon="newspaper", subtitle="Editorial"),
        TileOption("Comic", "comic", icon="comic", subtitle="Panels"),
    ]
    win._picture_format_tiles = OptionTiles(_pf_tiles, columns=3, default_index=0)
    step_out.addWidget(win._picture_format_tiles)
    il.addWidget(step_out)

    win.picture_output_hint = QWidget()
    hint_lay = QVBoxLayout(win.picture_output_hint)
    hint_lay.setContentsMargins(0, 0, 0, 0)
    win._picture_output_hint_lbl = QLabel("")
    win._picture_output_hint_lbl.setWordWrap(True)
    win._picture_output_hint_lbl.setStyleSheet(f"color: {token('muted', '#8A8A96')}; font-size: 11px;")
    hint_lay.addWidget(win._picture_output_hint_lbl)
    il.addWidget(win.picture_output_hint)

    win._picture_advanced_host = QWidget()
    adv_lay = QVBoxLayout(win._picture_advanced_host)
    adv_lay.setContentsMargins(0, 0, 0, 0)
    adv_form = QFormLayout()
    adv_form.addRow("Template (combo)", win.picture_template_combo)
    adv_form.addRow("Output type (combo)", win.picture_output_type_combo)
    adv_form.addRow("Count (spin)", win.picture_count_spin)
    adv_form.addRow("Format (combo)", win.picture_format_combo)
    adv_lay.addLayout(adv_form)
    il.addWidget(win._picture_advanced_host)
    register_advanced_sections(win, "picture", [win._picture_advanced_host])

    def _sync_template_from_cards() -> None:
        tid = str(win._picture_canvas_picker.currentData() or "vertical_1080")
        for i in range(win.picture_template_combo.count()):
            d = win.picture_template_combo.itemData(i)
            if isinstance(d, tuple) and str(d[0]) == tid:
                win.picture_template_combo.setCurrentIndex(i)
                break

    def _sync_template_to_cards() -> None:
        d = win.picture_template_combo.currentData()
        if isinstance(d, tuple) and d:
            win._picture_canvas_picker.setCurrentData(str(d[0]))

    def _sync_output_from_cards() -> None:
        ot = str(win._picture_output_picker.currentData() or "single_image")
        ix = win.picture_output_type_combo.findData(ot)
        if ix >= 0:
            win.picture_output_type_combo.setCurrentIndex(ix)

    def _sync_output_to_cards() -> None:
        ot = str(win.picture_output_type_combo.currentData() or "single_image")
        win._picture_output_picker.setCurrentData(ot)

    def _sync_count_from_stepper() -> None:
        win.picture_count_spin.setValue(win._picture_count_stepper.value())

    def _sync_count_to_stepper() -> None:
        win._picture_count_stepper.setValue(int(win.picture_count_spin.value()))

    def _sync_format_from_tiles() -> None:
        pf = str(win._picture_format_tiles.currentData() or "poster")
        ix = win.picture_format_combo.findData(pf)
        if ix >= 0:
            win.picture_format_combo.setCurrentIndex(ix)

    def _sync_format_to_tiles() -> None:
        pf = str(win.picture_format_combo.currentData() or "poster")
        ix = win._picture_format_tiles.findData(pf)
        if ix >= 0:
            win._picture_format_tiles.setCurrentIndex(ix)

    def _refresh_picture_output_hint() -> None:
        ot = str(win.picture_output_type_combo.currentData() or "single_image")
        is_pack = ot == "image_set"
        is_layout = ot == "layouted"
        win._picture_count_stepper.setEnabled(is_pack or is_layout)
        win._picture_format_tiles.setEnabled(is_layout)
        if is_layout:
            msg = "Layouted design: pick poster, newspaper, or comic."
        elif is_pack:
            msg = "Image pack: stepper sets how many images are produced."
        else:
            msg = "Single image: one final PNG (count and layout style are not used)."
        win._picture_output_hint_lbl.setText(msg)

    win._picture_canvas_picker.currentIndexChanged.connect(lambda _i: (_sync_template_from_cards(),))
    win.picture_template_combo.currentIndexChanged.connect(lambda _i: (_sync_template_to_cards(),))
    win._picture_output_picker.currentIndexChanged.connect(
        lambda _i: (_sync_output_from_cards(), _refresh_picture_output_hint())
    )
    win.picture_output_type_combo.currentIndexChanged.connect(
        lambda _i: (_sync_output_to_cards(), _refresh_picture_output_hint())
    )
    win._picture_count_stepper.valueChanged.connect(lambda _v: _sync_count_from_stepper())
    win.picture_count_spin.valueChanged.connect(lambda _v: _sync_count_to_stepper())
    win._picture_format_tiles.currentIndexChanged.connect(lambda _i: _sync_format_from_tiles())
    win.picture_format_combo.currentIndexChanged.connect(lambda _i: _sync_format_to_tiles())

    win._refresh_picture_output_hint = _refresh_picture_output_hint
    _sync_template_to_cards()
    _sync_output_to_cards()
    _sync_count_to_stepper()
    _sync_format_to_tiles()
    _refresh_picture_output_hint()

    il.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(inner_root)
    root_lay.addWidget(scroll, 1)
    win.tabs.addTab(w, "Picture")
