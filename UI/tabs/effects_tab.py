from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.settings.effects_presets import EFFECT_PRESETS, find_best_preset_for_effects, preset_by_id
from src.render.ffmpeg_slideshow import XFADE_TRANSITIONS
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSpinBox


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
    lay.addSpacing(2)

    preset_header = QLabel("Effects template")
    preset_header.setStyleSheet("font-size: 13px; font-weight: 600;")
    lay.addWidget(preset_header)

    _TILE_QSS = """
        QPushButton#effectsPresetTile {
            background-color: #1A1A22;
            border: 2px solid #2E2E38;
            border-radius: 8px;
            padding: 6px 8px;
            min-height: 44px;
            max-height: 64px;
            text-align: left;
            font-size: 10px;
            color: #E8E8EE;
        }
        QPushButton#effectsPresetTile:hover {
            border-color: #4A90D9;
            background-color: #22222C;
        }
        QPushButton#effectsPresetTile:checked {
            border-color: #25F4EE;
            background-color: #252532;
        }
        QPushButton#effectsPresetTile:pressed {
            background-color: #2A2A36;
        }
    """

    tile_wrap = QWidget()
    tile_grid = QGridLayout(tile_wrap)
    tile_grid.setHorizontalSpacing(8)
    tile_grid.setVerticalSpacing(8)
    tile_grid.setContentsMargins(0, 0, 0, 0)

    win._effects_preset_tile_group = QButtonGroup(win)
    win._effects_preset_tile_group.setExclusive(True)
    win._effects_preset_tile_buttons: dict[str, QPushButton] = {}

    cols = 4
    r, c = 0, 0
    for p in EFFECT_PRESETS:
        btn = QPushButton()
        btn.setObjectName("effectsPresetTile")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_TILE_QSS)
        btn.setText(f"{p.title}\n{p.subtitle}")
        btn.setToolTip(f"{p.title}\n\n{p.description}")
        btn.setProperty("preset_id", p.id)
        btn.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        win._effects_preset_tile_group.addButton(btn)
        win._effects_preset_tile_buttons[p.id] = btn
        tile_grid.addWidget(btn, r, c)
        c += 1
        if c >= cols:
            c = 0
            r += 1

    custom_tile = QPushButton()
    custom_tile.setObjectName("effectsPresetTile")
    custom_tile.setCheckable(True)
    custom_tile.setCursor(Qt.CursorShape.PointingHandCursor)
    custom_tile.setStyleSheet(_TILE_QSS)
    custom_tile.setText("Custom\nManual settings")
    custom_tile.setToolTip("Keep your own mix. Pick a template first, then tweak fields below.")
    custom_tile.setProperty("preset_id", "")
    custom_tile.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
    win._effects_preset_tile_group.addButton(custom_tile)
    win._effects_preset_custom_tile = custom_tile
    tile_grid.addWidget(custom_tile, r, c)
    for col in range(cols):
        tile_grid.setColumnStretch(col, 1)

    lay.addWidget(tile_wrap)

    preset_hint = QLabel(
        "Click a card to apply an effects profile (like graphics presets). "
        "Editing any value below switches selection to Custom."
    )
    preset_hint.setWordWrap(True)
    preset_hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(preset_hint)

    sub = QLabel("Visual & motion")
    sub.setStyleSheet("font-size: 13px; font-weight: 600; margin-top: 8px;")
    lay.addWidget(sub)

    hint = QLabel(
        "Motion between images, slideshow transitions, image seed, and mix options. "
        "Transition strength controls duration; type picks the FFmpeg xfade style."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(hint)

    form_vis = QFormLayout()
    form_vis.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form_vis.setVerticalSpacing(14)
    form_vis.setHorizontalSpacing(18)
    form_vis.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    win.quality_retries_spin = NoWheelSpinBox()
    win.quality_retries_spin.setRange(0, 5)
    win.quality_retries_spin.setValue(int(getattr(win.settings.video, "quality_retries", 2)))
    form_vis.addRow("Bad frame retries", win.quality_retries_spin)

    win.enable_motion_chk = QCheckBox("Enable motion + transitions (FFmpeg)")
    win.enable_motion_chk.setChecked(bool(getattr(win.settings.video, "enable_motion", True)))
    form_vis.addRow(win.enable_motion_chk)

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

    win.music_ducking_chk = QCheckBox("Music ducking under voice (FFmpeg)")
    win.music_ducking_chk.setChecked(bool(getattr(win.settings.video, "music_ducking", True)))
    form_audio.addRow(win.music_ducking_chk)

    win.ducking_spin = NoWheelSpinBox()
    win.ducking_spin.setRange(0, 100)
    win.ducking_spin.setValue(int(round(float(getattr(win.settings.video, "music_ducking_amount", 0.7)) * 100)))
    form_audio.addRow("Ducking intensity (%)", win.ducking_spin)

    win.music_fade_spin = NoWheelSpinBox()
    win.music_fade_spin.setRange(0, 6)
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

    lay.addLayout(form_audio)

    def _sync_audio_controls() -> None:
        enabled = str(win.audio_polish_combo.currentData() or "basic") != "off"
        win.music_ducking_chk.setEnabled(enabled)
        win.ducking_spin.setEnabled(enabled and bool(win.music_ducking_chk.isChecked()))
        win.music_fade_spin.setEnabled(enabled)
        win.sfx_combo.setEnabled(enabled)

    tip = QLabel("Tip: Set transition strength to Off to disable crossfades; motion zoom may still apply.")
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #B7B7C2; margin-top: 8px; font-size: 11px;")
    lay.addWidget(tip)

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
        if not hasattr(win, "_effects_preset_custom_tile"):
            return
        win._applying_effects_template = True
        try:
            win._effects_preset_custom_tile.setChecked(True)
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

    def _on_effects_tile_clicked(btn: QPushButton) -> None:
        if getattr(win, "_applying_effects_template", False):
            return
        raw = btn.property("preset_id")
        pid = "" if raw is None else str(raw)
        win._effects_preset_id = pid
        if pid:
            _apply_effects_preset(pid)

    win._apply_effects_preset = _apply_effects_preset
    win._mark_effects_template_custom = _mark_effects_custom
    win._effects_preset_id = ""

    win._effects_preset_tile_group.buttonClicked.connect(_on_effects_tile_clicked)

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
        if saved_fx and preset_by_id(saved_fx) and saved_fx in win._effects_preset_tile_buttons:
            win._effects_preset_tile_buttons[saved_fx].setChecked(True)
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
            if inferred and inferred in win._effects_preset_tile_buttons:
                win._effects_preset_tile_buttons[inferred].setChecked(True)
                win._effects_preset_id = inferred
            else:
                win._effects_preset_custom_tile.setChecked(True)
                win._effects_preset_id = ""
    finally:
        win._applying_effects_template = False

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
