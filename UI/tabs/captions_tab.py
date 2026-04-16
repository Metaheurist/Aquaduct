from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def attach_captions_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Captions & on-screen graphics")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    win.captions_enabled_chk = QCheckBox("Show on-screen captions (word highlights)")
    win.captions_enabled_chk.setChecked(bool(getattr(win.settings.video, "captions_enabled", True)))
    form.addRow("", win.captions_enabled_chk)

    win.caption_highlight_combo = QComboBox()
    win.caption_highlight_combo.addItem("Subtle highlight", "subtle")
    win.caption_highlight_combo.addItem("Strong highlight", "strong")
    ch = str(getattr(win.settings.video, "caption_highlight_intensity", "strong") or "strong")
    idx = win.caption_highlight_combo.findData(ch)
    if idx >= 0:
        win.caption_highlight_combo.setCurrentIndex(idx)
    form.addRow("Caption highlight", win.caption_highlight_combo)

    win.caption_max_words_spin = QSpinBox()
    win.caption_max_words_spin.setRange(6, 10)
    win.caption_max_words_spin.setValue(int(getattr(win.settings.video, "caption_max_words", 8)))
    form.addRow("Max words on screen", win.caption_max_words_spin)

    win.facts_card_chk = QCheckBox("Show Key facts card (from article text when available)")
    win.facts_card_chk.setChecked(bool(getattr(win.settings.video, "facts_card_enabled", True)))
    form.addRow("", win.facts_card_chk)

    win.facts_card_pos_combo = QComboBox()
    win.facts_card_pos_combo.addItem("Top left", "top_left")
    win.facts_card_pos_combo.addItem("Top right", "top_right")
    fp = str(getattr(win.settings.video, "facts_card_position", "top_left") or "top_left")
    fpi = win.facts_card_pos_combo.findData(fp)
    if fpi >= 0:
        win.facts_card_pos_combo.setCurrentIndex(fpi)
    form.addRow("Facts card position", win.facts_card_pos_combo)

    win.facts_card_dur_combo = QComboBox()
    win.facts_card_dur_combo.addItem("Short (first ~30% of video)", "short")
    win.facts_card_dur_combo.addItem("Long (first ~60% of video)", "long")
    fd = str(getattr(win.settings.video, "facts_card_duration", "short") or "short")
    fdi = win.facts_card_dur_combo.findData(fd)
    if fdi >= 0:
        win.facts_card_dur_combo.setCurrentIndex(fdi)
    form.addRow("Facts card duration", win.facts_card_dur_combo)

    lay.addLayout(form)

    tip = QLabel(
        "Branding palette accents can affect caption highlights; see the Branding tab for theme overrides."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(tip)

    win.tabs.addTab(w, "Captions")
