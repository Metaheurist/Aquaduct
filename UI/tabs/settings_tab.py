from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QMenu
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

from src.hardware import get_hardware_info, rate_model_fit_for_repo, rank_models_for_auto_fit, vram_requirement_hint
from src.model_integrity_cache import worst_integrity_status
from src.model_manager import (
    best_model_size_label,
    load_hf_size_cache,
    local_model_size_label,
    model_has_local_snapshot,
    model_options,
)
from UI.workers import ModelSizePingWorker


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

    header = QLabel("Model (dependencies + model downloads)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    actions_row = QHBoxLayout()
    actions_row.setSpacing(10)

    win.dl_menu_btn = QPushButton("Download")
    win.dl_menu_btn.setObjectName("primary")
    dl_menu = QMenu(win.dl_menu_btn)
    _a = QAction("Download script model", win)
    _a.triggered.connect(lambda: win._download_selected("script"))
    dl_menu.addAction(_a)
    _a = QAction("Download video model", win)
    _a.triggered.connect(lambda: win._download_selected("video"))
    dl_menu.addAction(_a)
    _a = QAction("Download voice model", win)
    _a.triggered.connect(lambda: win._download_selected("voice"))
    dl_menu.addAction(_a)
    _a = QAction("Download all voice models", win)
    _a.setToolTip(
        "Queue Hugging Face snapshots for every curated TTS repo (Kokoro, MMS-TTS, MeloTTS, "
        "Microsoft SpeechT5, Parler-TTS, XTTS, Bark, …). Skips folders already under models/."
    )
    _a.triggered.connect(win._download_all_voice_models)
    dl_menu.addAction(_a)
    dl_menu.addSeparator()
    _a = QAction("Download all selected", win)
    _a.triggered.connect(win._download_all_selected)
    dl_menu.addAction(_a)
    _a = QAction("Download ALL models", win)
    _a.triggered.connect(win._download_all_models)
    dl_menu.addAction(_a)
    dl_menu.addSeparator()
    _a = QAction("Import models from folder", win)
    _a.setToolTip("Select a folder containing model directories to import curated models from.")
    _a.triggered.connect(win._import_models_from_folder)
    dl_menu.addAction(_a)
    dl_menu.addSeparator()
    _a = QAction("Verify checksums — selected models (on disk)", win)
    _a.setToolTip(
        "Compare local files to Hugging Face Hub (SHA-256 for LFS weights, git blob ids for small files). "
        "Needs internet. Large models can take several minutes."
    )
    _a.triggered.connect(win._verify_models_checksums_selected)
    dl_menu.addAction(_a)
    _a = QAction("Verify checksums — all folders in models/", win)
    _a.setToolTip("Same as above, for every model-sized folder under models/.")
    _a.triggered.connect(win._verify_models_checksums_all)
    dl_menu.addAction(_a)
    dl_menu.addSeparator()
    _a = QAction("Check Python dependencies", win)
    _a.triggered.connect(win._check_deps)
    dl_menu.addAction(_a)
    win.dl_menu_btn.setMenu(dl_menu)
    actions_row.addWidget(win.dl_menu_btn)

    win.install_deps_btn = QPushButton("Install dependencies")
    win.install_deps_btn.setObjectName("primary")
    win.install_deps_btn.setToolTip(
        "Install PyTorch for this PC (CUDA if an NVIDIA GPU is detected, else CPU; macOS uses PyPI), "
        "then pip install -r requirements.txt — same as: python scripts/install_pytorch.py --with-rest"
    )
    win.install_deps_btn.clicked.connect(win._install_deps)
    actions_row.addWidget(win.install_deps_btn)

    win.clear_data_btn = QPushButton("Clear data")
    win.clear_data_btn.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
    win.clear_data_btn.setToolTip("Wipe settings, downloaded models, and cache.")
    win.clear_data_btn.setObjectName("danger")
    win.clear_data_btn.clicked.connect(win._clear_all_data)
    actions_row.addWidget(win.clear_data_btn)

    actions_row.addStretch(1)
    lay.addLayout(actions_row)

    mheader = QLabel("Models (select + download)")
    mheader.setStyleSheet("font-size: 14px; font-weight: 700; margin-top: 10px;")
    lay.addWidget(mheader)

    win._settings_hf_banner = QLabel(
        "Hugging Face token use is off: remote size checks and gated model downloads may fail or be rate-limited. "
        "Enable it under the API tab."
    )
    win._settings_hf_banner.setWordWrap(True)
    win._settings_hf_banner.setStyleSheet(
        "color: #E8C080; background-color: rgba(255, 160, 72, 0.10); "
        "padding: 8px 10px; border-radius: 8px; border: 1px solid rgba(255, 190, 120, 0.25); font-size: 12px;"
    )
    hf_on = bool(getattr(win.settings, "hf_api_enabled", True))
    win._settings_hf_banner.setVisible(not hf_on)
    lay.addWidget(win._settings_hf_banner)

    win._hub_status_lbl = QLabel("Checking Hugging Face for each model (sizes + availability)…")
    win._hub_status_lbl.setStyleSheet("color:#9BB0C4;font-size:12px;padding:0 0 8px 0;")
    win._hub_status_lbl.setWordWrap(True)
    lay.addWidget(win._hub_status_lbl)

    win._model_opts = model_options()
    win._model_opt_by_repo = {o.repo_id: o for o in win._model_opts}
    win._hw_info = get_hardware_info()
    win._hf_size_cache_path = win.paths.cache_dir / "hf_model_sizes.json"
    win._hf_remote_sizes = load_hf_size_cache(Path(win._hf_size_cache_path))
    win._hf_probe: dict[str, dict] = {}

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

    def _required_repos_for_option(opt, kind: str) -> list[str]:
        if kind == "video" and getattr(opt, "pair_image_repo_id", ""):
            return [str(opt.pair_image_repo_id).strip(), str(opt.repo_id).strip()]
        return [str(opt.repo_id).strip()]

    def _option_row_enabled(opt, kind: str) -> tuple[bool, str]:
        if not win._hf_probe:
            return True, ""
        repos = _required_repos_for_option(opt, kind)
        tips: list[str] = []
        models_dir = win.paths.models_dir
        for r in repos:
            if model_has_local_snapshot(r, models_dir=models_dir):
                continue
            pr = win._hf_probe.get(r)
            if pr is None:
                return True, ""
            if pr.get("ok"):
                continue
            err = (pr.get("error") or "Unavailable on Hugging Face").strip()
            short = r.split("/")[-1] if "/" in r else r
            tips.append(f"{short}: {err}")
        if tips:
            return False, "Not available from Hugging Face (and no local copy detected):\n" + "\n".join(tips)
        return True, ""

    def _combo_index_for_data(combo: QComboBox, data) -> int:
        role = Qt.ItemDataRole.UserRole
        for i in range(combo.count()):
            if combo.itemData(i, role) == data:
                return int(i)
        return -1

    def _pick_first_enabled(combo: QComboBox) -> None:
        m = combo.model()
        for i in range(combo.count()):
            midx = m.index(i, 0)
            try:
                if midx.flags() & Qt.ItemFlag.ItemIsEnabled:
                    combo.setCurrentIndex(i)
                    return
            except Exception:
                continue

    def fill_combo_model(combo: QComboBox, kind: str) -> None:
        model = QStandardItemModel(combo)
        for opt in [o for o in win._model_opts if o.kind == kind]:
            data = (
                (opt.pair_image_repo_id, opt.repo_id)
                if (kind == "video" and getattr(opt, "pair_image_repo_id", ""))
                else opt.repo_id
            )
            if kind == "video" and getattr(opt, "pair_image_repo_id", ""):
                vid_sz = best_model_size_label(
                    opt.repo_id,
                    models_dir=win.paths.models_dir,
                    remote_sizes=win._hf_remote_sizes,
                    size_hint=getattr(opt, "size_hint", ""),
                )
                img_sz = best_model_size_label(
                    opt.pair_image_repo_id,
                    models_dir=win.paths.models_dir,
                    remote_sizes=win._hf_remote_sizes,
                    size_hint="≈6–8GB",
                )
                sz = f"{img_sz}+{vid_sz}"
            else:
                sz = best_model_size_label(
                    opt.repo_id,
                    models_dir=win.paths.models_dir,
                    remote_sizes=win._hf_remote_sizes,
                    size_hint=getattr(opt, "size_hint", ""),
                )
            en, tip = _option_row_enabled(opt, kind)
            text = f"{opt.order:02d}. {opt.label}  [{sz} • {opt.speed}]"
            item = QStandardItem(text)
            item.setData(data, Qt.ItemDataRole.UserRole)
            if en:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(tip)
            model.appendRow(item)
        combo.setModel(model)
        _prep_combo(combo)

    def _refresh_model_combos_keep_selection() -> None:
        llm_data = win.llm_combo.currentData()
        img_data = win.img_combo.currentData()
        voice_data = win.voice_combo.currentData()

        fill_combo_model(win.llm_combo, "script")
        fill_combo_model(win.img_combo, "video")
        fill_combo_model(win.voice_combo, "voice")

        role = Qt.ItemDataRole.UserRole
        try:
            i = win.llm_combo.findData(llm_data, role)
            if i >= 0:
                win.llm_combo.setCurrentIndex(i)
            elif llm_data is not None:
                _pick_first_enabled(win.llm_combo)
        except Exception:
            _pick_first_enabled(win.llm_combo)
        try:
            i = win.img_combo.findData(img_data, role)
            if i >= 0:
                win.img_combo.setCurrentIndex(i)
            elif img_data is not None:
                _pick_first_enabled(win.img_combo)
        except Exception:
            _pick_first_enabled(win.img_combo)
        try:
            i = win.voice_combo.findData(voice_data, role)
            if i >= 0:
                win.voice_combo.setCurrentIndex(i)
            elif voice_data is not None:
                _pick_first_enabled(win.voice_combo)
        except Exception:
            _pick_first_enabled(win.voice_combo)

        # If restored index points at a disabled row, move to first enabled
        for combo in (win.llm_combo, win.img_combo, win.voice_combo):
            idx = combo.currentIndex()
            if idx < 0:
                _pick_first_enabled(combo)
                continue
            try:
                midx = combo.model().index(idx, 0)
                if not (midx.flags() & Qt.ItemFlag.ItemIsEnabled):
                    _pick_first_enabled(combo)
            except Exception:
                pass

    fill_combo_model(win.llm_combo, "script")
    fill_combo_model(win.img_combo, "video")
    fill_combo_model(win.voice_combo, "voice")

    win.llm_dl_badge = QLabel("")
    win.img_dl_badge = QLabel("")
    win.voice_dl_badge = QLabel("")
    for _b in (win.llm_dl_badge, win.img_dl_badge, win.voice_dl_badge):
        _b.setStyleSheet("color:#5DFFB0;font-size:12px;font-weight:700;min-width:8.5em;")
        _b.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    if win.settings.llm_model_id:
        idx = _combo_index_for_data(win.llm_combo, win.settings.llm_model_id)
        if idx >= 0:
            win.llm_combo.setCurrentIndex(idx)
    vm = str(getattr(win.settings, "video_model_id", "") or "").strip()
    im = str(getattr(win.settings, "image_model_id", "") or "").strip()
    if im:
        idx = _combo_index_for_data(win.img_combo, (im, vm)) if vm else -1
        if idx < 0:
            idx = _combo_index_for_data(win.img_combo, im)
        if idx >= 0:
            win.img_combo.setCurrentIndex(idx)
    if win.settings.voice_model_id:
        idx = _combo_index_for_data(win.voice_combo, win.settings.voice_model_id)
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
        def _dl_badge_base_style() -> str:
            return "font-size:12px;font-weight:700;min-width:8.5em;"

        def set_dl_badge(lbl: QLabel, repos: list[str]) -> None:
            ms = win.paths.models_dir
            cache = getattr(win, "_model_integrity_by_repo", {}) or {}
            uniq: list[str] = []
            seen: set[str] = set()
            for x in repos:
                r = str(x).strip()
                if not r or r in seen:
                    continue
                seen.add(r)
                uniq.append(r)
            if not uniq:
                lbl.setText("")
                lbl.setToolTip("")
                return

            def sizes_tooltip() -> str:
                return " · ".join(f"{r}: {local_model_size_label(r, models_dir=ms)}" for r in uniq)

            have = [r for r in uniq if model_has_local_snapshot(r, models_dir=ms)]
            if len(have) < len(uniq):
                lbl.setText("◐ Partial")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#6EC8FF;")
                lbl.setToolTip(
                    "Some weights on disk; others missing.\n"
                    + "\n".join(
                        f"{r}: {local_model_size_label(r, models_dir=ms)}"
                        if model_has_local_snapshot(r, models_dir=ms)
                        else f"{r}: not downloaded"
                        for r in uniq
                    )
                )
                return
            if not have:
                lbl.setText("")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#9BB0C4;")
                lbl.setToolTip("No local copy detected under models/ yet.")
                return

            integ = [cache.get(r) for r in uniq]
            known = [s for s in integ if s is not None]
            unknown_repos = [uniq[i] for i, s in enumerate(integ) if s is None]

            if not known:
                lbl.setText("✓ On disk")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#5DFFB0;")
                lbl.setToolTip(
                    f"Downloaded in models/: {sizes_tooltip()}\n\n"
                    "Checksum status unknown — use Download → Verify checksums to confirm files."
                )
                return

            bad_known = [s for s in known if str(s) != "ok"]
            if bad_known:
                w = worst_integrity_status(bad_known)
                tips = {
                    "missing": "Reported files are missing locally (incomplete download or wrong tree). Re-download if needed.",
                    "corrupt": "Checksum mismatch — one or more files are wrong or damaged. Re-download this model.",
                    "missing_and_corrupt": "Missing files and checksum failures. Re-download the affected model.",
                    "error": "Verification failed (offline, auth, gated repo, or Hub error). Retry when online.",
                }
                labels = {
                    "missing": "✗ Missing files",
                    "corrupt": "✗ Corrupt",
                    "missing_and_corrupt": "✗ Missing & corrupt",
                    "error": "⚠ Verify error",
                }
                colors = {
                    "missing": "#FFB0A0",
                    "corrupt": "#FF7B7B",
                    "missing_and_corrupt": "#FF9088",
                    "error": "#E8C080",
                }
                lbl.setText(labels.get(w, "✗ Issue"))
                lbl.setStyleSheet(_dl_badge_base_style() + f"color:{colors.get(w, '#FFB0A0')};")
                extra = ""
                if unknown_repos:
                    extra = f"\n\nNot verified yet: {', '.join(unknown_repos)}."
                lbl.setToolTip(f"{tips.get(w, '')}\n\n{sizes_tooltip()}{extra}")
                return

            if unknown_repos:
                lbl.setText("✓ On disk")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#5DFFB0;")
                ok_rs = [uniq[i] for i, s in enumerate(integ) if s == "ok"]
                lbl.setToolTip(
                    f"Checksum OK for: {', '.join(ok_rs)}.\n"
                    f"Not verified yet: {', '.join(unknown_repos)}.\n\n{sizes_tooltip()}"
                )
                return

            lbl.setText("✓ Verified")
            lbl.setStyleSheet(_dl_badge_base_style() + "color:#5DFFB0;")
            lbl.setToolTip("Local files matched Hugging Face checksums.\n\n" + sizes_tooltip())

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
        set_dl_badge(win.llm_dl_badge, [llm_repo])

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
        img_repos = [pair_id, vid_repo] if pair_id and vid_repo else [vid_repo]
        set_dl_badge(win.img_dl_badge, img_repos)

        voice_repo = str(win.voice_combo.currentData())
        voice_opt = win._model_opt_by_repo.get(voice_repo)
        voice_spd = voice_opt.speed if voice_opt else "slow"
        win.voice_vram_lbl.setText(vram_requirement_hint(kind="voice", repo_id=voice_repo, speed=voice_spd))
        set_badge(win.voice_fit, kind="voice", repo_id=voice_repo)
        set_dl_badge(win.voice_dl_badge, [voice_repo])

    win.llm_combo.currentIndexChanged.connect(_update_fit_badges)
    win.img_combo.currentIndexChanged.connect(_update_fit_badges)
    win.voice_combo.currentIndexChanged.connect(_update_fit_badges)
    win.llm_combo.currentIndexChanged.connect(lambda: win.llm_combo.setToolTip(win.llm_combo.currentText()))
    win.img_combo.currentIndexChanged.connect(lambda: win.img_combo.setToolTip(win.img_combo.currentText()))
    win.voice_combo.currentIndexChanged.connect(lambda: win.voice_combo.setToolTip(win.voice_combo.currentText()))

    llm_row = QHBoxLayout()
    llm_row.addWidget(win.llm_combo, 1)
    llm_row.addWidget(win.llm_dl_badge, 0)
    llm_row.addWidget(win.llm_vram_lbl, 0)
    llm_row.addWidget(win.llm_fit, 0)
    img_row = QHBoxLayout()
    img_row.addWidget(win.img_combo, 1)
    img_row.addWidget(win.img_dl_badge, 0)
    img_row.addWidget(win.img_vram_lbl, 0)
    img_row.addWidget(win.img_fit, 0)
    voice_row = QHBoxLayout()
    voice_row.addWidget(win.voice_combo, 1)
    voice_row.addWidget(win.voice_dl_badge, 0)
    voice_row.addWidget(win.voice_vram_lbl, 0)
    voice_row.addWidget(win.voice_fit, 0)

    form.addRow("Script model (LLM)", llm_row)
    form.addRow("Video/images model", img_row)
    form.addRow("Voice model (TTS)", voice_row)
    lay.addLayout(form)

    auto_fit_row = QHBoxLayout()
    win.auto_fit_models_btn = QPushButton("Auto-fit for this PC")
    win.auto_fit_models_btn.setObjectName("primary")
    win.auto_fit_models_btn.setToolTip(
        "Re-detect GPU/RAM and select the best script, video, and voice models for this machine "
        "(same heuristics as the fit badges). Skips grayed-out entries that are unavailable on Hugging Face."
    )
    auto_fit_row.addWidget(win.auto_fit_models_btn)
    auto_fit_row.addStretch(1)
    lay.addLayout(auto_fit_row)

    def _auto_fit_models() -> None:
        try:
            win._hw_info = get_hardware_info()
        except Exception:
            pass
        ranked = rank_models_for_auto_fit(win._model_opts, win._hw_info)
        role = Qt.ItemDataRole.UserRole

        def _combo_set_best(combo: QComboBox, candidates: tuple[str | tuple[str, str], ...]) -> bool:
            for data in candidates:
                i = combo.findData(data, role)
                if i < 0:
                    continue
                try:
                    midx = combo.model().index(i, 0)
                    if midx.flags() & Qt.ItemFlag.ItemIsEnabled:
                        combo.setCurrentIndex(i)
                        return True
                except Exception:
                    continue
            return False

        ok_s = _combo_set_best(win.llm_combo, ranked.script_repo_ids)
        ok_v = _combo_set_best(win.img_combo, ranked.video_combo_values)
        ok_c = _combo_set_best(win.voice_combo, ranked.voice_repo_ids)
        _update_fit_badges()
        if hasattr(win, "_append_log"):
            win._append_log(ranked.log_summary)
            if not (ok_s and ok_v and ok_c):
                win._append_log(
                    "Auto-fit: one or more preferred models are disabled (Hub check). "
                    "Try again when online, download weights to models/, or pick manually."
                )
        if hasattr(win, "_save_settings"):
            try:
                win._save_settings()
            except Exception:
                pass

    win.auto_fit_models_btn.clicked.connect(_auto_fit_models)
    win._auto_fit_models = _auto_fit_models

    _update_fit_badges()
    win.llm_combo.setToolTip(win.llm_combo.currentText())
    win.img_combo.setToolTip(win.img_combo.currentText())
    win.voice_combo.setToolTip(win.voice_combo.currentText())

    # Ping HF for remote sizes on startup (auth via HF_TOKEN / cached login).
    # This runs in the background and refreshes labels when complete.
    try:
        repo_ids = []
        seen = set()
        for opt in win._model_opts:
            for rid in (opt.repo_id, getattr(opt, "pair_image_repo_id", "")):
                rid = str(rid or "").strip()
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                repo_ids.append(rid)

        win._size_ping_worker = ModelSizePingWorker(repo_ids=repo_ids, cache_path=win._hf_size_cache_path)

        def _on_hub_probe_done(probe: dict) -> None:
            try:
                win._hf_probe = dict(probe or {})
                for rid, info in (probe or {}).items():
                    if isinstance(info, dict) and info.get("ok") and info.get("bytes") is not None:
                        win._hf_remote_sizes[str(rid)] = int(info["bytes"])
                bad = sum(1 for v in (probe or {}).values() if isinstance(v, dict) and not v.get("ok"))
                win._hub_status_lbl.setText(
                    f"Hub check done. Precise sizes updated. "
                    f"Unavailable entries ({bad}) are grayed unless you already have them under models/."
                )
                _refresh_model_combos_keep_selection()
                _update_fit_badges()
            except Exception:
                pass

        def _on_hub_probe_failed(_err: str) -> None:
            win._hub_status_lbl.setText("Could not finish Hugging Face check (offline?). Sizes may be estimates only.")

        win._size_ping_worker.done.connect(_on_hub_probe_done)
        win._size_ping_worker.failed.connect(_on_hub_probe_failed)
        win._size_ping_worker.start()
    except Exception:
        pass

    def _refresh_settings_model_combos() -> None:
        _refresh_model_combos_keep_selection()
        _update_fit_badges()

    win._refresh_settings_model_combos = _refresh_settings_model_combos

    win.tabs.addTab(w, "Model")
