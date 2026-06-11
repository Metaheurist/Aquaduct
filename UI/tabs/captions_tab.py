from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QVBoxLayout, QWidget

from UI.widgets.basic_advanced import register_advanced_sections
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox
from UI.widgets.segmented_picker import SegmentOption, SegmentedPicker
from UI.widgets.tab_scaffold import make_tab_root
from UI.widgets.themed_switch import ThemedSwitch
from UI.widgets.visual_primitives import PreviewStrip


def attach_captions_tab(win) -> None:
    w = QWidget()
    root_lay = QVBoxLayout(w)
    root_lay.setContentsMargins(0, 0, 0, 0)

    inner_root, _, _, lay = make_tab_root(
        title="Captions",
        intro_text="Burn-in captions and overlays.",
        tab_id="captions",
        win=win,
        basic_advanced=True,
    )
    root_lay.addWidget(inner_root, 1)

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    win.captions_enabled_chk = ThemedSwitch("On-screen captions")
    win.captions_enabled_chk.setChecked(bool(getattr(win.settings.video, "captions_enabled", True)))
    form.addRow("", win.captions_enabled_chk)

    win.caption_highlight_combo = NoWheelComboBox()
    win.caption_highlight_combo.addItem("Subtle", "subtle")
    win.caption_highlight_combo.addItem("Strong", "strong")
    ch = str(getattr(win.settings.video, "caption_highlight_intensity", "strong") or "strong")
    idx = win.caption_highlight_combo.findData(ch)
    if idx >= 0:
        win.caption_highlight_combo.setCurrentIndex(idx)
    win.caption_highlight_combo.setVisible(False)

    win._caption_highlight_picker = SegmentedPicker(
        [
            SegmentOption("Subtle", "subtle", tooltip="Light emphasis on spoken words."),
            SegmentOption("Strong", "strong", tooltip="Bold karaoke-style highlight."),
        ],
        accessible_name="Caption highlight",
        default_index=0 if ch == "subtle" else 1,
    )
    form.addRow("Highlight", win._caption_highlight_picker)

    win._captions_preview = PreviewStrip(aspect="9:16", label="Caption preview")
    lay.addLayout(form)
    lay.addWidget(win._captions_preview)

    def _sync_highlight_from_picker() -> None:
        v = str(win._caption_highlight_picker.currentData() or "strong")
        ix = win.caption_highlight_combo.findData(v)
        if ix >= 0:
            win.caption_highlight_combo.setCurrentIndex(ix)

    def _sync_picker_from_combo() -> None:
        v = str(win.caption_highlight_combo.currentData() or "strong")
        ix = 0 if v == "subtle" else 1
        win._caption_highlight_picker.setCurrentIndex(ix)

    win._caption_highlight_picker.currentIndexChanged.connect(lambda _i: _sync_highlight_from_picker())
    win.caption_highlight_combo.currentIndexChanged.connect(lambda _i: _sync_picker_from_combo())

    win._captions_advanced_host = QWidget()
    adv_form = QFormLayout(win._captions_advanced_host)
    adv_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    win.caption_max_words_spin = NoWheelSpinBox()
    win.caption_max_words_spin.setRange(6, 10)
    win.caption_max_words_spin.setValue(int(getattr(win.settings.video, "caption_max_words", 8)))
    adv_form.addRow("Max words", win.caption_max_words_spin)

    win.caption_vertical_combo = NoWheelComboBox()
    win.caption_vertical_combo.addItem("Lower third", "bottom")
    win.caption_vertical_combo.addItem("Middle", "middle")
    win.caption_vertical_combo.addItem("Upper", "top")
    cv = str(getattr(win.settings.video, "caption_vertical_anchor", "bottom") or "bottom")
    cvi = win.caption_vertical_combo.findData(cv)
    if cvi >= 0:
        win.caption_vertical_combo.setCurrentIndex(cvi)
    adv_form.addRow("Position", win.caption_vertical_combo)

    win.facts_card_chk = ThemedSwitch("Key facts card")
    win.facts_card_chk.setChecked(bool(getattr(win.settings.video, "facts_card_enabled", True)))
    adv_form.addRow("", win.facts_card_chk)

    win.facts_card_pos_combo = NoWheelComboBox()
    win.facts_card_pos_combo.addItem("Top left", "top_left")
    win.facts_card_pos_combo.addItem("Top right", "top_right")
    fp = str(getattr(win.settings.video, "facts_card_position", "top_left") or "top_left")
    fpi = win.facts_card_pos_combo.findData(fp)
    if fpi >= 0:
        win.facts_card_pos_combo.setCurrentIndex(fpi)
    adv_form.addRow("Facts position", win.facts_card_pos_combo)

    win.facts_card_dur_combo = NoWheelComboBox()
    win.facts_card_dur_combo.addItem("Short (~30%)", "short")
    win.facts_card_dur_combo.addItem("Long (~60%)", "long")
    fd = str(getattr(win.settings.video, "facts_card_duration", "short") or "short")
    fdi = win.facts_card_dur_combo.findData(fd)
    if fdi >= 0:
        win.facts_card_dur_combo.setCurrentIndex(fdi)
    adv_form.addRow("Facts duration", win.facts_card_dur_combo)

    lay.addWidget(win._captions_advanced_host)
    register_advanced_sections(win, "captions", [win._captions_advanced_host])

    win.tabs.addTab(w, "Captions")
