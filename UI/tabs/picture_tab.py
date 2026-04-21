from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget


def attach_picture_tab(win) -> None:
    """
    Photo-mode settings scaffold.

    This tab will be expanded in later todos to include templates, output type, and picture formats
    (Poster/Newspaper/Comic).
    """
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setSpacing(12)
    lay.setContentsMargins(14, 12, 14, 14)

    header = QLabel("Picture settings")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    hint = QLabel(
        "Photo mode generates still images and layouted designs (poster / newspaper / comic). "
        "These choices are saved with your settings and used on Run together with headline/topic mode there."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(hint)

    form = QFormLayout()
    form.setVerticalSpacing(10)
    form.setHorizontalSpacing(14)
    lay.addLayout(form)

    win.picture_template_combo = QComboBox()
    win.picture_template_combo.addItem("Vertical 9:16 — 1080×1920 (default)", ("vertical_1080", 1080, 1920))
    win.picture_template_combo.addItem("Vertical 9:16 — 720×1280", ("vertical_720", 720, 1280))
    win.picture_template_combo.addItem("Square 1:1 — 1080×1080", ("square_1080", 1080, 1080))
    win.picture_template_combo.addItem("Landscape 16:9 — 1920×1080", ("landscape_1080", 1920, 1080))
    form.addRow("Template", win.picture_template_combo)

    win.picture_output_type_combo = QComboBox()
    win.picture_output_type_combo.addItem("Single final image (PNG)", "single_image")
    win.picture_output_type_combo.addItem("Image pack (N images)", "image_set")
    win.picture_output_type_combo.addItem("Layouted design (poster/newspaper/comic)", "layouted")
    form.addRow("Output type", win.picture_output_type_combo)

    win.picture_count_spin = QSpinBox()
    win.picture_count_spin.setRange(1, 32)
    win.picture_count_spin.setValue(6)
    win.picture_count_spin.setToolTip("Used for Image pack (and as a source pool for layouts).")
    form.addRow("Images to generate", win.picture_count_spin)

    win.picture_format_combo = QComboBox()
    win.picture_format_combo.addItem("Poster", "poster")
    win.picture_format_combo.addItem("Newspaper", "newspaper")
    win.picture_format_combo.addItem("Comic", "comic")
    form.addRow("Picture format", win.picture_format_combo)

    lay.addStretch(1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    win.tabs.addTab(scroll, "Picture")

