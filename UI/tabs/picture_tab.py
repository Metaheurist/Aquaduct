from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from UI.help.tutorial_links import help_tooltip_rich
from UI.theme import token
from UI.widgets.tab_sections import section_title


def attach_picture_tab(win) -> None:
    """
    Photo-mode settings (parity with the Video tab): canvas template, output type,
    image count, and picture format (Poster/Newspaper/Comic). These choices are saved
    with your settings and used on the Pipeline tab when running in Photo mode.
    """
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setSpacing(12)
    lay.setContentsMargins(14, 12, 14, 14)

    header = QLabel("Picture settings")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)
    lay.addSpacing(4)

    hint = QLabel(
        "Photo mode generates still images and layouted designs (poster / newspaper / comic). "
        "These choices are saved with your settings and used on the Pipeline tab together with headline/topic mode there."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color: {token('muted', '#B7B7C2')};")
    lay.addWidget(hint)

    lay.addWidget(section_title("Canvas"))

    form = QFormLayout()
    form.setVerticalSpacing(10)
    form.setHorizontalSpacing(14)
    lay.addLayout(form)

    win.picture_template_combo = QComboBox()
    win.picture_template_combo.addItem("Vertical 9:16 - 1080×1920 (default)", ("vertical_1080", 1080, 1920))
    win.picture_template_combo.addItem("Vertical 9:16 - 720×1280", ("vertical_720", 720, 1280))
    win.picture_template_combo.addItem("Square 1:1 - 1080×1080", ("square_1080", 1080, 1080))
    win.picture_template_combo.addItem("Landscape 16:9 - 1920×1080", ("landscape_1080", 1920, 1080))
    win.picture_template_combo.setToolTip(
        help_tooltip_rich("Canvas size and aspect for photo-mode outputs.", "run", slide=2)
    )
    win.picture_template_combo.setAccessibleName("Picture canvas template")
    form.addRow("Template", win.picture_template_combo)

    lay.addWidget(section_title("Output"))

    out_form = QFormLayout()
    out_form.setVerticalSpacing(10)
    out_form.setHorizontalSpacing(14)
    lay.addLayout(out_form)

    win.picture_output_type_combo = QComboBox()
    win.picture_output_type_combo.addItem("Single final image (PNG)", "single_image")
    win.picture_output_type_combo.addItem("Image pack (N images)", "image_set")
    win.picture_output_type_combo.addItem("Layouted design (poster/newspaper/comic)", "layouted")
    win.picture_output_type_combo.setToolTip(
        help_tooltip_rich("Single image, image pack, or layouted design (poster / newspaper / comic).", "run", slide=2)
    )
    win.picture_output_type_combo.setAccessibleName("Picture output type")
    out_form.addRow("Output type", win.picture_output_type_combo)

    win.picture_count_spin = QSpinBox()
    win.picture_count_spin.setRange(1, 32)
    win.picture_count_spin.setValue(6)
    win.picture_count_spin.setToolTip(
        help_tooltip_rich(
            "Used for Image pack (and as a source pool for layouts).",
            "run",
            slide=2,
        )
    )
    win.picture_count_spin.setAccessibleName("Number of images to generate")
    out_form.addRow("Images to generate", win.picture_count_spin)

    win.picture_format_combo = QComboBox()
    win.picture_format_combo.addItem("Poster", "poster")
    win.picture_format_combo.addItem("Newspaper", "newspaper")
    win.picture_format_combo.addItem("Comic", "comic")
    win.picture_format_combo.setToolTip(
        help_tooltip_rich(
            "Visual style for layouted outputs. This is the same setting as the Pipeline tab's picture format - "
            "changing it in either place keeps both in sync.",
            "run",
            slide=2,
        )
    )
    win.picture_format_combo.setAccessibleName("Picture format (mirrors Pipeline tab)")
    out_form.addRow("Picture format", win.picture_format_combo)

    # Contextual hint that explains which control applies to the selected output type
    # (mirrors the contextual hints used on the Video tab).
    win.picture_output_hint = QLabel("")
    win.picture_output_hint.setWordWrap(True)
    win.picture_output_hint.setStyleSheet(f"color: {token('muted', '#8A8A96')}; font-size: 11px;")
    lay.addWidget(win.picture_output_hint)

    def _refresh_picture_output_hint() -> None:
        ot = str(win.picture_output_type_combo.currentData() or "single_image")
        is_pack = ot == "image_set"
        is_layout = ot == "layouted"
        win.picture_count_spin.setEnabled(is_pack or is_layout)
        win.picture_format_combo.setEnabled(is_layout)
        if is_layout:
            msg = "Layouted design: Picture format selects the poster / newspaper / comic style."
        elif is_pack:
            msg = "Image pack: 'Images to generate' sets how many images are produced."
        else:
            msg = "Single image: one final PNG is produced (image count and picture format are not used)."
        win.picture_output_hint.setText(msg)

    win.picture_output_type_combo.currentIndexChanged.connect(lambda _i: _refresh_picture_output_hint())
    win._refresh_picture_output_hint = _refresh_picture_output_hint
    _refresh_picture_output_hint()

    lay.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    win.tabs.addTab(scroll, "Picture")

