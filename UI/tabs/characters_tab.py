from __future__ import annotations

import shutil
from dataclasses import replace

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.content.character_presets import (
    GeneratedCharacterFields,
    character_auto_presets_for_ui,
    get_character_auto_preset_by_id,
    CHARACTER_AGE_RANGE_OPTIONS,
    CHARACTER_ETHNICITY_OPTIONS,
    CHARACTER_GENDER_OPTIONS,
    CHARACTER_VOICE_INSTRUCTION_OPTIONS,
)
from src.content.characters_store import (
    Character,
    character_portrait_abs_path,
    character_portrait_relpath,
    character_reference_image_resolved,
    delete_by_id,
    delete_character_assets,
    get_by_id,
    load_all,
    new_character,
    save_all,
    subject_token_phrase,
    upsert,
)
from src.runtime.model_backend import api_role_ready, is_api_mode
from src.content.topics import normalize_video_format
from src.speech.elevenlabs_tts import effective_elevenlabs_api_key, elevenlabs_available_for_app
from src.settings.ui_settings import save_settings
from src.speech.voice import list_pyttsx3_voices as list_sys_voices
from UI.widgets.basic_advanced import attach_basic_advanced_header, register_advanced_sections
from UI.widgets.themed_switch import ThemedSwitch
from UI.services.brain_expand import image_model_id_from_ui, resolve_llm_model_id
from UI.dialogs.frameless_dialog import FramelessDialog, aquaduct_question, aquaduct_warning
from UI.dialogs.auxiliary_progress_dialog import AuxiliaryProgressDialog, schedule_auxiliary_job_memory_purge
from UI.widgets.no_wheel_controls import NoWheelComboBox
from UI.widgets.tab_sections import add_section_spacing, section_card, section_title
from UI.widgets.visual_primitives import StepCard
from UI.help.tutorial_links import help_tooltip_rich
from UI.theme import resolve_palette, token
from UI.widgets.character_card import CharacterCard
from UI.widgets.tab_layout import TAB_PAGE_MARGINS, TAB_PAGE_SPACING
from UI.widgets.two_column import two_column_row
from UI.widgets.toolbar_svg_icons import qicon_toolbar
from UI.workers import CharacterGenerateWorker, CharacterPortraitWorker


def _fill_fixed_combo(combo: QComboBox, options: list[tuple[str, str]], current_value: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    cur = (current_value or "").strip()
    for label, value in options:
        combo.addItem(label, value)
    if cur and combo.findData(cur) < 0:
        combo.addItem(f"[custom] {cur[:48]}", cur)
    idx = combo.findData(cur) if cur else 0
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


class _PortraitThumbLabel(QLabel):
    """Small preview; click opens enlarged view when a pixmap is set."""

    portraitClicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            pm = self.pixmap()
            if pm is not None and not pm.isNull():
                self.portraitClicked.emit()
                return
        super().mousePressEvent(event)


class _FitPixmapLabel(QLabel):
    """Keeps aspect ratio while filling the label as the dialog resizes / maximizes."""

    def __init__(self, original: QPixmap) -> None:
        super().__init__()
        self._orig = original
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #14141A;")

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        QTimer.singleShot(0, self._sync)

    def _sync(self) -> None:
        if self._orig.isNull():
            return
        w = max(1, int(self.width()) - 16)
        h = max(1, int(self.height()) - 16)
        self.setPixmap(
            self._orig.scaled(
                w,
                h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class _ElevenLabsVoicesThread(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key

    def run(self) -> None:
        try:
            from src.speech.elevenlabs_tts import list_voices

            self.finished_ok.emit(list_voices(self._api_key))
        except Exception as e:
            self.failed.emit(str(e))


def _fill_voice_combo(combo: QComboBox, current_id: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("(Engine default)", "")
    for label, vid in list_sys_voices():
        combo.addItem(label[:80], vid)
    idx = combo.findData(current_id)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def _fill_el_voice_combo(combo: QComboBox, current_voice_id: str, voices: list[tuple[str, str]]) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("(None)", "")
    cid = (current_voice_id or "").strip()
    for label, vid in voices:
        combo.addItem(label[:120], vid)
    if cid and combo.findData(cid) < 0:
        combo.addItem(f"[id] {cid[:32]}", cid)
    idx = combo.findData(cid) if cid else 0
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def attach_characters_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(*TAB_PAGE_MARGINS)
    lay.setSpacing(TAB_PAGE_SPACING)

    left_panel = QWidget()
    left_lay = QVBoxLayout(left_panel)
    left_lay.setContentsMargins(0, 0, 4, 0)
    left_lay.setSpacing(3)

    list_card, list_lay = section_card(margins=10, spacing=8)
    hdr_row = QWidget()
    hdr_lay = QHBoxLayout(hdr_row)
    hdr_lay.setContentsMargins(0, 0, 0, 0)
    char_hdr = section_title("Characters", emphasis=True)
    attach_basic_advanced_header(win, "characters", title_row_parent_layout=hdr_lay, title_widget=char_hdr)
    list_lay.addWidget(hdr_row)

    hero = StepCard(1, "Create a host", subtitle="Lead voice + portrait — assign on Pipeline")
    hint = QLabel("Tap + or Generate with LLM to add your first character.")
    hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    hero.addWidget(hint)
    list_lay.addWidget(hero)

    gen_row = QHBoxLayout()
    gen_row.setSpacing(6)
    gen_lbl = QLabel("Preset")
    gen_lbl.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    gen_lbl.setMinimumWidth(44)
    gen_row.addWidget(gen_lbl)
    win.character_preset_combo = NoWheelComboBox()
    win.character_preset_combo.setMinimumWidth(160)
    win.character_preset_combo.setMaximumHeight(26)

    def _current_vf_for_char_presets() -> str:
        if hasattr(win, "video_format_combo"):
            return str(win.video_format_combo.currentData() or getattr(win.settings, "video_format", "news") or "news")
        return str(getattr(win.settings, "video_format", "news") or "news")

    def _refresh_character_preset_combo() -> None:
        cur = str(win.character_preset_combo.currentData() or "")
        win.character_preset_combo.clear()
        for ap in character_auto_presets_for_ui(_current_vf_for_char_presets()):
            win.character_preset_combo.addItem(ap.label, ap.id)
        ix = win.character_preset_combo.findData(cur)
        if ix >= 0:
            win.character_preset_combo.setCurrentIndex(ix)
        elif win.character_preset_combo.count() > 0:
            win.character_preset_combo.setCurrentIndex(0)

    _refresh_character_preset_combo()
    win._refresh_character_preset_combo = _refresh_character_preset_combo
    gen_row.addWidget(win.character_preset_combo, 1)
    win.character_generate_btn = QPushButton("Generate with LLM")
    win.character_generate_btn.setProperty("buttonRole", "secondary")
    win.character_generate_btn.setMaximumHeight(28)
    win.character_generate_btn.setMinimumWidth(132)
    win.character_generate_btn.setToolTip(
        help_tooltip_rich(
            "Fill name, identity, visual style, and negatives using the Model-tab script LLM (loads weights like other brain tasks). "
            "Preset picks use the same LLM to invent a profile - click Save character when happy.",
            "topics_chars",
            slide=2,
        )
    )
    gen_row.addWidget(win.character_generate_btn)
    list_lay.addLayout(gen_row)

    win.character_preset_notes_edit = QLineEdit()
    win.character_preset_notes_edit.setPlaceholderText("Optional extra notes for this generation (style, audience, running gag…)")
    win.character_preset_notes_edit.setMaximumHeight(26)
    list_lay.addWidget(win.character_preset_notes_edit)

    cards_scroll = QScrollArea()
    cards_scroll.setWidgetResizable(True)
    cards_scroll.setMinimumHeight(220)
    cards_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    win.characters_cards_inner = QWidget()
    win.characters_cards_layout = QVBoxLayout(win.characters_cards_inner)
    win.characters_cards_layout.setContentsMargins(0, 0, 0, 0)
    win.characters_cards_layout.setSpacing(8)
    cards_scroll.setWidget(win.characters_cards_inner)
    list_lay.addWidget(cards_scroll, 1)

    win.characters_empty_hint = QLabel(
        "No characters yet. Use the + button or \u201cGenerate with LLM\u201d to add your first profile."
    )
    win.characters_empty_hint.setWordWrap(True)
    win.characters_empty_hint.setStyleSheet(f"color: {token('muted', '#8A96A3')}; font-size: 11px;")
    win.characters_empty_hint.setVisible(False)
    list_lay.addWidget(win.characters_empty_hint)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)
    _tb_pal = resolve_palette(getattr(win.settings, "branding", None))
    _tb_muted = str(_tb_pal.get("muted", "#B7B7C2"))
    _tb_icon_px = 22
    win.characters_add_btn = QPushButton()
    win.characters_add_btn.setIcon(qicon_toolbar("folder_plus", _tb_muted, _tb_icon_px))
    win.characters_add_btn.setToolTip(help_tooltip_rich("Add a new character profile.", "topics_chars", slide=2))
    win.characters_add_btn.setAccessibleName("Add character")
    win.characters_dup_btn = QPushButton()
    win.characters_dup_btn.setIcon(qicon_toolbar("duplicate", _tb_muted, _tb_icon_px))
    win.characters_dup_btn.setToolTip(help_tooltip_rich("Duplicate the selected character.", "topics_chars", slide=2))
    win.characters_dup_btn.setAccessibleName("Duplicate character")
    win.characters_del_btn = QPushButton()
    win.characters_del_btn.setIcon(qicon_toolbar("trash", _tb_muted, _tb_icon_px))
    win.characters_del_btn.setToolTip(help_tooltip_rich("Delete the selected character.", "topics_chars", slide=2))
    win.characters_del_btn.setAccessibleName("Delete character")
    for b in (win.characters_add_btn, win.characters_dup_btn, win.characters_del_btn):
        b.setProperty("buttonRole", "secondary")
        b.setMaximumHeight(28)
        b.setMinimumWidth(30)
        b.setMaximumWidth(34)
    btn_row.addWidget(win.characters_add_btn)
    btn_row.addWidget(win.characters_dup_btn)
    btn_row.addWidget(win.characters_del_btn)
    btn_row.addStretch(1)
    list_lay.addLayout(btn_row)
    left_lay.addWidget(list_card, 1)

    right_scroll = QScrollArea()
    right_scroll.setWidgetResizable(True)
    right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    right_inner = QWidget()
    right_lay = QVBoxLayout(right_inner)
    right_lay.setContentsMargins(0, 0, 0, 8)
    right_lay.setSpacing(3)

    edit_card, edit_lay = section_card(margins=10, spacing=6)
    edit_lay.addWidget(section_title("Profile", emphasis=True))

    win.character_name_edit = QLineEdit()
    win.character_name_edit.setPlaceholderText("Name")
    win.character_name_edit.setMaximumHeight(26)
    lbl_name = QLabel("Name")
    lbl_name.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    edit_lay.addWidget(lbl_name)
    edit_lay.addWidget(win.character_name_edit)

    tok_row = QHBoxLayout()
    tok_row.setSpacing(8)
    for _lbl_txt, _attr, _options in (
        ("Gender", "character_gender_combo", CHARACTER_GENDER_OPTIONS),
        ("Ethnicity", "character_ethnicity_combo", CHARACTER_ETHNICITY_OPTIONS),
        ("Age band", "character_age_range_combo", CHARACTER_AGE_RANGE_OPTIONS),
    ):
        col = QVBoxLayout()
        col.setSpacing(2)
        t_l = QLabel(_lbl_txt)
        t_l.setStyleSheet("color: #B7B7C2; font-size: 11px;")
        col.addWidget(t_l)
        cb = NoWheelComboBox()
        cb.setMaximumHeight(26)
        setattr(win, _attr, cb)
        _fill_fixed_combo(cb, _options, "")
        col.addWidget(cb)
        tok_row.addLayout(col)
    edit_lay.addLayout(tok_row)

    lbl_id = QLabel("Identity / persona (script + on-screen)")
    lbl_id.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    edit_lay.addWidget(lbl_id)
    win.character_identity_edit = QTextEdit()
    win.character_identity_edit.setMinimumHeight(36)
    win.character_identity_edit.setMaximumHeight(72)
    win.character_identity_edit.setPlaceholderText("Who is this host? Tone, channel, audience…")
    win.character_identity_edit.setAcceptRichText(False)
    win.character_identity_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    edit_lay.addWidget(win.character_identity_edit)

    lbl_vis = QLabel("Visual style (prepended to image prompts)")
    lbl_vis.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    edit_lay.addWidget(lbl_vis)
    win.character_visual_edit = QTextEdit()
    win.character_visual_edit.setMinimumHeight(32)
    win.character_visual_edit.setMaximumHeight(64)
    win.character_visual_edit.setPlaceholderText("e.g. neon cyberpunk studio, warm key light, mascot host…")
    win.character_visual_edit.setAcceptRichText(False)
    win.character_visual_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    edit_lay.addWidget(win.character_visual_edit)

    portrait_row = QHBoxLayout()
    portrait_row.setSpacing(8)
    win.character_portrait_generate_btn = QPushButton("Generate portrait")
    win.character_portrait_generate_btn.setProperty("buttonRole", "secondary")
    win.character_portrait_generate_btn.setMaximumHeight(28)
    win.character_portrait_generate_btn.setMinimumWidth(132)
    win.character_portrait_generate_btn.setToolTip(
        help_tooltip_rich(
            "Render one reference still with the image model selected on the Model tab. Requires Visual style text.",
            "topics_chars",
            slide=2,
        )
    )
    portrait_row.addWidget(win.character_portrait_generate_btn)
    win.character_portrait_preview = _PortraitThumbLabel()
    win.character_portrait_preview.setFixedSize(100, 120)
    win.character_portrait_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win.character_portrait_preview.setStyleSheet(
        "QLabel { background-color: #14141A; border: 1px solid #2E2E38; border-radius: 6px; color: #6A6A78; font-size: 10px; }"
    )
    win.character_portrait_preview.setText("No portrait")
    win.character_portrait_preview.setScaledContents(False)
    portrait_row.addWidget(win.character_portrait_preview)
    portrait_row.addStretch(1)
    edit_lay.addLayout(portrait_row)
    portrait_hint = QLabel("")
    portrait_hint.setWordWrap(True)
    portrait_hint.setStyleSheet("color: #8A96A3; font-size: 10px;")
    portrait_hint.setText("Portrait uses the image model selected on the Model tab (same weights as slideshow / Run stills).")
    portrait_hint.setToolTip(
        help_tooltip_rich(
            "Fill Visual style first - the portrait prompt is built from it. Saved on this profile for the script LLM and storyboards.",
            "topics_chars",
            slide=2,
        )
    )
    edit_lay.addWidget(portrait_hint)

    lbl_neg = QLabel("Extra negatives for diffusion (comma phrases)")
    lbl_neg.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    edit_lay.addWidget(lbl_neg)
    win.character_negatives_edit = QTextEdit()
    win.character_negatives_edit.setMaximumHeight(40)
    win.character_negatives_edit.setPlaceholderText("e.g. extra fingers, watermark")
    win.character_negatives_edit.setAcceptRichText(False)
    win.character_negatives_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    edit_lay.addWidget(win.character_negatives_edit)

    win.character_default_voice_chk = ThemedSwitch("Use project default voice (Settings → Voice model)")
    win.character_default_voice_chk.setChecked(True)
    win.character_default_voice_chk.setStyleSheet("font-size: 11px; font-weight: 600;")
    edit_lay.addWidget(win.character_default_voice_chk)

    vrow = QHBoxLayout()
    vrow.setSpacing(6)
    v_lbl = QLabel("On-device voice (pyttsx3)")
    v_lbl.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    v_lbl.setMinimumWidth(108)
    vrow.addWidget(v_lbl)
    win.character_voice_combo = NoWheelComboBox()
    win.character_voice_combo.setMinimumWidth(200)
    win.character_voice_combo.setMaximumHeight(26)
    vrow.addWidget(win.character_voice_combo, 1)
    win.character_voice_refresh_btn = QPushButton("Refresh")
    win.character_voice_refresh_btn.setProperty("buttonRole", "secondary")
    win.character_voice_refresh_btn.setMaximumHeight(28)
    win.character_voice_refresh_btn.setMinimumWidth(88)
    win.character_voice_refresh_btn.setToolTip(
        help_tooltip_rich("Refresh the local pyttsx3 voice list.", "topics_chars", slide=2)
    )
    vrow.addWidget(win.character_voice_refresh_btn)
    edit_lay.addLayout(vrow)

    lbl_ko = QLabel("Kokoro voice (optional)")
    lbl_ko.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    edit_lay.addWidget(lbl_ko)
    win.character_kokoro_edit = QLineEdit()
    win.character_kokoro_edit.setPlaceholderText("e.g. af_bella or “Bella” - leave empty to rotate voices")
    win.character_kokoro_edit.setMaximumHeight(26)
    edit_lay.addWidget(win.character_kokoro_edit)

    lbl_vi = QLabel("Voice description (MOSS only)")
    lbl_vi.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lbl_vi.setToolTip(
        help_tooltip_rich(
            "When Settings → Voice model is OpenMOSS MOSS-VoiceGenerator: describe the voice "
            "(e.g. a young woman with a raspy voice, speaking fast). Not used for Kokoro.",
            "topics_chars",
            slide=2,
        )
    )
    edit_lay.addWidget(lbl_vi)
    win.character_voice_instruction_combo = NoWheelComboBox()
    win.character_voice_instruction_combo.setMaximumHeight(26)
    win.character_voice_instruction_combo.setToolTip(
        'Used by MOSS-VoiceGenerator and ElevenLabs. Choose "(LLM decides)" to let generation pick.'
    )
    _fill_fixed_combo(win.character_voice_instruction_combo, CHARACTER_VOICE_INSTRUCTION_OPTIONS, "")
    edit_lay.addWidget(win.character_voice_instruction_combo)

    win.character_el_container = QWidget()
    el_outer = QVBoxLayout(win.character_el_container)
    el_outer.setContentsMargins(0, 0, 0, 0)
    el_outer.setSpacing(2)
    win.character_el_hint = QLabel("ElevenLabs when default voice is off - configure on API tab.")
    win.character_el_hint.setWordWrap(True)
    win.character_el_hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    win.character_el_hint.setToolTip(
        help_tooltip_rich(
            "Requires API tab + key or ELEVENLABS_API_KEY in the environment.",
            "api_social",
            slide=0,
        )
    )
    el_outer.addWidget(win.character_el_hint)
    el_row = QHBoxLayout()
    el_row.setSpacing(6)
    el_lbl = QLabel("ElevenLabs voice")
    el_lbl.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    el_lbl.setMinimumWidth(108)
    el_row.addWidget(el_lbl)
    win.character_el_voice_combo = NoWheelComboBox()
    win.character_el_voice_combo.setMinimumWidth(200)
    win.character_el_voice_combo.setMaximumHeight(26)
    el_row.addWidget(win.character_el_voice_combo, 1)
    win.character_el_refresh_btn = QPushButton("Refresh EL")
    win.character_el_refresh_btn.setProperty("buttonRole", "secondary")
    win.character_el_refresh_btn.setMaximumHeight(28)
    win.character_el_refresh_btn.setMinimumWidth(98)
    win.character_el_refresh_btn.setToolTip(
        help_tooltip_rich("Refresh the ElevenLabs voice list from the API.", "api_social", slide=0)
    )
    el_row.addWidget(win.character_el_refresh_btn)
    el_outer.addLayout(el_row)
    edit_lay.addWidget(win.character_el_container)

    right_lay.addWidget(edit_card)
    right_scroll.setWidget(right_inner)

    register_advanced_sections(win, "characters", [right_scroll])

    split = two_column_row(left_panel, right_scroll, ratio=(2, 3), spacing=16)
    lay.addWidget(split, 1)

    foot = QWidget()
    foot_lay = QHBoxLayout(foot)
    foot_lay.setContentsMargins(0, 6, 0, 0)
    foot_lay.setSpacing(10)
    win.characters_save_btn = QPushButton("Save character")
    win.characters_save_btn.setObjectName("primary")
    win.characters_save_btn.setMinimumHeight(34)
    win.characters_save_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    foot_lay.addWidget(win.characters_save_btn)
    foot_lay.addStretch(1)
    lay.addWidget(foot)

    w.setStyleSheet(
        """
        QTextEdit { font-size: 11px; padding: 2px 4px; }
        QLineEdit { font-size: 11px; padding: 2px 4px; }
        """
    )

    all_chars: list[Character] = []
    _current_id: str | None = None
    _el_voices_cache: list[tuple[str, str]] = []
    _el_worker: _ElevenLabsVoicesThread | None = None
    _char_gen_worker: CharacterGenerateWorker | None = None
    _portrait_worker: CharacterPortraitWorker | None = None

    def _update_el_visibility() -> None:
        ok = elevenlabs_available_for_app(win.settings)
        win.character_el_container.setVisible(ok)
        if not ok:
            _fill_el_voice_combo(win.character_el_voice_combo, "", [])
        elif not _el_voices_cache:
            _start_el_fetch()

    def _start_el_fetch() -> None:
        nonlocal _el_worker
        key = effective_elevenlabs_api_key(win.settings)
        if not key:
            return
        if _el_worker is not None and _el_worker.isRunning():
            return
        th = _ElevenLabsVoicesThread(key)
        _el_worker = th

        def _ok(voices: object) -> None:
            nonlocal _el_voices_cache
            parsed: list[tuple[str, str]] = []
            if isinstance(voices, list):
                for item in voices:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        parsed.append((str(item[0]), str(item[1])))
            _el_voices_cache = parsed
            ch = get_by_id(all_chars, str(_current_id or "")) if _current_id else None
            el_id = (ch.elevenlabs_voice_id if ch else "") or ""
            _fill_el_voice_combo(win.character_el_voice_combo, el_id, _el_voices_cache)
            th.deleteLater()

        def _fail(msg: str) -> None:
            if hasattr(win, "_append_log"):
                win._append_log(f"ElevenLabs voices: {msg}")
            th.deleteLater()

        th.finished_ok.connect(_ok)
        th.failed.connect(_fail)
        th.start()

    def _on_el_refresh_clicked() -> None:
        nonlocal _el_voices_cache
        _el_voices_cache = []
        _start_el_fetch()

    def _select_character_id(cid: str | None, *, load_form: bool = True) -> None:
        nonlocal _current_id
        _current_id = str(cid) if cid else None
        cards = getattr(win, "_character_card_widgets", {}) or {}
        for card_id, card in cards.items():
            try:
                card.set_selected(card_id == _current_id)
            except Exception:
                pass
        if load_form and _current_id:
            ch = get_by_id(all_chars, _current_id)
            if ch:
                _load_form(ch)

    def _refresh_list(select_id: str | None = None) -> None:
        nonlocal all_chars, _current_id
        all_chars = load_all()
        lay_cards = win.characters_cards_layout
        while lay_cards.count():
            item = lay_cards.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        win._character_card_widgets = {}
        sid = select_id if select_id is not None else _current_id
        for c in all_chars:
            card = CharacterCard(c, is_selected=(c.id == sid), parent=win.characters_cards_inner)
            card.selected.connect(lambda cid=c.id: _select_character_id(cid))
            lay_cards.addWidget(card)
            win._character_card_widgets[c.id] = card
        lay_cards.addStretch(1)
        if hasattr(win, "characters_empty_hint"):
            win.characters_empty_hint.setVisible(not all_chars)
        if select_id:
            _current_id = select_id
            _select_character_id(select_id)
        elif all_chars and not _current_id:
            _select_character_id(all_chars[0].id)
        elif sid and sid in win._character_card_widgets:
            _select_character_id(sid)

    def _refresh_portrait_thumb() -> None:
        ch = get_by_id(all_chars, str(_current_id)) if _current_id else None
        p = character_reference_image_resolved(ch) if ch else None
        win.character_portrait_preview.clear()
        if p is not None and p.exists():
            pm = QPixmap(str(p))
            if not pm.isNull():
                win.character_portrait_preview.setPixmap(
                    pm.scaled(
                        100,
                        120,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                win.character_portrait_preview.setText("")
                win.character_portrait_preview.setToolTip(
                    "Click portrait to enlarge (maximized preview)."
                )
                win.character_portrait_preview.setCursor(Qt.CursorShape.PointingHandCursor)
                return
        win.character_portrait_preview.setPixmap(QPixmap())
        win.character_portrait_preview.setText("No portrait")
        win.character_portrait_preview.setToolTip("")
        win.character_portrait_preview.setCursor(Qt.CursorShape.ArrowCursor)

    def _load_form(c: Character) -> None:
        win.character_name_edit.setText(c.name)
        _fill_fixed_combo(win.character_gender_combo, CHARACTER_GENDER_OPTIONS, c.gender)
        _fill_fixed_combo(win.character_ethnicity_combo, CHARACTER_ETHNICITY_OPTIONS, c.ethnicity)
        _fill_fixed_combo(win.character_age_range_combo, CHARACTER_AGE_RANGE_OPTIONS, c.age_range)
        win.character_identity_edit.setPlainText(c.identity)
        win.character_visual_edit.setPlainText(c.visual_style)
        win.character_negatives_edit.setPlainText(c.negatives)
        win.character_default_voice_chk.setChecked(c.use_default_voice)
        _fill_voice_combo(win.character_voice_combo, c.pyttsx3_voice_id)
        win.character_kokoro_edit.setText(c.kokoro_voice)
        _fill_fixed_combo(win.character_voice_instruction_combo, CHARACTER_VOICE_INSTRUCTION_OPTIONS, c.voice_instruction)
        if elevenlabs_available_for_app(win.settings):
            _fill_el_voice_combo(win.character_el_voice_combo, c.elevenlabs_voice_id, _el_voices_cache)
        else:
            _fill_el_voice_combo(win.character_el_voice_combo, "", [])
        _refresh_portrait_thumb()

    def _on_select() -> None:
        _select_character_id(_current_id, load_form=True)

    def _read_form() -> Character | None:
        nonlocal _current_id
        name = win.character_name_edit.text().strip() or "Unnamed"
        if not _current_id:
            return None

        base = get_by_id(all_chars, _current_id)
        if not base:
            return None
        return Character(
            id=base.id,
            name=name[:120],
            identity=win.character_identity_edit.toPlainText(),
            visual_style=win.character_visual_edit.toPlainText(),
            negatives=win.character_negatives_edit.toPlainText(),
            gender=str(win.character_gender_combo.currentData() or "").strip(),
            ethnicity=str(win.character_ethnicity_combo.currentData() or "").strip(),
            age_range=str(win.character_age_range_combo.currentData() or "").strip(),
            reference_image_rel=str(getattr(base, "reference_image_rel", "") or "").strip(),
            use_default_voice=bool(win.character_default_voice_chk.isChecked()),
            pyttsx3_voice_id=str(win.character_voice_combo.currentData() or "").strip(),
            kokoro_voice=win.character_kokoro_edit.text().strip(),
            voice_instruction=str(win.character_voice_instruction_combo.currentData() or "").strip(),
            elevenlabs_voice_id=str(win.character_el_voice_combo.currentData() or "").strip(),
        )

    def _on_save() -> None:
        nonlocal all_chars
        ch = _read_form()
        if not ch:
            aquaduct_warning(w, "Characters", "Select or add a character first.")
            return
        all_chars = upsert(all_chars, ch)
        save_all(all_chars)
        _refresh_list(select_id=ch.id)
        if hasattr(win, "_refresh_character_combo"):
            win._refresh_character_combo()
        if hasattr(win, "_append_log"):
            win._append_log(f"Saved character “{ch.name}”.")
        _on_select()

    def _on_add() -> None:
        nonlocal all_chars, _current_id
        nc = new_character(name="New character")
        all_chars = upsert(all_chars, nc)
        save_all(all_chars)
        _current_id = nc.id
        _refresh_list(select_id=nc.id)
        _load_form(nc)
        if hasattr(win, "_refresh_character_combo"):
            win._refresh_character_combo()

    def _on_duplicate() -> None:
        nonlocal all_chars, _current_id
        ch = _read_form()
        if not ch:
            aquaduct_warning(w, "Characters", "Select a character to duplicate.")
            return
        dup = new_character(name=f"{ch.name} (copy)")
        ref_rel = ""
        old_p = character_portrait_abs_path(ch.id)
        if old_p.is_file():
            new_p = character_portrait_abs_path(dup.id)
            new_p.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(old_p, new_p)
                ref_rel = character_portrait_relpath(dup.id)
            except OSError:
                ref_rel = ""
        dup = Character(
            id=dup.id,
            name=dup.name,
            identity=ch.identity,
            visual_style=ch.visual_style,
            negatives=ch.negatives,
            gender=ch.gender,
            ethnicity=ch.ethnicity,
            age_range=ch.age_range,
            reference_image_rel=ref_rel,
            use_default_voice=ch.use_default_voice,
            pyttsx3_voice_id=ch.pyttsx3_voice_id,
            kokoro_voice=ch.kokoro_voice,
            voice_instruction=ch.voice_instruction,
            elevenlabs_voice_id=ch.elevenlabs_voice_id,
        )
        all_chars = upsert(all_chars, dup)
        save_all(all_chars)
        _current_id = dup.id
        _refresh_list(select_id=dup.id)
        _load_form(dup)
        if hasattr(win, "_refresh_character_combo"):
            win._refresh_character_combo()

    def _on_generate_character() -> None:
        nonlocal _char_gen_worker
        if _char_gen_worker is not None and _char_gen_worker.isRunning():
            return
        if not _current_id:
            aquaduct_warning(w, "Characters", "Add or select a character first.")
            return
        s = getattr(win, "settings", None)
        if s is not None and is_api_mode(s):
            if not api_role_ready(s, "llm"):
                aquaduct_warning(
                    w,
                    "Characters",
                    "In API mode, configure the LLM provider and model (Generation APIs) and save settings.",
                )
                return
            mid = ""
        else:
            mid = resolve_llm_model_id(win)
            if not mid:
                aquaduct_warning(w, "Characters", "Pick a script (LLM) model on the Model tab.")
                return
        pid = str(win.character_preset_combo.currentData() or "").strip()
        preset = get_character_auto_preset_by_id(pid)
        if preset is None:
            aquaduct_warning(w, "Characters", "Select a preset.")
            return

        th = CharacterGenerateWorker(
            model_id=mid,
            preset=preset,
            extra_notes=win.character_preset_notes_edit.text(),
            try_llm_4bit=bool(getattr(win.settings, "try_llm_4bit", True)),
            hf_token=str(getattr(win.settings, "hf_token", "") or ""),
            hf_api_enabled=bool(getattr(win.settings, "hf_api_enabled", True)),
            app_settings=getattr(win, "settings", None),
        )
        _char_gen_worker = th

        dlg = AuxiliaryProgressDialog(
            win,
            window_title="Generate with LLM",
            initial_message="Starting…",
        )
        dlg.show()
        th.progress.connect(dlg.slot_update)

        win.character_generate_btn.setEnabled(False)
        win.character_generate_btn.setText("Generating…")

        def _ok(fields: object) -> None:
            nonlocal _char_gen_worker

            try:
                dlg.close()
            except Exception:
                pass
            schedule_auxiliary_job_memory_purge()
            _char_gen_worker = None
            win.character_generate_btn.setEnabled(True)
            win.character_generate_btn.setText("Generate with LLM")
            if not isinstance(fields, GeneratedCharacterFields):
                return
            win.character_name_edit.setText(fields.name)
            _fill_fixed_combo(win.character_gender_combo, CHARACTER_GENDER_OPTIONS, fields.gender)
            _fill_fixed_combo(win.character_ethnicity_combo, CHARACTER_ETHNICITY_OPTIONS, fields.ethnicity)
            _fill_fixed_combo(win.character_age_range_combo, CHARACTER_AGE_RANGE_OPTIONS, fields.age_range)
            win.character_identity_edit.setPlainText(fields.identity)
            win.character_visual_edit.setPlainText(fields.visual_style)
            win.character_negatives_edit.setPlainText(fields.negatives)
            win.character_default_voice_chk.setChecked(fields.use_default_voice)
            _fill_fixed_combo(
                win.character_voice_instruction_combo,
                CHARACTER_VOICE_INSTRUCTION_OPTIONS,
                getattr(fields, "voice_instruction", ""),
            )
            if hasattr(win, "_append_log"):
                win._append_log(f"Generated character fields - preset “{preset.label}”. Click Save character to keep.")

        def _fail(msg: str) -> None:
            nonlocal _char_gen_worker
            try:
                dlg.close()
            except Exception:
                pass
            schedule_auxiliary_job_memory_purge()
            _char_gen_worker = None
            win.character_generate_btn.setEnabled(True)
            win.character_generate_btn.setText("Generate with LLM")
            short = (msg or "").strip()
            if len(short) > 1600:
                short = short[:1600] + "…"
            aquaduct_warning(w, "Character generation", short)

        th.done.connect(_ok)
        th.failed.connect(_fail)
        th.finished.connect(th.deleteLater)
        th.start()

    def _on_generate_portrait() -> None:
        nonlocal all_chars, _portrait_worker
        if _portrait_worker is not None and _portrait_worker.isRunning():
            return
        if not _current_id:
            aquaduct_warning(w, "Characters", "Select a character first.")
            return
        vs = win.character_visual_edit.toPlainText().strip()
        if not vs:
            aquaduct_warning(
                w,
                "Characters",
                "Fill in Visual style first - the portrait prompt is built from that field.",
            )
            return
        s = getattr(win, "settings", None)
        if s is not None and is_api_mode(s):
            if not api_role_ready(s, "image"):
                aquaduct_warning(
                    w,
                    "Characters",
                    "In API mode, configure the Image provider and model (Generation APIs) and save settings.",
                )
                return
            img_id = ""
        else:
            img_id = image_model_id_from_ui(win)
            if not img_id:
                aquaduct_warning(
                    w,
                    "Characters",
                    "Choose an image model on the Model tab (same weights used for video slideshow images).",
                )
                return
        base = get_by_id(all_chars, str(_current_id))
        if not base:
            return
        th = CharacterPortraitWorker(
            image_model_id=img_id,
            character_id=base.id,
            visual_style=vs,
            subject_prefix=subject_token_phrase(base),
            allow_nsfw=(
                bool(getattr(win.settings, "allow_nsfw", False))
                or normalize_video_format(_current_vf_for_char_presets()) == "nsfw"
                or str(win.character_preset_combo.currentData() or "").strip().lower().startswith("nsfw_")
            ),
            app_settings=getattr(win, "settings", None),
            steps=4,
            art_style_preset_id=str(getattr(win.settings, "art_style_preset_id", None) or "balanced"),
        )
        _portrait_worker = th

        dlg = AuxiliaryProgressDialog(
            win,
            window_title="Portrait generation",
            initial_message="Starting…",
        )
        dlg.show()
        th.progress.connect(dlg.slot_update)

        win.character_portrait_generate_btn.setEnabled(False)
        win.character_portrait_generate_btn.setText("Generating…")

        def _ok(rel: str) -> None:
            nonlocal all_chars, _portrait_worker
            try:
                dlg.close()
            except Exception:
                pass
            schedule_auxiliary_job_memory_purge()
            _portrait_worker = None
            win.character_portrait_generate_btn.setEnabled(True)
            win.character_portrait_generate_btn.setText("Generate portrait")
            cid = str(_current_id or "")
            if not cid:
                return
            cur = get_by_id(all_chars, cid)
            if not cur:
                return
            updated = replace(cur, reference_image_rel=str(rel or "").strip())
            all_chars = upsert(all_chars, updated)
            save_all(all_chars)
            _refresh_portrait_thumb()
            if hasattr(win, "_append_log"):
                win._append_log("Saved character reference portrait for video consistency.")

        def _fail(msg: str) -> None:
            nonlocal _portrait_worker
            try:
                dlg.close()
            except Exception:
                pass
            schedule_auxiliary_job_memory_purge()
            _portrait_worker = None
            win.character_portrait_generate_btn.setEnabled(True)
            win.character_portrait_generate_btn.setText("Generate portrait")
            short = (msg or "").strip()
            if len(short) > 1600:
                short = short[:1600] + "…"
            aquaduct_warning(w, "Portrait generation", short)

        th.done.connect(_ok)
        th.failed.connect(_fail)
        th.finished.connect(th.deleteLater)
        th.start()

    def _on_delete() -> None:
        nonlocal all_chars, _current_id
        if not _current_id:
            return

        ch = get_by_id(all_chars, str(_current_id))
        if not ch:
            return
        if not aquaduct_question(
            w,
            "Delete character",
            f"Delete “{ch.name}”?",
            default_no=True,
        ):
            return
        delete_character_assets(ch.id)
        all_chars = delete_by_id(all_chars, ch.id)
        save_all(all_chars)
        _current_id = None
        _refresh_list()
        if hasattr(win, "settings") and str(getattr(win.settings, "active_character_id", "") or "") == ch.id:
            win.settings = replace(win.settings, active_character_id="")  # type: ignore[misc]
            save_settings(win.settings)
        if hasattr(win, "_refresh_character_combo"):
            win._refresh_character_combo()

    def _open_portrait_preview() -> None:
        ch = get_by_id(all_chars, str(_current_id or "")) if _current_id else None
        if ch is None:
            return
        p = character_reference_image_resolved(ch)
        if p is None or not p.exists():
            return
        pm = QPixmap(str(p))
        if pm.isNull():
            return
        title = str(ch.name or "Character").strip() or "Character"
        dlg = FramelessDialog(win, title=f"Portrait - {title}"[:120])
        img = _FitPixmapLabel(pm)
        dlg.body_layout.addWidget(img, 1)
        dlg.showMaximized()
        dlg.exec()

    win.characters_save_btn.clicked.connect(_on_save)
    win.characters_add_btn.clicked.connect(_on_add)
    win.characters_dup_btn.clicked.connect(_on_duplicate)
    win.characters_del_btn.clicked.connect(_on_delete)
    win.character_voice_refresh_btn.clicked.connect(
        lambda: _fill_voice_combo(win.character_voice_combo, str(win.character_voice_combo.currentData() or ""))
    )
    win.character_el_refresh_btn.clicked.connect(_on_el_refresh_clicked)
    win.character_generate_btn.clicked.connect(_on_generate_character)
    win.character_portrait_generate_btn.clicked.connect(_on_generate_portrait)
    win.character_portrait_preview.portraitClicked.connect(_open_portrait_preview)

    QTimer.singleShot(0, lambda: _fill_voice_combo(win.character_voice_combo, ""))
    _update_el_visibility()
    win._characters_refresh_elevenlabs = _update_el_visibility  # main_window calls when switching to Characters tab

    _refresh_list()

    win.tabs.addTab(w, "Characters")
