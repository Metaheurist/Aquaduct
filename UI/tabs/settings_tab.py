from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.hardware import get_hardware_info, rate_model_fit
from src.model_manager import model_options


def _fit_badge_style(marker: str) -> str:
    m = (marker or "").upper().strip()
    if m == "EXCELLENT":
        return "background:#12381F;color:#CFFFE0;border:1px solid #1B5A2F;border-radius:8px;padding:4px 8px;font-weight:700;"
    if m == "OK":
        return "background:#0F2F45;color:#D7F1FF;border:1px solid #1A4D6F;border-radius:8px;padding:4px 8px;font-weight:700;"
    if m == "RISKY":
        return "background:#3C2D12;color:#FFE7C2;border:1px solid #6D4E16;border-radius:8px;padding:4px 8px;font-weight:700;"
    if m == "NO_GPU":
        return "background:#3B1414;color:#FFD2D2;border:1px solid #6B1C1C;border-radius:8px;padding:4px 8px;font-weight:700;"
    return "background:#2A2A2F;color:#E6E6F0;border:1px solid #3A3A44;border-radius:8px;padding:4px 8px;font-weight:700;"


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

    mheader = QLabel("Models (select + download)")
    mheader.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 10px;")
    lay.addWidget(mheader)

    win._model_opts = model_options()
    win._model_opt_by_repo = {o.repo_id: o for o in win._model_opts}
    win._hw_info = get_hardware_info()

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    win.llm_combo = QComboBox()
    win.img_combo = QComboBox()
    win.voice_combo = QComboBox()

    def _prep_combo(combo: QComboBox) -> None:
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, combo.sizePolicy().verticalPolicy())
        combo.setMinimumWidth(560)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(28)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        # Ensure the popup is wide enough to read
        combo.view().setMinimumWidth(720)

    def fill(combo: QComboBox, kind: str) -> None:
        combo.clear()
        for opt in [o for o in win._model_opts if o.kind == kind]:
            data = (opt.pair_image_repo_id, opt.repo_id) if (kind == "video" and getattr(opt, "pair_image_repo_id", "")) else opt.repo_id
            combo.addItem(f"{opt.order:02d}. {opt.label}  [{opt.speed}]", data)

    fill(win.llm_combo, "script")
    fill(win.img_combo, "video")
    fill(win.voice_combo, "voice")
    _prep_combo(win.llm_combo)
    _prep_combo(win.img_combo)
    _prep_combo(win.voice_combo)

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

    # Fit badges (based on detected hardware)
    win.llm_fit = QLabel("UNKNOWN")
    win.img_fit = QLabel("UNKNOWN")
    win.voice_fit = QLabel("UNKNOWN")

    def _update_fit_badges() -> None:
        def set_badge(lbl: QLabel, *, kind: str, repo_id: str) -> None:
            opt = win._model_opt_by_repo.get(repo_id)
            speed = opt.speed if opt else "slow"
            marker, why = rate_model_fit(
                kind=kind,
                speed=speed,
                vram_gb=win._hw_info.vram_gb,
                ram_gb=win._hw_info.ram_gb,
            )
            lbl.setText(marker)
            lbl.setStyleSheet(_fit_badge_style(marker))
            lbl.setToolTip(why)

        set_badge(win.llm_fit, kind="script", repo_id=str(win.llm_combo.currentData()))
        img_data = win.img_combo.currentData()
        vid_repo = img_data[1] if isinstance(img_data, tuple) and len(img_data) == 2 else str(img_data)
        set_badge(win.img_fit, kind="video", repo_id=str(vid_repo))
        set_badge(win.voice_fit, kind="voice", repo_id=str(win.voice_combo.currentData()))

    win.llm_combo.currentIndexChanged.connect(_update_fit_badges)
    win.img_combo.currentIndexChanged.connect(_update_fit_badges)
    win.voice_combo.currentIndexChanged.connect(_update_fit_badges)
    win.llm_combo.currentIndexChanged.connect(lambda: win.llm_combo.setToolTip(win.llm_combo.currentText()))
    win.img_combo.currentIndexChanged.connect(lambda: win.img_combo.setToolTip(win.img_combo.currentText()))
    win.voice_combo.currentIndexChanged.connect(lambda: win.voice_combo.setToolTip(win.voice_combo.currentText()))

    llm_row = QHBoxLayout()
    llm_row.addWidget(win.llm_combo, 1)
    llm_row.addWidget(win.llm_fit, 0)
    img_row = QHBoxLayout()
    img_row.addWidget(win.img_combo, 1)
    img_row.addWidget(win.img_fit, 0)
    voice_row = QHBoxLayout()
    voice_row.addWidget(win.voice_combo, 1)
    voice_row.addWidget(win.voice_fit, 0)

    form.addRow("Script model (LLM)", llm_row)
    form.addRow("Video/images model", img_row)
    form.addRow("Voice model (TTS)", voice_row)
    lay.addLayout(form)
    _update_fit_badges()
    win.llm_combo.setToolTip(win.llm_combo.currentText())
    win.img_combo.setToolTip(win.img_combo.currentText())
    win.voice_combo.setToolTip(win.voice_combo.currentText())

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

    win.dl_everything_btn = QPushButton("Download ALL models")
    win.dl_everything_btn.clicked.connect(win._download_all_models)
    dl_row.addWidget(win.dl_everything_btn)
    dl_row.addStretch(1)
    lay.addLayout(dl_row)

    win.tabs.addTab(w, "Settings")
