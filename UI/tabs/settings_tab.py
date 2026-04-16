from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from src.hardware import get_hardware_info, rate_model_fit_for_repo, vram_requirement_hint
from src.model_manager import model_options


def _vram_label_style() -> str:
    return "color:#9BB0C4;font-size:12px;padding:0 10px;min-width:7.5em;"


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
    form.setVerticalSpacing(10)
    form.setHorizontalSpacing(14)
    win.llm_combo = QComboBox()
    win.img_combo = QComboBox()
    win.voice_combo = QComboBox()

    def _prep_combo(combo: QComboBox) -> None:
        combo.setSizePolicy(QSizePolicy.Policy.Preferred, combo.sizePolicy().verticalPolicy())
        combo.setMinimumWidth(300)
        combo.setMaximumWidth(700)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(28)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        combo.view().setMinimumWidth(480)

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

    # Required VRAM (typical; heuristic) between combo and fit badge
    win.llm_vram_lbl = QLabel("—")
    win.img_vram_lbl = QLabel("—")
    win.voice_vram_lbl = QLabel("—")
    for _lbl in (win.llm_vram_lbl, win.img_vram_lbl, win.voice_vram_lbl):
        _lbl.setStyleSheet(_vram_label_style())
        _lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _lbl.setWordWrap(False)
        _lbl.setToolTip("Typical GPU VRAM for this model class (estimate only; CPU fallback may apply).")

    # Fit badges (based on detected hardware)
    win.llm_fit = QLabel("UNKNOWN")
    win.img_fit = QLabel("UNKNOWN")
    win.voice_fit = QLabel("UNKNOWN")

    def _update_fit_badges() -> None:
        def set_badge(lbl: QLabel, *, kind: str, repo_id: str, pair_image_repo_id: str = "") -> None:
            opt = win._model_opt_by_repo.get(repo_id)
            speed = opt.speed if opt else "slow"
            marker, why = rate_model_fit_for_repo(
                kind=kind,
                speed=speed,
                repo_id=repo_id,
                pair_image_repo_id=pair_image_repo_id,
                vram_gb=win._hw_info.vram_gb,
                ram_gb=win._hw_info.ram_gb,
            )
            lbl.setText(marker)
            lbl.setStyleSheet(_fit_badge_style(marker))
            lbl.setToolTip(why)

        llm_repo = str(win.llm_combo.currentData())
        llm_opt = win._model_opt_by_repo.get(llm_repo)
        llm_spd = llm_opt.speed if llm_opt else "slow"
        win.llm_vram_lbl.setText(vram_requirement_hint(kind="script", repo_id=llm_repo, speed=llm_spd))
        set_badge(win.llm_fit, kind="script", repo_id=llm_repo)

        img_data = win.img_combo.currentData()
        if isinstance(img_data, tuple) and len(img_data) == 2:
            pair_id, vid_repo = str(img_data[0]), str(img_data[1])
        else:
            pair_id, vid_repo = "", str(img_data)
        vid_opt = win._model_opt_by_repo.get(vid_repo)
        vid_spd = vid_opt.speed if vid_opt else "slow"
        if not pair_id and vid_opt and getattr(vid_opt, "pair_image_repo_id", ""):
            pair_id = str(vid_opt.pair_image_repo_id)
        win.img_vram_lbl.setText(
            vram_requirement_hint(kind="video", repo_id=vid_repo, speed=vid_spd, pair_image_repo_id=pair_id)
        )
        set_badge(win.img_fit, kind="video", repo_id=str(vid_repo), pair_image_repo_id=pair_id)

        voice_repo = str(win.voice_combo.currentData())
        voice_opt = win._model_opt_by_repo.get(voice_repo)
        voice_spd = voice_opt.speed if voice_opt else "slow"
        win.voice_vram_lbl.setText(vram_requirement_hint(kind="voice", repo_id=voice_repo, speed=voice_spd))
        set_badge(win.voice_fit, kind="voice", repo_id=voice_repo)

    win.llm_combo.currentIndexChanged.connect(_update_fit_badges)
    win.img_combo.currentIndexChanged.connect(_update_fit_badges)
    win.voice_combo.currentIndexChanged.connect(_update_fit_badges)
    win.llm_combo.currentIndexChanged.connect(lambda: win.llm_combo.setToolTip(win.llm_combo.currentText()))
    win.img_combo.currentIndexChanged.connect(lambda: win.img_combo.setToolTip(win.img_combo.currentText()))
    win.voice_combo.currentIndexChanged.connect(lambda: win.voice_combo.setToolTip(win.voice_combo.currentText()))

    llm_row = QHBoxLayout()
    llm_row.addWidget(win.llm_combo, 1)
    llm_row.addWidget(win.llm_vram_lbl, 0)
    llm_row.addWidget(win.llm_fit, 0)
    img_row = QHBoxLayout()
    img_row.addWidget(win.img_combo, 1)
    img_row.addWidget(win.img_vram_lbl, 0)
    img_row.addWidget(win.img_fit, 0)
    voice_row = QHBoxLayout()
    voice_row.addWidget(win.voice_combo, 1)
    voice_row.addWidget(win.voice_vram_lbl, 0)
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

    danger_header = QLabel("Danger zone")
    danger_header.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 12px;")
    lay.addWidget(danger_header)

    danger_row = QHBoxLayout()
    win.clear_data_btn = QPushButton("Clear data")
    win.clear_data_btn.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
    win.clear_data_btn.setToolTip("Wipe settings, downloaded models, and cache.")
    win.clear_data_btn.setObjectName("danger")
    win.clear_data_btn.clicked.connect(win._clear_all_data)
    danger_row.addWidget(win.clear_data_btn)
    danger_row.addStretch(1)
    lay.addLayout(danger_row)

    win.tabs.addTab(w, "Settings")
