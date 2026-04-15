from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.model_manager import model_options


def attach_settings_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("Settings (dependencies + model downloads)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    dep_row = QHBoxLayout()
    win.check_deps_btn = QPushButton("Check Python dependencies")
    win.check_deps_btn.clicked.connect(win._check_deps)
    dep_row.addWidget(win.check_deps_btn)

    win.install_deps_btn = QPushButton("Install missing dependencies")
    win.install_deps_btn.setObjectName("primary")
    win.install_deps_btn.clicked.connect(win._install_deps)
    dep_row.addWidget(win.install_deps_btn)
    dep_row.addStretch(1)
    lay.addLayout(dep_row)

    win.deps_status = QPlainTextEdit()
    win.deps_status.setReadOnly(True)
    win.deps_status.setPlaceholderText("Dependency status will appear here…")
    lay.addWidget(win.deps_status, 1)

    mheader = QLabel("Models (select + download)")
    mheader.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 10px;")
    lay.addWidget(mheader)

    win._model_opts = model_options()

    form = QFormLayout()
    win.llm_combo = QComboBox()
    win.img_combo = QComboBox()
    win.voice_combo = QComboBox()

    def fill(combo: QComboBox, kind: str) -> None:
        combo.clear()
        for opt in [o for o in win._model_opts if o.kind == kind]:
            combo.addItem(f"{opt.label}  [{opt.speed}]", opt.repo_id)

    fill(win.llm_combo, "script")
    fill(win.img_combo, "video")
    fill(win.voice_combo, "voice")

    if win.settings.llm_model_id:
        idx = win.llm_combo.findData(win.settings.llm_model_id)
        if idx >= 0:
            win.llm_combo.setCurrentIndex(idx)
    if win.settings.image_model_id:
        idx = win.img_combo.findData(win.settings.image_model_id)
        if idx >= 0:
            win.img_combo.setCurrentIndex(idx)
    if win.settings.voice_model_id:
        idx = win.voice_combo.findData(win.settings.voice_model_id)
        if idx >= 0:
            win.voice_combo.setCurrentIndex(idx)

    form.addRow("Script model (LLM)", win.llm_combo)
    form.addRow("Video/images model", win.img_combo)
    form.addRow("Voice model (TTS)", win.voice_combo)
    lay.addLayout(form)

    dl_row = QHBoxLayout()
    win.dl_script_btn = QPushButton("Download script model")
    win.dl_script_btn.clicked.connect(lambda: win._download_selected("script"))
    dl_row.addWidget(win.dl_script_btn)

    win.dl_video_btn = QPushButton("Download video model")
    win.dl_video_btn.clicked.connect(lambda: win._download_selected("video"))
    dl_row.addWidget(win.dl_video_btn)

    win.dl_voice_btn = QPushButton("Download voice model")
    win.dl_voice_btn.clicked.connect(lambda: win._download_selected("voice"))
    dl_row.addWidget(win.dl_voice_btn)

    win.dl_all_btn = QPushButton("Download all selected")
    win.dl_all_btn.setObjectName("primary")
    win.dl_all_btn.clicked.connect(win._download_all_selected)
    dl_row.addWidget(win.dl_all_btn)
    dl_row.addStretch(1)
    lay.addLayout(dl_row)

    win.tabs.addTab(w, "Settings")
