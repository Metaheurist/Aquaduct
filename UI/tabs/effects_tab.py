from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.settings.effects_presets import EFFECT_PRESETS, find_best_preset_for_effects, preset_by_id
from src.render.ffmpeg_slideshow import XFADE_TRANSITIONS
from UI.help.tutorial_links import help_tooltip_rich
from UI.widgets.basic_advanced import attach_basic_advanced_header, register_advanced_sections
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox
from UI.widgets.tab_sections import section_title
from UI.widgets.themed_switch import ThemedSwitch
from UI.widgets.visual_primitives import PresetCard, PresetCardGrid

_EFFECT_PRESET_ICONS: dict[str, str] = {
    "effects_minimal": "minus",
    "effects_balanced": "layers",
    "effects_polished": "images",
    "effects_dynamic": "unhinged",
    "effects_cinematic": "landscape",
    "effects_voice_first": "explainer",
    "effects_music_forward": "layout",
    "": "more",
}


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
    content.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
    lay = QVBoxLayout(content)
    lay.setSpacing(10)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setAlignment(Qt.AlignmentFlag.AlignTop)

    hdr_row = QWidget()
    hdr_lay = QHBoxLayout(hdr_row)
    hdr_lay.setContentsMargins(0, 0, 0, 0)
    header = QLabel("Effects")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    attach_basic_advanced_header(win, "effects", title_row_parent_layout=hdr_lay, title_widget=header)
    lay.addWidget(hdr_row)

    lay.addWidget(section_title("Effects template", emphasis=True))

    _preset_cards: list[PresetCard] = []
    for p in EFFECT_PRESETS:
        _preset_cards.append(
            PresetCard(
                p.id,
                p.title,
                p.subtitle,
                icon=_EFFECT_PRESET_ICONS.get(p.id, "layers"),
                recommended=(p.id == "effects_balanced"),
            )
        )
    _preset_cards.append(PresetCard("", "Custom", "Manual settings", icon="more"))
    win._effects_preset_grid = PresetCardGrid(_preset_cards, columns=4, default_id="effects_balanced")
    win._effects_preset_grid.setSizePolicy(
        QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    )
    lay.addWidget(win._effects_preset_grid)

    preset_hint = QLabel("Tap a card for a preset. Switch to Advanced to tweak individual fields.")
    preset_hint.setWordWrap(True)
    preset_hint.setStyleSheet("color: #8A96A3; font-size: 11px;")
    lay.addWidget(preset_hint)

    win._effects_advanced_host = QWidget()
    win._effects_advanced_host.setSizePolicy(
        QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    )
    adv_outer = QVBoxLayout(win._effects_advanced_host)
    adv_outer.setContentsMargins(0, 8, 0, 0)
    adv_outer.setSpacing(10)
    lay.addWidget(win._effects_advanced_host, 0)

    adv_outer.addWidget(section_title("Visual & motion", emphasis=True))

    hint = QLabel("Motion, transitions, and audio mix.")
    hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    adv_outer.addWidget(hint)

    form_vis = QFormLayout()
    form_vis.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form_vis.setVerticalSpacing(14)
    form_vis.setHorizontalSpacing(18)
    form_vis.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    win.quality_retries_spin = NoWheelSpinBox()
    win.quality_retries_spin.setRange(0, 5)
    win.quality_retries_spin.setMaximumWidth(100)
    win.quality_retries_spin.setValue(int(getattr(win.settings.video, "quality_retries", 2)))
    form_vis.addRow("Bad frame retries", win.quality_retries_spin)

    win.enable_motion_chk = ThemedSwitch("Motion & transitions")
    win.enable_motion_chk.setChecked(bool(getattr(win.settings.video, "enable_motion", True)))
    form_vis.addRow("", win.enable_motion_chk)

    win.transition_combo = NoWheelComboBox()
    win.transition_combo.addItem("Off", "off")
    win.transition_combo.addItem("Low (recommended)", "low")
    win.transition_combo.addItem("Medium", "med")
    cur_ts = str(getattr(win.settings.video, "transition_strength", "low") or "low")
    tidx = win.transition_combo.findData(cur_ts)
    if tidx >= 0:
        win.transition_combo.setCurrentIndex(tidx)
    _prep_combo(win.transition_combo)
    form_vis.addRow("Transition strength", win.transition_combo)

    win.xfade_transition_combo = NoWheelComboBox()
    cur_xf = str(getattr(win.settings.video, "xfade_transition", "fade") or "fade")
    for name in XFADE_TRANSITIONS:
        win.xfade_transition_combo.addItem(_label_for_xfade(name), name)
    xf_idx = win.xfade_transition_combo.findData(cur_xf)
    if xf_idx >= 0:
        win.xfade_transition_combo.setCurrentIndex(xf_idx)
    _prep_combo(win.xfade_transition_combo)
    win.xfade_transition_combo.setToolTip(
        help_tooltip_rich(
            "FFmpeg xfade transition between slideshow images (when transition strength is not Off).",
            "video",
            slide=3,
        )
    )
    form_vis.addRow("Transition style", win.xfade_transition_combo)

    win.seed_base_input = QLineEdit()
    win.seed_base_input.setPlaceholderText("Blank = auto (random per run)")
    win.seed_base_input.setMaximumWidth(220)
    cur_seed = getattr(win.settings.video, "seed_base", None)
    win.seed_base_input.setText("" if cur_seed is None else str(cur_seed))
    form_vis.addRow("Image seed (optional)", win.seed_base_input)

    adv_outer.addLayout(form_vis)

    divider_audio = QFrame()
    divider_audio.setFrameShape(QFrame.Shape.HLine)
    divider_audio.setStyleSheet("color: #2A2A34; margin-top: 10px; margin-bottom: 6px;")
    adv_outer.addWidget(divider_audio)

    adv_outer.addWidget(section_title("Audio mix", emphasis=True))

    form_audio = QFormLayout()
    form_audio.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form_audio.setVerticalSpacing(14)
    form_audio.setHorizontalSpacing(18)
    form_audio.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    win.audio_polish_combo = NoWheelComboBox()
    win.audio_polish_combo.addItem("Off", "off")
    win.audio_polish_combo.addItem("Basic (recommended)", "basic")
    win.audio_polish_combo.addItem("Strong", "strong")
    cur_ap = str(getattr(win.settings.video, "audio_polish", "basic") or "basic")
    apidx = win.audio_polish_combo.findData(cur_ap)
    if apidx >= 0:
        win.audio_polish_combo.setCurrentIndex(apidx)
    _prep_combo(win.audio_polish_combo)
    form_audio.addRow("Audio polish", win.audio_polish_combo)

    win.music_ducking_chk = ThemedSwitch("Music ducking")
    win.music_ducking_chk.setChecked(bool(getattr(win.settings.video, "music_ducking", True)))
    form_audio.addRow("", win.music_ducking_chk)

    win.ducking_spin = NoWheelSpinBox()
    win.ducking_spin.setRange(0, 100)
    win.ducking_spin.setMaximumWidth(100)
    win.ducking_spin.setValue(int(round(float(getattr(win.settings.video, "music_ducking_amount", 0.7)) * 100)))
    form_audio.addRow("Ducking intensity (%)", win.ducking_spin)

    win.music_fade_spin = NoWheelSpinBox()
    win.music_fade_spin.setRange(0, 6)
    win.music_fade_spin.setMaximumWidth(100)
    win.music_fade_spin.setValue(int(round(float(getattr(win.settings.video, "music_fade_s", 1.2)))))
    form_audio.addRow("Music fade seconds", win.music_fade_spin)

    win.sfx_combo = NoWheelComboBox()
    win.sfx_combo.addItem("Off", "off")
    win.sfx_combo.addItem("Subtle (whoosh/click)", "subtle")
    cur_sfx = str(getattr(win.settings.video, "sfx_mode", "off") or "off")
    sfxidx = win.sfx_combo.findData(cur_sfx)
    if sfxidx >= 0:
        win.sfx_combo.setCurrentIndex(sfxidx)
    _prep_combo(win.sfx_combo)
    form_audio.addRow("SFX layer", win.sfx_combo)

    adv_outer.addLayout(form_audio)

    def _sync_audio_controls() -> None:
        enabled = str(win.audio_polish_combo.currentData() or "basic") != "off"
        win.music_ducking_chk.setEnabled(enabled)
        win.ducking_spin.setEnabled(enabled and bool(win.music_ducking_chk.isChecked()))
        win.music_fade_spin.setEnabled(enabled)
        win.sfx_combo.setEnabled(enabled)

    tip = QLabel("Off transitions = no crossfade.")
    tip.setStyleSheet("color: #B7B7C2; margin-top: 8px; font-size: 11px;")
    adv_outer.addWidget(tip)

    register_advanced_sections(win, "effects", [win._effects_advanced_host])

    win._applying_effects_template = False

    def _apply_effects_preset(preset_id: str) -> None:
        pr = preset_by_id(preset_id)
        if not pr:
            return
        win._applying_effects_template = True
        try:
            win.quality_retries_spin.setValue(int(pr.quality_retries))
            win.enable_motion_chk.setChecked(bool(pr.enable_motion))
            ts = str(pr.transition_strength)
            tix = win.transition_combo.findData(ts)
            if tix >= 0:
                win.transition_combo.setCurrentIndex(tix)
            xix = win.xfade_transition_combo.findData(str(pr.xfade_transition))
            if xix >= 0:
                win.xfade_transition_combo.setCurrentIndex(xix)
            if pr.seed_base is None:
                win.seed_base_input.setText("")
            else:
                win.seed_base_input.setText(str(int(pr.seed_base)))
            ap = str(pr.audio_polish)
            pix = win.audio_polish_combo.findData(ap)
            if pix >= 0:
                win.audio_polish_combo.setCurrentIndex(pix)
            win.music_ducking_chk.setChecked(bool(pr.music_ducking))
            win.ducking_spin.setValue(int(round(float(pr.music_ducking_amount) * 100)))
            win.music_fade_spin.setValue(int(round(float(pr.music_fade_s))))
            sx = str(pr.sfx_mode)
            six = win.sfx_combo.findData(sx)
            if six >= 0:
                win.sfx_combo.setCurrentIndex(six)
            _sync_audio_controls()
        finally:
            win._applying_effects_template = False

    def _mark_effects_custom() -> None:
        if getattr(win, "_applying_effects_template", False):
            return
        if not hasattr(win, "_effects_preset_grid"):
            return
        win._applying_effects_template = True
        try:
            cix = win._effects_preset_grid.findData("")
            if cix >= 0:
                win._effects_preset_grid.setCurrentIndex(cix)
            win._effects_preset_id = ""
        finally:
            win._applying_effects_template = False

    def _on_audio_polish_changed() -> None:
        _sync_audio_controls()
        _mark_effects_custom()

    def _on_music_ducking_changed() -> None:
        _sync_audio_controls()
        _mark_effects_custom()

    win.audio_polish_combo.currentIndexChanged.connect(_on_audio_polish_changed)
    win.music_ducking_chk.stateChanged.connect(_on_music_ducking_changed)
    _sync_audio_controls()

    def _on_effects_preset_changed(_index: int) -> None:
        if getattr(win, "_applying_effects_template", False):
            return
        pid = str(win._effects_preset_grid.currentData() or "")
        win._effects_preset_id = pid
        if pid:
            _apply_effects_preset(pid)

    win._apply_effects_preset = _apply_effects_preset
    win._mark_effects_template_custom = _mark_effects_custom
    win._effects_preset_id = ""

    win._effects_preset_grid.currentIndexChanged.connect(_on_effects_preset_changed)

    win.quality_retries_spin.valueChanged.connect(lambda *_: _mark_effects_custom())
    win.enable_motion_chk.stateChanged.connect(lambda *_: _mark_effects_custom())
    win.transition_combo.currentIndexChanged.connect(lambda *_: _mark_effects_custom())
    win.xfade_transition_combo.currentIndexChanged.connect(lambda *_: _mark_effects_custom())
    win.seed_base_input.textChanged.connect(lambda *_: _mark_effects_custom())
    win.audio_polish_combo.currentIndexChanged.connect(lambda *_: _mark_effects_custom())
    win.music_ducking_chk.stateChanged.connect(lambda *_: _mark_effects_custom())
    win.ducking_spin.valueChanged.connect(lambda *_: _mark_effects_custom())
    win.music_fade_spin.valueChanged.connect(lambda *_: _mark_effects_custom())
    win.sfx_combo.currentIndexChanged.connect(lambda *_: _mark_effects_custom())

    v = win.settings.video
    saved_fx = str(getattr(v, "effects_preset_id", "") or "").strip()
    win._applying_effects_template = True
    try:
        if saved_fx and preset_by_id(saved_fx) and win._effects_preset_grid.findData(saved_fx) >= 0:
            win._effects_preset_grid.setCurrentData(saved_fx)
            win._effects_preset_id = saved_fx
        else:
            inferred = find_best_preset_for_effects(
                quality_retries=int(getattr(v, "quality_retries", 2)),
                enable_motion=bool(getattr(v, "enable_motion", True)),
                transition_strength=str(getattr(v, "transition_strength", "low") or "low"),
                xfade_transition=str(getattr(v, "xfade_transition", "fade") or "fade"),
                seed_base=getattr(v, "seed_base", None),
                audio_polish=str(getattr(v, "audio_polish", "basic") or "basic"),
                music_ducking=bool(getattr(v, "music_ducking", True)),
                music_ducking_amount=float(getattr(v, "music_ducking_amount", 0.7)),
                music_fade_s=float(getattr(v, "music_fade_s", 1.2)),
                sfx_mode=str(getattr(v, "sfx_mode", "off") or "off"),
            )
            if inferred and win._effects_preset_grid.findData(inferred) >= 0:
                win._effects_preset_grid.setCurrentData(inferred)
                win._effects_preset_id = inferred
            else:
                cix = win._effects_preset_grid.findData("")
                if cix >= 0:
                    win._effects_preset_grid.setCurrentIndex(cix)
                win._effects_preset_id = ""
    finally:
        win._applying_effects_template = False

    hint_sz = lay.sizeHint()
    content.setMinimumWidth(max(hint_sz.width(), 480))

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
    scroll.setWidget(content)
    win._effects_scroll = scroll
    win._effects_content = content

    shell = QWidget()
    shell.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
    shell_lay = QVBoxLayout(shell)
    shell_lay.setContentsMargins(0, 0, 0, 0)
    shell_lay.setSpacing(0)
    shell_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
    shell_lay.addWidget(scroll, 0)

    win.tabs.addTab(shell, "Effects")
