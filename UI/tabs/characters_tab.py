from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.characters_store import Character, delete_by_id, get_by_id, load_all, new_character, save_all, upsert
from src.elevenlabs_tts import effective_elevenlabs_api_key, elevenlabs_available_for_app
from src.ui_settings import save_settings
from src.voice import list_pyttsx3_voices as list_sys_voices
from UI.brain_expand import wrap_editor_with_brain
from UI.frameless_dialog import aquaduct_question, aquaduct_warning


class _ElevenLabsVoicesThread(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key

    def run(self) -> None:
        try:
            from src.elevenlabs_tts import list_voices

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
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(4)

    header = QLabel("Characters")
    header.setStyleSheet("font-size: 14px; font-weight: 700;")
    lay.addWidget(header)

    hint = QLabel("Host identity, visuals, optional TTS — pick one on the Run tab.")
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #8A96A3; font-size: 10px;")
    lay.addWidget(hint)

    win.characters_list = QListWidget()
    win.characters_list.setMinimumHeight(88)
    win.characters_list.setMaximumHeight(132)
    lay.addWidget(win.characters_list)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)
    win.characters_add_btn = QPushButton("Add")
    win.characters_dup_btn = QPushButton("Duplicate")
    win.characters_del_btn = QPushButton("Delete")
    for b in (win.characters_add_btn, win.characters_dup_btn, win.characters_del_btn):
        b.setMaximumHeight(28)
    btn_row.addWidget(win.characters_add_btn)
    btn_row.addWidget(win.characters_dup_btn)
    btn_row.addWidget(win.characters_del_btn)
    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    win.character_name_edit = QLineEdit()
    win.character_name_edit.setPlaceholderText("Name")
    win.character_name_edit.setMaximumHeight(26)
    lbl_name = QLabel("Name")
    lbl_name.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(lbl_name)
    lay.addWidget(win.character_name_edit)

    lbl_id = QLabel("Identity / persona (script + on-screen)")
    lbl_id.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(lbl_id)
    win.character_identity_edit = QTextEdit()
    win.character_identity_edit.setMinimumHeight(48)
    win.character_identity_edit.setMaximumHeight(96)
    win.character_identity_edit.setPlaceholderText("Who is this host? Tone, channel, audience…")
    win.character_identity_edit.setAcceptRichText(False)
    win.character_identity_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    lay.addWidget(wrap_editor_with_brain(win.character_identity_edit, "Identity / persona (script + on-screen)", win))

    lbl_vis = QLabel("Visual style (prepended to image prompts)")
    lbl_vis.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(lbl_vis)
    win.character_visual_edit = QTextEdit()
    win.character_visual_edit.setMinimumHeight(40)
    win.character_visual_edit.setMaximumHeight(80)
    win.character_visual_edit.setPlaceholderText("e.g. neon cyberpunk studio, warm key light, mascot host…")
    win.character_visual_edit.setAcceptRichText(False)
    win.character_visual_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    lay.addWidget(wrap_editor_with_brain(win.character_visual_edit, "Visual style (image prompts)", win))

    lbl_neg = QLabel("Extra negatives for diffusion (comma phrases)")
    lbl_neg.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(lbl_neg)
    win.character_negatives_edit = QTextEdit()
    win.character_negatives_edit.setMaximumHeight(48)
    win.character_negatives_edit.setPlaceholderText("e.g. extra fingers, watermark")
    win.character_negatives_edit.setAcceptRichText(False)
    win.character_negatives_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    lay.addWidget(wrap_editor_with_brain(win.character_negatives_edit, "Extra negatives for diffusion", win))

    win.character_default_voice_chk = QCheckBox("Use project default voice (Settings → Voice model)")
    win.character_default_voice_chk.setChecked(True)
    win.character_default_voice_chk.setStyleSheet("font-size: 11px;")
    lay.addWidget(win.character_default_voice_chk)

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
    win.character_voice_refresh_btn.setMaximumHeight(28)
    win.character_voice_refresh_btn.setToolTip("Refresh pyttsx3 voice list")
    vrow.addWidget(win.character_voice_refresh_btn)
    lay.addLayout(vrow)

    lbl_ko = QLabel("Kokoro speaker (optional)")
    lbl_ko.setStyleSheet("color: #B7B7C2; font-size: 11px;")
    lay.addWidget(lbl_ko)
    win.character_kokoro_edit = QLineEdit()
    win.character_kokoro_edit.setPlaceholderText("When Kokoro path is enabled in settings")
    win.character_kokoro_edit.setMaximumHeight(26)
    lay.addWidget(win.character_kokoro_edit)

    win.character_el_container = QWidget()
    el_outer = QVBoxLayout(win.character_el_container)
    el_outer.setContentsMargins(0, 0, 0, 0)
    el_outer.setSpacing(2)
    win.character_el_hint = QLabel(
        "ElevenLabs: API tab + key (or ELEVENLABS_API_KEY). Used when default voice is off."
    )
    win.character_el_hint.setWordWrap(True)
    win.character_el_hint.setStyleSheet("color: #8A96A3; font-size: 10px;")
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
    win.character_el_refresh_btn.setMaximumHeight(28)
    win.character_el_refresh_btn.setToolTip("Refresh ElevenLabs voice list")
    el_row.addWidget(win.character_el_refresh_btn)
    el_outer.addLayout(el_row)
    lay.addWidget(win.character_el_container)

    save_row = QHBoxLayout()
    win.characters_save_btn = QPushButton("Save character")
    win.characters_save_btn.setObjectName("primary")
    win.characters_save_btn.setMaximumHeight(32)
    save_row.addWidget(win.characters_save_btn)
    save_row.addStretch(1)
    lay.addLayout(save_row)

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
        dup = Character(
            id=dup.id,
            name=dup.name,
            identity=ch.identity,
            visual_style=ch.visual_style,
            negatives=ch.negatives,
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

    _fill_voice_combo(win.character_voice_combo, "")
    _update_el_visibility()
    win._characters_refresh_elevenlabs = _update_el_visibility  # main_window calls when switching to Characters tab

    _refresh_list()
    if win.characters_list.count():
        win.characters_list.setCurrentRow(0)
        _on_select()

    win.tabs.addTab(w, "Characters")
