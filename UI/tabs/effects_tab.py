from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.ffmpeg_slideshow import XFADE_TRANSITIONS


def _prep_combo(combo: QComboBox, *, min_w: int = 260, max_w: int = 520, pop_min: int = 400) -> None:
    combo.setSizePolicy(QSizePolicy.Policy.Preferred, combo.sizePolicy().verticalPolicy())
    combo.setMinimumWidth(min_w)
    combo.setMaximumWidth(max_w)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
    combo.view().setMinimumWidth(pop_min)


def _label_for_xfade(name: str) -> str:
    pretty = {
        "fade": "Fade",
        "dissolve": "Dissolve",
        "wipeleft": "Wipe left",
        "wiperight": "Wipe right",
        "wipeup": "Wipe up",
        "wipedown": "Wipe down",
        "slideleft": "Slide left",
        "slideright": "Slide right",
        "slideup": "Slide up",
        "slidedown": "Slide down",
        "radial": "Radial",
        "smoothleft": "Smooth left",
        "smoothright": "Smooth right",
        "circlecrop": "Circle crop",
        "vertopen": "Vertical open",
        "horzopen": "Horizontal open",
        "diagtl": "Diagonal TL",
        "diagtr": "Diagonal TR",
        "hlslice": "Horizontal slice L",
        "hrslice": "Horizontal slice R",
    }
    return pretty.get(name, name)


def attach_effects_tab(win) -> None:
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setSpacing(12)
    lay.setContentsMargins(14, 12, 14, 14)

    header = QLabel("Effects & audio")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)
    hint = QLabel(
        "Motion between images, slideshow transitions, image seed, and mix options. "
        "Transition strength controls duration; type picks the FFmpeg xfade style."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(hint)
    lay.addSpacing(4)

    form_vis = QFormLayout()
    form_vis.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form_vis.setVerticalSpacing(14)
    form_vis.setHorizontalSpacing(18)
    form_vis.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    win.quality_retries_spin = QSpinBox()
    win.quality_retries_spin.setRange(0, 5)
    win.quality_retries_spin.setValue(int(getattr(win.settings.video, "quality_retries", 2)))
    form_vis.addRow("Bad frame retries", win.quality_retries_spin)

    win.enable_motion_chk = QCheckBox("Enable motion + transitions (FFmpeg)")
    win.enable_motion_chk.setChecked(bool(getattr(win.settings.video, "enable_motion", True)))
    form_vis.addRow(win.enable_motion_chk)

    win.transition_combo = QComboBox()
    win.transition_combo.addItem("Off", "off")
    win.transition_combo.addItem("Low (recommended)", "low")
    win.transition_combo.addItem("Medium", "med")
    cur_ts = str(getattr(win.settings.video, "transition_strength", "low") or "low")
    tidx = win.transition_combo.findData(cur_ts)
    if tidx >= 0:
        win.transition_combo.setCurrentIndex(tidx)
    _prep_combo(win.transition_combo)
    form_vis.addRow("Transition strength", win.transition_combo)

    win.xfade_transition_combo = QComboBox()
    cur_xf = str(getattr(win.settings.video, "xfade_transition", "fade") or "fade")
    for name in XFADE_TRANSITIONS:
        win.xfade_transition_combo.addItem(_label_for_xfade(name), name)
    xf_idx = win.xfade_transition_combo.findData(cur_xf)
    if xf_idx >= 0:
        win.xfade_transition_combo.setCurrentIndex(xf_idx)
    _prep_combo(win.xfade_transition_combo)
    win.xfade_transition_combo.setToolTip("FFmpeg xfade transition between slideshow images (when strength is not Off).")
    form_vis.addRow("Transition style", win.xfade_transition_combo)

    win.seed_base_input = QLineEdit()
    win.seed_base_input.setPlaceholderText("Blank = auto (random per run)")
    cur_seed = getattr(win.settings.video, "seed_base", None)
    win.seed_base_input.setText("" if cur_seed is None else str(cur_seed))
    form_vis.addRow("Image seed (optional)", win.seed_base_input)

    lay.addLayout(form_vis)

    divider_audio = QFrame()
    divider_audio.setFrameShape(QFrame.Shape.HLine)
    divider_audio.setStyleSheet("color: #2A2A34; margin-top: 10px; margin-bottom: 6px;")
    lay.addWidget(divider_audio)

    ah2 = QLabel("Audio mix")
    ah2.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 4px;")
    lay.addWidget(ah2)

    form_audio = QFormLayout()
    form_audio.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form_audio.setVerticalSpacing(14)
    form_audio.setHorizontalSpacing(18)
    form_audio.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    win.audio_polish_combo = QComboBox()
    win.audio_polish_combo.addItem("Off", "off")
    win.audio_polish_combo.addItem("Basic (recommended)", "basic")
    win.audio_polish_combo.addItem("Strong", "strong")
    cur_ap = str(getattr(win.settings.video, "audio_polish", "basic") or "basic")
    apidx = win.audio_polish_combo.findData(cur_ap)
    if apidx >= 0:
        win.audio_polish_combo.setCurrentIndex(apidx)
    _prep_combo(win.audio_polish_combo)
    form_audio.addRow("Audio polish", win.audio_polish_combo)

    win.music_ducking_chk = QCheckBox("Music ducking under voice (FFmpeg)")
    win.music_ducking_chk.setChecked(bool(getattr(win.settings.video, "music_ducking", True)))
    form_audio.addRow(win.music_ducking_chk)

    win.ducking_spin = QSpinBox()
    win.ducking_spin.setRange(0, 100)
    win.ducking_spin.setValue(int(round(float(getattr(win.settings.video, "music_ducking_amount", 0.7)) * 100)))
    form_audio.addRow("Ducking intensity (%)", win.ducking_spin)

    win.music_fade_spin = QSpinBox()
    win.music_fade_spin.setRange(0, 6)
    win.music_fade_spin.setValue(int(round(float(getattr(win.settings.video, "music_fade_s", 1.2)))))
    form_audio.addRow("Music fade seconds", win.music_fade_spin)

    win.sfx_combo = QComboBox()
    win.sfx_combo.addItem("Off", "off")
    win.sfx_combo.addItem("Subtle (whoosh/click)", "subtle")
    cur_sfx = str(getattr(win.settings.video, "sfx_mode", "off") or "off")
    sfxidx = win.sfx_combo.findData(cur_sfx)
    if sfxidx >= 0:
        win.sfx_combo.setCurrentIndex(sfxidx)
    _prep_combo(win.sfx_combo)
    form_audio.addRow("SFX layer", win.sfx_combo)

    lay.addLayout(form_audio)

    def _sync_audio_controls() -> None:
        enabled = str(win.audio_polish_combo.currentData() or "basic") != "off"
        win.music_ducking_chk.setEnabled(enabled)
        win.ducking_spin.setEnabled(enabled and bool(win.music_ducking_chk.isChecked()))
        win.music_fade_spin.setEnabled(enabled)
        win.sfx_combo.setEnabled(enabled)

    win.audio_polish_combo.currentIndexChanged.connect(_sync_audio_controls)
    win.music_ducking_chk.stateChanged.connect(_sync_audio_controls)
    _sync_audio_controls()

    tip = QLabel("Tip: Set transition strength to Off to disable crossfades; motion zoom may still apply.")
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #B7B7C2; margin-top: 8px; font-size: 11px;")
    lay.addWidget(tip)

    hint_sz = lay.sizeHint()
    content.setMinimumHeight(max(hint_sz.height(), 360))
    content.setMinimumWidth(max(hint_sz.width(), 520))

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setMinimumHeight(480)
    scroll.setWidget(content)

    shell = QWidget()
    shell_lay = QVBoxLayout(shell)
    shell_lay.setContentsMargins(0, 0, 0, 0)
    shell_lay.setSpacing(0)
    shell_lay.addWidget(scroll)

    win.tabs.addTab(shell, "Effects")
