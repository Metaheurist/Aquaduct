from __future__ import annotations

import shutil
from dataclasses import replace

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.content.character_presets import (
    GeneratedCharacterFields,
    get_character_auto_preset_by_id,
    get_character_auto_presets,
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
    upsert,
)
from src.runtime.model_backend import api_role_ready, is_api_mode
from src.speech.elevenlabs_tts import effective_elevenlabs_api_key, elevenlabs_available_for_app
from src.settings.ui_settings import save_settings
from src.speech.voice import list_pyttsx3_voices as list_sys_voices
from UI.brain_expand import image_model_id_from_ui, resolve_llm_model_id
from UI.frameless_dialog import aquaduct_question, aquaduct_warning
from UI.workers import CharacterGenerateWorker, CharacterPortraitWorker


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


def _first_non_empty_standard_icon(style: QStyle, *pixmaps: QStyle.StandardPixmap) -> QIcon:
    """``SP_DialogSaveAllButton`` is often blank on Windows + Fusion; try alternatives."""
    for px in pixmaps:
        ic = style.standardIcon(px)
        if not ic.isNull():
            return ic
    return QIcon()


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
    lay.setContentsMargins(6, 4, 6, 4)
    lay.setSpacing(2)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    inner = QWidget()
    inner_lay = QVBoxLayout(inner)
    inner_lay.setContentsMargins(0, 0, 4, 8)
    inner_lay.setSpacing(3)

    header = QLabel("Characters")
    header.setStyleSheet("font-size: 13px; font-weight: 700;")
    inner_lay.addWidget(header)

    hint = QLabel("Host identity, visuals, optional TTS — pick one on the Run tab.")
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #B7B7C2; font-size: 10px;")
    inner_lay.addWidget(hint)

    gen_hint = QLabel("Auto presets use the script (LLM) model from the Model tab to invent a profile — Save character when happy.")
    gen_hint.setWordWrap(True)
    gen_hint.setStyleSheet("color: #8A96A3; font-size: 10px;")
    inner_lay.addWidget(gen_hint)

    gen_row = QHBoxLayout()
    gen_row.setSpacing(6)
    gen_lbl = QLabel("Preset")
    gen_lbl.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    gen_lbl.setMinimumWidth(44)
    gen_row.addWidget(gen_lbl)
    win.character_preset_combo = QComboBox()
    win.character_preset_combo.setMinimumWidth(160)
    win.character_preset_combo.setMaximumHeight(26)
    for ap in get_character_auto_presets():
        win.character_preset_combo.addItem(ap.label, ap.id)
    gen_row.addWidget(win.character_preset_combo, 1)
    win.character_generate_btn = QPushButton("Generate with LLM")
    win.character_generate_btn.setProperty("buttonRole", "secondary")
    win.character_generate_btn.setMaximumHeight(28)
    win.character_generate_btn.setMinimumWidth(132)
    win.character_generate_btn.setToolTip(
        "Fill name, identity, visual style, and negatives using the Model-tab script LLM (loads weights like other brain tasks)."
    )
    gen_row.addWidget(win.character_generate_btn)
    inner_lay.addLayout(gen_row)

    win.character_preset_notes_edit = QLineEdit()
    win.character_preset_notes_edit.setPlaceholderText("Optional extra notes for this generation (style, audience, running gag…)")
    win.character_preset_notes_edit.setMaximumHeight(26)
    inner_lay.addWidget(win.character_preset_notes_edit)

    win.characters_list = QListWidget()
    win.characters_list.setMinimumHeight(56)
    win.characters_list.setMaximumHeight(100)
    inner_lay.addWidget(win.characters_list)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)
    _sty = w.style()
    win.characters_add_btn = QPushButton()
    win.characters_add_btn.setIcon(_sty.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
    win.characters_add_btn.setToolTip("Add character")
    win.characters_add_btn.setAccessibleName("Add character")
    win.characters_dup_btn = QPushButton()
    _dup_icon = _first_non_empty_standard_icon(
        _sty,
        QStyle.StandardPixmap.SP_FileLinkIcon,
        QStyle.StandardPixmap.SP_DialogSaveAllButton,
        QStyle.StandardPixmap.SP_DialogApplyButton,
        QStyle.StandardPixmap.SP_FileDialogContentsView,
    )
    win.characters_dup_btn.setIcon(_dup_icon)
    if _dup_icon.isNull():
        win.characters_dup_btn.setText("⧉")
    win.characters_dup_btn.setToolTip("Duplicate character")
    win.characters_dup_btn.setAccessibleName("Duplicate character")
    win.characters_del_btn = QPushButton()
    win.characters_del_btn.setIcon(_sty.standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
    win.characters_del_btn.setToolTip("Delete character")
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
    inner_lay.addLayout(btn_row)

    win.character_name_edit = QLineEdit()
    win.character_name_edit.setPlaceholderText("Name")
    win.character_name_edit.setMaximumHeight(26)
    lbl_name = QLabel("Name")
    lbl_name.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    inner_lay.addWidget(lbl_name)
    inner_lay.addWidget(win.character_name_edit)

    lbl_id = QLabel("Identity / persona (script + on-screen)")
    lbl_id.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    inner_lay.addWidget(lbl_id)
    win.character_identity_edit = QTextEdit()
    win.character_identity_edit.setMinimumHeight(36)
    win.character_identity_edit.setMaximumHeight(72)
    win.character_identity_edit.setPlaceholderText("Who is this host? Tone, channel, audience…")
    win.character_identity_edit.setAcceptRichText(False)
    win.character_identity_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    inner_lay.addWidget(win.character_identity_edit)

    lbl_vis = QLabel("Visual style (prepended to image prompts)")
    lbl_vis.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    inner_lay.addWidget(lbl_vis)
    win.character_visual_edit = QTextEdit()
    win.character_visual_edit.setMinimumHeight(32)
    win.character_visual_edit.setMaximumHeight(64)
    win.character_visual_edit.setPlaceholderText("e.g. neon cyberpunk studio, warm key light, mascot host…")
    win.character_visual_edit.setAcceptRichText(False)
    win.character_visual_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    inner_lay.addWidget(win.character_visual_edit)

    portrait_row = QHBoxLayout()
    portrait_row.setSpacing(8)
    win.character_portrait_generate_btn = QPushButton("Generate portrait")
    win.character_portrait_generate_btn.setProperty("buttonRole", "secondary")
    win.character_portrait_generate_btn.setMaximumHeight(28)
    win.character_portrait_generate_btn.setMinimumWidth(132)
    win.character_portrait_generate_btn.setToolTip(
        "Render one reference still with the image model selected on the Model tab. Requires Visual style text."
    )
    portrait_row.addWidget(win.character_portrait_generate_btn)
    win.character_portrait_preview = QLabel()
    win.character_portrait_preview.setFixedSize(100, 120)
    win.character_portrait_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    win.character_portrait_preview.setStyleSheet(
        "QLabel { background-color: #14141A; border: 1px solid #2E2E38; border-radius: 6px; color: #6A6A78; font-size: 10px; }"
    )
    win.character_portrait_preview.setText("No portrait")
    win.character_portrait_preview.setScaledContents(False)
    portrait_row.addWidget(win.character_portrait_preview)
    portrait_row.addStretch(1)
    inner_lay.addLayout(portrait_row)
    portrait_hint = QLabel(
        "Uses the Model tab image weights. Fill Visual style above first — the portrait prompt is built from it. "
        "Saved on this profile for the script LLM and for video storyboard consistency."
    )
    portrait_hint.setWordWrap(True)
    portrait_hint.setStyleSheet("color: #8A96A3; font-size: 10px;")
    inner_lay.addWidget(portrait_hint)

    lbl_neg = QLabel("Extra negatives for diffusion (comma phrases)")
    lbl_neg.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    inner_lay.addWidget(lbl_neg)
    win.character_negatives_edit = QTextEdit()
    win.character_negatives_edit.setMaximumHeight(40)
    win.character_negatives_edit.setPlaceholderText("e.g. extra fingers, watermark")
    win.character_negatives_edit.setAcceptRichText(False)
    win.character_negatives_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    inner_lay.addWidget(win.character_negatives_edit)

    win.character_default_voice_chk = QCheckBox("Use project default voice (Settings → Voice model)")
    win.character_default_voice_chk.setChecked(True)
    win.character_default_voice_chk.setStyleSheet("font-size: 11px; font-weight: 600;")
    inner_lay.addWidget(win.character_default_voice_chk)

    vrow = QHBoxLayout()
    vrow.setSpacing(6)
    v_lbl = QLabel("System TTS (pyttsx3)")
    v_lbl.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    v_lbl.setMinimumWidth(108)
    vrow.addWidget(v_lbl)
    win.character_voice_combo = QComboBox()
    win.character_voice_combo.setMinimumWidth(200)
    win.character_voice_combo.setMaximumHeight(26)
    vrow.addWidget(win.character_voice_combo, 1)
    win.character_voice_refresh_btn = QPushButton("Refresh")
    win.character_voice_refresh_btn.setProperty("buttonRole", "secondary")
    win.character_voice_refresh_btn.setMaximumHeight(28)
    win.character_voice_refresh_btn.setMinimumWidth(88)
    win.character_voice_refresh_btn.setToolTip("Refresh pyttsx3 voice list")
    vrow.addWidget(win.character_voice_refresh_btn)
    inner_lay.addLayout(vrow)

    lbl_ko = QLabel("Kokoro speaker (optional)")
    lbl_ko.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    inner_lay.addWidget(lbl_ko)
    win.character_kokoro_edit = QLineEdit()
    win.character_kokoro_edit.setPlaceholderText("Optional Kokoro speaker id (when enabled in settings)")
    win.character_kokoro_edit.setMaximumHeight(26)
    inner_lay.addWidget(win.character_kokoro_edit)

    win.character_el_container = QWidget()
    el_outer = QVBoxLayout(win.character_el_container)
    el_outer.setContentsMargins(0, 0, 0, 0)
    el_outer.setSpacing(2)
    win.character_el_hint = QLabel(
        "ElevenLabs: API tab + key (or ELEVENLABS_API_KEY). Used when default voice is off."
    )
    win.character_el_hint.setWordWrap(True)
    win.character_el_hint.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    el_outer.addWidget(win.character_el_hint)
    el_row = QHBoxLayout()
    el_row.setSpacing(6)
    el_lbl = QLabel("ElevenLabs voice")
    el_lbl.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    el_lbl.setMinimumWidth(108)
    el_row.addWidget(el_lbl)
    win.character_el_voice_combo = QComboBox()
    win.character_el_voice_combo.setMinimumWidth(200)
    win.character_el_voice_combo.setMaximumHeight(26)
    el_row.addWidget(win.character_el_voice_combo, 1)
    win.character_el_refresh_btn = QPushButton("Refresh EL")
    win.character_el_refresh_btn.setProperty("buttonRole", "secondary")
    win.character_el_refresh_btn.setMaximumHeight(28)
    win.character_el_refresh_btn.setMinimumWidth(98)
    win.character_el_refresh_btn.setToolTip("Refresh ElevenLabs voice list")
    el_row.addWidget(win.character_el_refresh_btn)
    el_outer.addLayout(el_row)
    inner_lay.addWidget(win.character_el_container)

    scroll.setWidget(inner)

    foot = QWidget()
    foot_lay = QHBoxLayout(foot)
    foot_lay.setContentsMargins(0, 4, 0, 8)
    foot_lay.setSpacing(6)
    win.characters_save_btn = QPushButton("Save character")
    win.characters_save_btn.setObjectName("primary")
    win.characters_save_btn.setMinimumHeight(34)
    win.characters_save_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    foot_lay.addWidget(win.characters_save_btn)
    foot_lay.addStretch(1)

    lay.addWidget(scroll, 1)
    lay.addWidget(foot)

    w.setStyleSheet(
        """
        QListWidget { font-size: 11px; padding: 2px; }
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
            it = win.characters_list.currentItem()
            cid = str(it.data(256) or "") if it else ""
            ch = get_by_id(all_chars, cid) if cid else None
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

    def _refresh_list(select_id: str | None = None) -> None:
        nonlocal all_chars, _current_id
        all_chars = load_all()
        win.characters_list.clear()
        for c in all_chars:
            it = QListWidgetItem(c.name)
            it.setData(256, c.id)
            win.characters_list.addItem(it)
        sid = select_id if select_id is not None else _current_id
        if sid:
            _current_id = sid
            for i in range(win.characters_list.count()):
                it = win.characters_list.item(i)
                if it and it.data(256) == sid:
                    win.characters_list.setCurrentRow(i)
                    break
        elif win.characters_list.count():
            win.characters_list.setCurrentRow(0)

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
                return
        win.character_portrait_preview.setPixmap(QPixmap())
        win.character_portrait_preview.setText("No portrait")

    def _load_form(c: Character) -> None:
        win.character_name_edit.setText(c.name)
        win.character_identity_edit.setPlainText(c.identity)
        win.character_visual_edit.setPlainText(c.visual_style)
        win.character_negatives_edit.setPlainText(c.negatives)
        win.character_default_voice_chk.setChecked(c.use_default_voice)
        _fill_voice_combo(win.character_voice_combo, c.pyttsx3_voice_id)
        win.character_kokoro_edit.setText(c.kokoro_voice)
        if elevenlabs_available_for_app(win.settings):
            _fill_el_voice_combo(win.character_el_voice_combo, c.elevenlabs_voice_id, _el_voices_cache)
        else:
            _fill_el_voice_combo(win.character_el_voice_combo, "", [])
        _refresh_portrait_thumb()

    def _on_select() -> None:
        nonlocal _current_id
        it = win.characters_list.currentItem()
        if not it:
            _current_id = None
            return
        cid = it.data(256)
        _current_id = str(cid) if cid else None

        ch = get_by_id(all_chars, str(_current_id)) if _current_id else None
        if ch:
            _load_form(ch)

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
            reference_image_rel=str(getattr(base, "reference_image_rel", "") or "").strip(),
            use_default_voice=bool(win.character_default_voice_chk.isChecked()),
            pyttsx3_voice_id=str(win.character_voice_combo.currentData() or "").strip(),
            kokoro_voice=win.character_kokoro_edit.text().strip(),
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
            reference_image_rel=ref_rel,
            use_default_voice=ch.use_default_voice,
            pyttsx3_voice_id=ch.pyttsx3_voice_id,
            kokoro_voice=ch.kokoro_voice,
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
        win.character_generate_btn.setEnabled(False)
        win.character_generate_btn.setText("Generating…")

        def _ok(fields: object) -> None:
            nonlocal _char_gen_worker

            _char_gen_worker = None
            win.character_generate_btn.setEnabled(True)
            win.character_generate_btn.setText("Generate with LLM")
            if not isinstance(fields, GeneratedCharacterFields):
                return
            win.character_name_edit.setText(fields.name)
            win.character_identity_edit.setPlainText(fields.identity)
            win.character_visual_edit.setPlainText(fields.visual_style)
            win.character_negatives_edit.setPlainText(fields.negatives)
            win.character_default_voice_chk.setChecked(fields.use_default_voice)
            if hasattr(win, "_append_log"):
                win._append_log(f"Generated character fields — preset “{preset.label}”. Click Save character to keep.")

        def _fail(msg: str) -> None:
            nonlocal _char_gen_worker
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
                "Fill in Visual style first — the portrait prompt is built from that field.",
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
            allow_nsfw=bool(getattr(win.settings, "allow_nsfw", False)),
            app_settings=getattr(win, "settings", None),
            steps=4,
            art_style_preset_id=str(getattr(win.settings, "art_style_preset_id", None) or "balanced"),
        )
        _portrait_worker = th
        win.character_portrait_generate_btn.setEnabled(False)
        win.character_portrait_generate_btn.setText("Generating…")

        def _ok(rel: str) -> None:
            nonlocal all_chars, _portrait_worker
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
        it = win.characters_list.currentItem()
        if not it:
            return

        ch = get_by_id(all_chars, str(it.data(256) or ""))
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

    win.characters_list.currentRowChanged.connect(lambda _r: _on_select())
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

    _fill_voice_combo(win.character_voice_combo, "")
    _update_el_visibility()
    win._characters_refresh_elevenlabs = _update_el_visibility  # main_window calls when switching to Characters tab

    _refresh_list()
    if win.characters_list.count():
        win.characters_list.setCurrentRow(0)
        _on_select()

    win.tabs.addTab(w, "Characters")
