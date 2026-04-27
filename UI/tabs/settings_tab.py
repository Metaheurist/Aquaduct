from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from src.core.models_dir import models_dir_for_app

from src.models.hardware import (
    fit_marker_display,
    get_hardware_info,
    list_cuda_gpus,
    rate_model_fit_for_repo,
    rank_models_for_auto_fit,
    vram_requirement_hint,
)
from src.models.quantization import (
    mode_label,
    parse_vram_hint_gb,
    predict_vram_gb,
    supported_quant_modes,
)
from src.util.cuda_device_policy import effective_vram_gb_for_kind
from src.models.model_integrity_cache import worst_integrity_status
from src.models.model_tiers import TIER_LITE, TIER_PRO, TIER_STANDARD, tier_label
from src.models.model_manager import (
    best_model_size_label,
    load_hf_size_cache,
    local_model_size_label,
    model_has_local_snapshot,
    model_options,
)
from UI.dialogs.frameless_dialog import aquaduct_information
from UI.widgets.model_execution_toggle import ModelExecutionModeToggle
from UI.widgets.models_storage_toggle import ModelsStorageModeToggle
from UI.widgets.no_wheel_controls import NoWheelComboBox
from UI.widgets.tab_sections import add_section_spacing, section_title
from UI.help.tutorial_links import help_tooltip_rich
from UI.workers import ModelSizePingWorker


def _vram_label_style() -> str:
    return "color:#9BB0C4;font-size:12px;padding:4px 4px;"


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

    title_row = QHBoxLayout()
    header = QLabel("Model (dependencies + model downloads)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    title_row.addWidget(header)
    title_row.addStretch(1)
    win.model_execution_mode_combo = ModelExecutionModeToggle()
    _mem = str(getattr(win.settings, "model_execution_mode", "local") or "local").strip().lower()
    win.model_execution_mode_combo.setCurrentIndex(1 if _mem == "api" else 0)
    title_row.addWidget(win.model_execution_mode_combo)
    lay.addLayout(title_row)

    actions_row = QHBoxLayout()
    actions_row.setSpacing(10)

    win.dl_menu_btn = QPushButton("Download")
    win.dl_menu_btn.setObjectName("primary")
    dl_menu = QMenu(win.dl_menu_btn)
    _a = QAction("Download script model", win)
    _a.triggered.connect(lambda: win._download_selected("script"))
    dl_menu.addAction(_a)
    _a = QAction("Download image model", win)
    _a.triggered.connect(lambda: win._download_selected("image"))
    dl_menu.addAction(_a)
    _a = QAction("Download video model", win)
    _a.triggered.connect(lambda: win._download_selected("video"))
    dl_menu.addAction(_a)
    _a = QAction("Download voice model", win)
    _a.triggered.connect(lambda: win._download_selected("voice"))
    dl_menu.addAction(_a)
    _a = QAction("Download all voice models", win)
    _a.setToolTip(
        "Queue Hugging Face snapshots for every curated TTS repo (Kokoro, MOSS-VoiceGenerator). "
        "Skips folders already under models/."
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
    win.clear_data_btn.setToolTip(
        "Wipe settings, cache, and project outputs. Removes default models under .Aquaduct_data/models; "
        "does not delete an external models folder."
    )
    win.clear_data_btn.setObjectName("danger")
    win.clear_data_btn.clicked.connect(win._clear_all_data)
    actions_row.addWidget(win.clear_data_btn)

    actions_row.addStretch(1)
    lay.addLayout(actions_row)

    add_section_spacing(lay)
    win._model_mode_stack = QStackedWidget()
    lay.addWidget(win._model_mode_stack, 1)

    local_scroll = QScrollArea()
    local_scroll.setObjectName("modelLocalScroll")
    local_scroll.setWidgetResizable(True)
    local_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    local_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    local_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    local_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    local_scroll.setStyleSheet(
        "QScrollArea#modelLocalScroll { background: transparent; border: none; }"
        "QScrollArea#modelLocalScroll > QWidget > QWidget { background: transparent; }"
    )
    local_page = QWidget()
    ll = QVBoxLayout(local_page)
    ll.setContentsMargins(0, 0, 10, 0)
    ll.setSpacing(8)
    win._local_model_shell = local_page

    ll.addWidget(section_title("Models (select + download)", emphasis=True))

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
    ll.addWidget(win._settings_hf_banner)

    win._hub_status_lbl = QLabel("Checking Hugging Face for each model (sizes + availability)…")
    win._hub_status_lbl.setStyleSheet("color:#9BB0C4;font-size:12px;padding:0 0 8px 0;")
    win._hub_status_lbl.setWordWrap(True)
    ll.addWidget(win._hub_status_lbl)

    win._model_fit_policy_hint = QLabel(
        "Fit badges use the same GPU policy and effective VRAM per role as the My PC tab (set Auto vs Single there)."
    )
    win._model_fit_policy_hint.setWordWrap(True)
    win._model_fit_policy_hint.setStyleSheet("color:#7A8A9A;font-size:12px;padding:0 0 8px 0;")
    ll.addWidget(win._model_fit_policy_hint)

    win._model_opts = model_options()
    win._model_opt_by_repo = {o.repo_id: o for o in win._model_opts}
    win._hw_info = get_hardware_info()
    win._hf_size_cache_path = win.paths.cache_dir / "hf_model_sizes.json"
    win._hf_remote_sizes = load_hf_size_cache(Path(win._hf_size_cache_path))
    win._hf_probe: dict[str, dict] = {}

    win.llm_combo = NoWheelComboBox()
    win.img_combo = NoWheelComboBox()
    win.vid_combo = NoWheelComboBox()
    win.voice_combo = NoWheelComboBox()

    win.llm_quant_combo = NoWheelComboBox()
    win.img_quant_combo = NoWheelComboBox()
    win.vid_quant_combo = NoWheelComboBox()
    win.voice_quant_combo = NoWheelComboBox()

    def _prep_combo(combo: QComboBox) -> None:
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumWidth(220)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(26)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        combo.view().setMinimumWidth(480)

    def _fill_quant_combo(combo: QComboBox, *, role: str, repo_id: str) -> None:
        # Block signals while repopulating to avoid re-entering ``_update_fit_badges``
        # via ``currentIndexChanged`` (clear/addItem fire that signal).
        was_blocked = combo.signalsBlocked()
        combo.blockSignals(True)
        try:
            combo.clear()
            for opt in supported_quant_modes(role=role, repo_id=repo_id):
                combo.addItem(opt.label, opt.mode)
                i = combo.count() - 1
                if not opt.enabled:
                    try:
                        m = combo.model()
                        midx = m.index(i, 0)
                        m.setData(midx, 0, Qt.ItemDataRole.EnabledRole)
                    except Exception:
                        pass
                if opt.tooltip:
                    combo.setItemData(i, opt.tooltip, Qt.ItemDataRole.ToolTipRole)
            # Wide enough for full labels (e.g. ``NF4 4-bit (lowest VRAM)``), but not enough
            # to force the card wider than a 1080p tab.
            combo.setMinimumWidth(180)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            combo.setMinimumContentsLength(22)
        finally:
            combo.blockSignals(was_blocked)

    def _required_repos_for_option(opt, kind: str) -> list[str]:
        if kind == "video" and getattr(opt, "pair_image_repo_id", ""):
            return [str(opt.pair_image_repo_id).strip(), str(opt.repo_id).strip()]
        return [str(opt.repo_id).strip()]

    def _option_row_enabled(opt, kind: str) -> tuple[bool, str]:
        if not win._hf_probe:
            return True, ""
        repos = _required_repos_for_option(opt, kind)
        tips: list[str] = []
        models_dir = models_dir_for_app(win.settings)
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

    def _tier_header_item(title: str) -> QStandardItem:
        h = QStandardItem(title)
        h.setEnabled(False)
        h.setSelectable(False)
        hf = QFont()
        hf.setBold(True)
        h.setFont(hf)
        return h

    def fill_combo_model(combo: QComboBox, kind: str) -> None:
        model = QStandardItemModel(combo)
        opts_kind = [o for o in win._model_opts if o.kind == kind]
        per_tier: dict[str, int] = {}
        for tier_key in (TIER_LITE, TIER_STANDARD, TIER_PRO):
            group = [o for o in opts_kind if getattr(o, "tier", TIER_STANDARD) == tier_key]
            if not group:
                continue
            model.appendRow(_tier_header_item(tier_label(tier_key)))
            for opt in sorted(group, key=lambda o: (o.order, o.label.lower())):
                data = opt.repo_id
                sz = best_model_size_label(
                    opt.repo_id,
                    models_dir=models_dir_for_app(win.settings),
                    remote_sizes=win._hf_remote_sizes,
                    size_hint=getattr(opt, "size_hint", ""),
                )
                en, tip = _option_row_enabled(opt, kind)
                per_tier[tier_key] = per_tier.get(tier_key, 0) + 1
                n = per_tier[tier_key]
                text = f"{n:02d}. {opt.label}  [{sz}]"
                item = QStandardItem(text)
                item.setData(data, Qt.ItemDataRole.UserRole)
                t_full = tier_label(getattr(opt, "tier", TIER_STANDARD))
                tip_lines = [opt.label, str(data), f"Tier: {t_full}"]
                if getattr(opt, "size_hint", ""):
                    tip_lines.append(f"Size hint: {opt.size_hint}")
                full_tip = "\n".join(tip_lines)
                if not en and tip:
                    full_tip = tip + "\n\n" + full_tip
                item.setToolTip(full_tip)
                if en:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                model.appendRow(item)
        combo.setModel(model)
        _prep_combo(combo)

    def _refresh_model_combos_keep_selection() -> None:
        llm_data = win.llm_combo.currentData()
        img_data = win.img_combo.currentData()
        vid_data = win.vid_combo.currentData()
        voice_data = win.voice_combo.currentData()

        fill_combo_model(win.llm_combo, "script")
        fill_combo_model(win.img_combo, "image")
        fill_combo_model(win.vid_combo, "video")
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
            i = win.vid_combo.findData(vid_data, role)
            if i >= 0:
                win.vid_combo.setCurrentIndex(i)
            elif vid_data is not None:
                _pick_first_enabled(win.vid_combo)
        except Exception:
            _pick_first_enabled(win.vid_combo)
        try:
            i = win.voice_combo.findData(voice_data, role)
            if i >= 0:
                win.voice_combo.setCurrentIndex(i)
            elif voice_data is not None:
                _pick_first_enabled(win.voice_combo)
        except Exception:
            _pick_first_enabled(win.voice_combo)

        # If restored index points at a disabled row, move to first enabled
        for combo in (win.llm_combo, win.img_combo, win.vid_combo, win.voice_combo):
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
    fill_combo_model(win.img_combo, "image")
    fill_combo_model(win.vid_combo, "video")
    fill_combo_model(win.voice_combo, "voice")

    win.llm_dl_badge = QLabel("")
    win.img_dl_badge = QLabel("")
    win.vid_dl_badge = QLabel("")
    win.voice_dl_badge = QLabel("")
    # Wide enough for one-line "○ Not on disk"; left-aligned so text never paints left of the
    # label rect (centered + narrow width was bleeding over the QComboBox).
    _dl_badge_w = 128
    for _b in (win.llm_dl_badge, win.img_dl_badge, win.vid_dl_badge, win.voice_dl_badge):
        _b.setStyleSheet("color:#5DFFB0;font-size:11px;font-weight:700;padding:0px;")
        _b.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        _b.setWordWrap(False)
        _b.setFixedWidth(_dl_badge_w)
        _b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    if win.settings.llm_model_id:
        idx = _combo_index_for_data(win.llm_combo, win.settings.llm_model_id)
        if idx >= 0:
            win.llm_combo.setCurrentIndex(idx)
    im = str(getattr(win.settings, "image_model_id", "") or "").strip()
    if im:
        idx = _combo_index_for_data(win.img_combo, im)
        if idx >= 0:
            win.img_combo.setCurrentIndex(idx)
    vm = str(getattr(win.settings, "video_model_id", "") or "").strip()
    if vm:
        idx = _combo_index_for_data(win.vid_combo, vm)
        if idx >= 0:
            win.vid_combo.setCurrentIndex(idx)
    if win.settings.voice_model_id:
        idx = _combo_index_for_data(win.voice_combo, win.settings.voice_model_id)
        if idx >= 0:
            win.voice_combo.setCurrentIndex(idx)

    # Required VRAM (typical; heuristic) between combo and fit badge
    win.llm_vram_lbl = QLabel("—")
    win.img_vram_lbl = QLabel("—")
    win.vid_vram_lbl = QLabel("—")
    win.voice_vram_lbl = QLabel("—")
    for _lbl in (win.llm_vram_lbl, win.img_vram_lbl, win.vid_vram_lbl, win.voice_vram_lbl):
        _lbl.setStyleSheet(_vram_label_style())
        _lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _lbl.setWordWrap(False)
        _lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        _lbl.setMaximumWidth(280)
        _lbl.setToolTip("Typical GPU VRAM for this model class (estimate only; CPU fallback may apply).")

    # Fit badges (based on detected hardware)
    win.llm_fit = QLabel("UNKNOWN")
    win.img_fit = QLabel("UNKNOWN")
    win.vid_fit = QLabel("UNKNOWN")
    win.voice_fit = QLabel("UNKNOWN")
    _fit_badge_w = 92
    for _f in (win.llm_fit, win.img_fit, win.vid_fit, win.voice_fit):
        _f.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _f.setFixedWidth(_fit_badge_w)
        _f.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _combo_repo_id_from_selection(combo: QComboBox) -> str:
        idx = combo.currentIndex()
        if idx < 0:
            return ""
        try:
            raw = combo.itemData(idx, Qt.ItemDataRole.UserRole)
        except Exception:
            raw = None
        if raw is None:
            return ""
        s = str(raw).strip()
        if not s or s.lower() == "none":
            return ""
        return s

    def _ensure_model_combo_valid_selection(combo: QComboBox) -> None:
        if _combo_repo_id_from_selection(combo):
            return
        _pick_first_enabled(combo)

    def _update_fit_badges() -> None:
        for c in (win.llm_combo, win.img_combo, win.vid_combo, win.voice_combo):
            _ensure_model_combo_valid_selection(c)
        try:
            gpus_fb = list_cuda_gpus()
            app_fb = win._collect_settings_from_ui() if hasattr(win, "_collect_settings_from_ui") else win.settings
        except Exception:
            gpus_fb = []
            app_fb = win.settings

        def _vram_for_kind(kind: str) -> float | None:
            if gpus_fb:
                v = effective_vram_gb_for_kind(kind, gpus_fb, app_fb)
                if v is not None:
                    return v
            return win._hw_info.vram_gb

        def _dl_badge_base_style() -> str:
            return "font-size:11px;font-weight:700;padding:2px 2px;"

        def set_dl_badge(lbl: QLabel, repos: list[str]) -> None:
            ms = models_dir_for_app(win.settings)
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
            # Must check empty first: len(have) < len(uniq) is True when have is [] and uniq is non-empty,
            # which wrongly showed "Partial" for models that do not exist at all.
            if not have:
                lbl.setText("○ Not on disk")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#9BB0C4;")
                lbl.setToolTip(
                    "No local snapshot under models/ yet (or below minimum size).\n"
                    + "\n".join(f"{r}: not downloaded" for r in uniq)
                )
                return
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
                vram_gb=_vram_for_kind(kind),
                ram_gb=win._hw_info.ram_gb,
            )
            lbl.setText(fit_marker_display(marker))
            lbl.setStyleSheet(_fit_badge_style(marker))
            lbl.setToolTip(why)

        # Repopulating the quant combo clears the widget; if we only restored from
        # ``win.settings`` here, every ``currentIndexChanged`` (including the
        # user's new pick) would snap back. Preserve live ``currentData()`` when
        # the same Hub repo is still selected; use ``AppSettings`` when the model
        # row changes. See win._quant_ui_last_model_repo.
        _last_mrepo = getattr(win, "_quant_ui_last_model_repo", None)
        if not isinstance(_last_mrepo, dict):
            _last_mrepo = {"script": None, "image": None, "video": None, "voice": None}

        def _refill_and_restore_quant(
            combo: QComboBox,
            *,
            rkey: str,
            repo: str,
            settings_attr: str,
            fill_role: str,
        ) -> None:
            prev = _last_mrepo.get(rkey)
            prev_s = (str(prev) if prev is not None else "").strip()
            r = (repo or "").strip()
            if prev_s == r and r:
                preserve = str(combo.currentData() or "").strip()
            else:
                preserve = ""
            _fill_quant_combo(combo, role=fill_role, repo_id=repo)
            want = preserve
            if not want or combo.findData(want) < 0:
                want = str(getattr(win.settings, settings_attr, "auto") or "auto")
            if combo.findData(want) < 0:
                want = "auto"
            ix = combo.findData(want)
            if ix < 0 and combo.count() > 0:
                ix = 0
            was_blk = combo.signalsBlocked()
            combo.blockSignals(True)
            try:
                if ix >= 0:
                    combo.setCurrentIndex(ix)
            finally:
                combo.blockSignals(was_blk)
            _last_mrepo[rkey] = repo

        llm_repo = _combo_repo_id_from_selection(win.llm_combo)
        _refill_and_restore_quant(
            win.llm_quant_combo,
            rkey="script",
            repo=llm_repo,
            settings_attr="script_quant_mode",
            fill_role="script",
        )
        llm_opt = win._model_opt_by_repo.get(llm_repo) if llm_repo else None
        llm_spd = llm_opt.speed if llm_opt else "slow"
        if llm_repo:
            _vh = vram_requirement_hint(kind="script", repo_id=llm_repo, speed=llm_spd)
            lo, hi = parse_vram_hint_gb(_vh)
            qm = str(win.llm_quant_combo.currentData() or "auto")
            pv = predict_vram_gb(role="script", repo_id=llm_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.llm_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.llm_vram_lbl.setToolTip(pv.rationale)
        else:
            win.llm_vram_lbl.setText("—")
        if llm_repo:
            set_badge(win.llm_fit, kind="script", repo_id=llm_repo)
            set_dl_badge(win.llm_dl_badge, [llm_repo])
        else:
            win.llm_fit.setText("—")
            win.llm_dl_badge.setText("")

        img_repo = _combo_repo_id_from_selection(win.img_combo)
        _refill_and_restore_quant(
            win.img_quant_combo,
            rkey="image",
            repo=img_repo,
            settings_attr="image_quant_mode",
            fill_role="image",
        )
        img_opt = win._model_opt_by_repo.get(img_repo) if img_repo else None
        img_spd = img_opt.speed if img_opt else "slow"
        if img_repo:
            _vh = vram_requirement_hint(kind="image", repo_id=img_repo, speed=img_spd)
            lo, hi = parse_vram_hint_gb(_vh)
            qm = str(win.img_quant_combo.currentData() or "auto")
            pv = predict_vram_gb(role="image", repo_id=img_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.img_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.img_vram_lbl.setToolTip(pv.rationale)
        else:
            win.img_vram_lbl.setText("—")
        if img_repo:
            set_badge(win.img_fit, kind="image", repo_id=img_repo)
            set_dl_badge(win.img_dl_badge, [img_repo])
        else:
            win.img_fit.setText("—")
            win.img_dl_badge.setText("")

        vid_repo = _combo_repo_id_from_selection(win.vid_combo)
        _refill_and_restore_quant(
            win.vid_quant_combo,
            rkey="video",
            repo=vid_repo,
            settings_attr="video_quant_mode",
            fill_role="video",
        )
        vid_opt = win._model_opt_by_repo.get(vid_repo) if vid_repo else None
        vid_spd = vid_opt.speed if vid_opt else "slow"
        pair_id = str(getattr(vid_opt, "pair_image_repo_id", "") or "").strip() if vid_opt else ""
        if vid_repo:
            _vh = vram_requirement_hint(kind="video", repo_id=vid_repo, speed=vid_spd, pair_image_repo_id=pair_id)
            lo, hi = parse_vram_hint_gb(_vh)
            qm = str(win.vid_quant_combo.currentData() or "auto")
            pv = predict_vram_gb(role="video", repo_id=vid_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.vid_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.vid_vram_lbl.setToolTip(pv.rationale)
        else:
            win.vid_vram_lbl.setText("—")
        if vid_repo:
            set_badge(win.vid_fit, kind="video", repo_id=str(vid_repo), pair_image_repo_id=pair_id)
            set_dl_badge(win.vid_dl_badge, [vid_repo])
        else:
            win.vid_fit.setText("—")
            win.vid_dl_badge.setText("")

        voice_repo = _combo_repo_id_from_selection(win.voice_combo)
        _refill_and_restore_quant(
            win.voice_quant_combo,
            rkey="voice",
            repo=voice_repo,
            settings_attr="voice_quant_mode",
            fill_role="voice",
        )
        win._quant_ui_last_model_repo = _last_mrepo
        voice_opt = win._model_opt_by_repo.get(voice_repo) if voice_repo else None
        voice_spd = voice_opt.speed if voice_opt else "slow"
        if voice_repo:
            _vh = vram_requirement_hint(kind="voice", repo_id=voice_repo, speed=voice_spd)
            lo, hi = parse_vram_hint_gb(_vh)
            qm = str(win.voice_quant_combo.currentData() or "auto")
            pv = predict_vram_gb(role="voice", repo_id=voice_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.voice_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.voice_vram_lbl.setToolTip(pv.rationale)
        else:
            win.voice_vram_lbl.setText("—")
        if voice_repo:
            set_badge(win.voice_fit, kind="voice", repo_id=voice_repo)
            set_dl_badge(win.voice_dl_badge, [voice_repo])
        else:
            win.voice_fit.setText("—")
            win.voice_dl_badge.setText("")

    def _sync_local_model_combo_tooltip(combo: QComboBox) -> None:
        idx = combo.currentIndex()
        if idx < 0:
            combo.setToolTip(combo.currentText() or "")
            return
        midx = combo.model().index(idx, 0)
        t = midx.data(Qt.ItemDataRole.ToolTipRole)
        if t is not None and str(t).strip():
            combo.setToolTip(str(t))
        else:
            combo.setToolTip(combo.currentText() or "")

    win.llm_combo.currentIndexChanged.connect(_update_fit_badges)
    win.img_combo.currentIndexChanged.connect(_update_fit_badges)
    win.vid_combo.currentIndexChanged.connect(_update_fit_badges)
    win.voice_combo.currentIndexChanged.connect(_update_fit_badges)
    win.llm_quant_combo.currentIndexChanged.connect(_update_fit_badges)
    win.img_quant_combo.currentIndexChanged.connect(_update_fit_badges)
    win.vid_quant_combo.currentIndexChanged.connect(_update_fit_badges)
    win.voice_quant_combo.currentIndexChanged.connect(_update_fit_badges)
    win.llm_combo.currentIndexChanged.connect(lambda: _sync_local_model_combo_tooltip(win.llm_combo))
    win.img_combo.currentIndexChanged.connect(lambda: _sync_local_model_combo_tooltip(win.img_combo))
    win.vid_combo.currentIndexChanged.connect(lambda: _sync_local_model_combo_tooltip(win.vid_combo))
    win.voice_combo.currentIndexChanged.connect(lambda: _sync_local_model_combo_tooltip(win.voice_combo))

    def _disk_status_panel(dl_b: QLabel) -> QFrame:
        disk_frame = QFrame()
        disk_frame.setObjectName("ModelDiskStatusPanel")
        disk_frame.setFrameShape(QFrame.Shape.StyledPanel)
        fr = QHBoxLayout(disk_frame)
        fr.setContentsMargins(6, 3, 6, 3)
        fr.setSpacing(0)
        fr.addWidget(dl_b, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        fr.addStretch(1)
        disk_frame.setMinimumWidth(int(_dl_badge_w) + 12)
        disk_frame.setMaximumWidth(int(_dl_badge_w) + 12)
        disk_frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        disk_frame.setStyleSheet(
            "QFrame#ModelDiskStatusPanel {"
            " background-color: rgba(60, 72, 86, 0.55);"
            " border: 1px solid rgba(120, 135, 150, 0.65);"
            " border-radius: 4px;"
            "}"
        )
        return disk_frame

    def _model_role_card(
        title: str,
        combo: QComboBox,
        dl_b: QLabel,
        qcombo: QComboBox,
        vram_l: QLabel,
        fit_l: QLabel,
    ) -> QFrame:
        """Responsive role block: title/fit, full-width model, metadata, full-width quant."""
        card = QFrame()
        card.setObjectName("ModelRoleCard")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame#ModelRoleCard {"
            " background-color: rgba(255, 255, 255, 0.025);"
            " border: 1px solid rgba(120, 135, 150, 0.32);"
            " border-radius: 10px;"
            "}"
        )
        lay_card = QVBoxLayout(card)
        lay_card.setContentsMargins(10, 8, 10, 8)
        lay_card.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_l = QLabel(title)
        title_l.setStyleSheet("font-weight:700;color:#E8E8EE;")
        title_l.setWordWrap(False)
        title_row.addWidget(title_l, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(fit_l, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay_card.addLayout(title_row)

        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay_card.addWidget(combo)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)
        meta_row.addWidget(_disk_status_panel(dl_b), 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        meta_row.addStretch(1)
        vram_l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        meta_row.addWidget(vram_l, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay_card.addLayout(meta_row)

        qcombo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        qcombo.setMinimumWidth(180)
        lay_card.addWidget(qcombo)
        return card

    _model_rows: list[tuple[str, QComboBox, QLabel, QComboBox, QLabel, QLabel]] = [
        ("Script model (LLM)", win.llm_combo, win.llm_dl_badge, win.llm_quant_combo, win.llm_vram_lbl, win.llm_fit),
        ("Image model (diffusion stills)", win.img_combo, win.img_dl_badge, win.img_quant_combo, win.img_vram_lbl, win.img_fit),
        ("Video model (motion / Pro / scenes)", win.vid_combo, win.vid_dl_badge, win.vid_quant_combo, win.vid_vram_lbl, win.vid_fit),
        ("Voice model (TTS)", win.voice_combo, win.voice_dl_badge, win.voice_quant_combo, win.voice_vram_lbl, win.voice_fit),
    ]
    for _txt, combo, dl_b, qcombo, vram_l, fit_l in _model_rows:
        ll.addWidget(_model_role_card(_txt, combo, dl_b, qcombo, vram_l, fit_l))

    auto_fit_row = QHBoxLayout()
    win.auto_fit_models_btn = QPushButton("Auto-fit for this PC")
    win.auto_fit_models_btn.setObjectName("primary")
    win.auto_fit_models_btn.setToolTip(
        help_tooltip_rich(
            "Re-detect GPU/RAM and select the best script, image, video, and voice models for this machine "
            "(same heuristics as the fit badges). Skips grayed-out entries that are unavailable on Hugging Face.",
            "models",
            slide=0,
        )
    )
    auto_fit_row.addWidget(win.auto_fit_models_btn)
    auto_fit_row.addStretch(1)
    ll.addLayout(auto_fit_row)

    def _auto_fit_models() -> None:
        try:
            win._hw_info = get_hardware_info()
        except Exception:
            pass
        try:
            app_af = win._collect_settings_from_ui() if hasattr(win, "_collect_settings_from_ui") else win.settings
        except Exception:
            app_af = win.settings
        ranked = rank_models_for_auto_fit(win._model_opts, win._hw_info, app_settings=app_af)
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
        ok_i = _combo_set_best(win.img_combo, ranked.image_repo_ids)
        ok_v = _combo_set_best(win.vid_combo, ranked.video_repo_ids)
        ok_c = _combo_set_best(win.voice_combo, ranked.voice_repo_ids)

        # Apply matching quant mode defaults (best effort).
        try:
            if ranked.script_quant_modes:
                q = ranked.script_quant_modes[win.llm_combo.currentIndex()] if win.llm_combo.currentIndex() >= 0 else ""
                ix = win.llm_quant_combo.findData(q, role)
                if ix >= 0:
                    win.llm_quant_combo.setCurrentIndex(ix)
            if ranked.image_quant_modes:
                q = ranked.image_quant_modes[win.img_combo.currentIndex()] if win.img_combo.currentIndex() >= 0 else ""
                ix = win.img_quant_combo.findData(q, role)
                if ix >= 0:
                    win.img_quant_combo.setCurrentIndex(ix)
            if ranked.video_quant_modes:
                q = ranked.video_quant_modes[win.vid_combo.currentIndex()] if win.vid_combo.currentIndex() >= 0 else ""
                ix = win.vid_quant_combo.findData(q, role)
                if ix >= 0:
                    win.vid_quant_combo.setCurrentIndex(ix)
            if ranked.voice_quant_modes:
                q = ranked.voice_quant_modes[win.voice_combo.currentIndex()] if win.voice_combo.currentIndex() >= 0 else ""
                ix = win.voice_quant_combo.findData(q, role)
                if ix >= 0:
                    win.voice_quant_combo.setCurrentIndex(ix)
        except Exception:
            pass
        # Match ``win.settings`` to the combo rows we just set so ``_update_fit_badges`` does
        # not re-apply stale quant modes from before Auto-fit (``AppSettings`` is immutable).
        try:
            if hasattr(win, "_collect_settings_from_ui"):
                win.settings = win._collect_settings_from_ui()
        except Exception:
            pass
        _update_fit_badges()
        if hasattr(win, "_append_log"):
            win._append_log(ranked.log_summary)
            try:
                from src.models.inference_profiles import format_inference_profile_report

                for line in format_inference_profile_report(app_af).splitlines():
                    win._append_log(f"[Aquaduct][inference_profile] {line}")
            except Exception:
                pass
            if not (ok_s and ok_i and ok_v and ok_c):
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

    add_section_spacing(ll)
    storage_title = QHBoxLayout()
    storage_title.addWidget(section_title("Model files location", emphasis=True))
    storage_title.addStretch(1)
    win.models_storage_mode_combo = ModelsStorageModeToggle()
    _msm = str(getattr(win.settings, "models_storage_mode", "default") or "default").strip().lower()
    win.models_storage_mode_combo.setCurrentIndex(1 if _msm == "external" else 0)
    storage_title.addWidget(win.models_storage_mode_combo)
    ll.addLayout(storage_title)

    win.models_external_path_edit = QLineEdit()
    win.models_external_path_edit.setPlaceholderText("Absolute path to folder for Hugging Face model snapshots…")
    win.models_external_browse_btn = QPushButton("Browse…")
    win.models_external_apply_btn = QPushButton("Apply")
    win.models_external_apply_btn.setObjectName("primary")
    win.models_external_apply_btn.setToolTip("Save path and storage mode to settings.")
    win.models_external_detect_btn = QPushButton("Detect")
    win.models_external_detect_btn.setToolTip("List model snapshots found under the resolved folder (uses path field when External).")
    win.models_external_path_edit.setText(str(getattr(win.settings, "models_external_path", "") or ""))

    ext_row = QHBoxLayout()
    ext_row.addWidget(win.models_external_path_edit, 1)
    ext_row.addWidget(win.models_external_browse_btn, 0)
    ext_row.addWidget(win.models_external_apply_btn, 0)
    ext_row.addWidget(win.models_external_detect_btn, 0)
    ll.addLayout(ext_row)

    storage_hint = QLabel(
        "Default uses the project folder .Aquaduct_data/models. External uses another folder for downloads and loading weights — Apply saves the path."
    )
    storage_hint.setWordWrap(True)
    storage_hint.setStyleSheet("color:#8A8A96;font-size:11px;padding:0 0 4px 0;")
    ll.addWidget(storage_hint)

    def _apply_models_storage_ui() -> None:
        ext = str(win.models_storage_mode_combo.currentData() or "default") == "external"
        win.models_external_path_edit.setVisible(ext)
        win.models_external_browse_btn.setVisible(ext)
        win.models_external_apply_btn.setVisible(ext)
        win.models_external_detect_btn.setVisible(ext)

    def _browse_models_dir() -> None:
        start = win.models_external_path_edit.text().strip() or str(win.paths.data_dir)
        d = QFileDialog.getExistingDirectory(win, "Select models folder", start)
        if d:
            win.models_external_path_edit.setText(d)

    def _apply_models_storage_path() -> None:
        if hasattr(win, "_save_settings"):
            win._save_settings()
        if hasattr(win, "_refresh_settings_model_combos"):
            win._refresh_settings_model_combos()

    def _detect_models_in_folder() -> None:
        from dataclasses import replace

        mode = str(win.models_storage_mode_combo.currentData() or "default")
        raw = win.models_external_path_edit.text().strip()
        app = replace(win.settings, models_storage_mode=mode, models_external_path=raw)  # type: ignore[arg-type]
        md = models_dir_for_app(app)
        from src.models.model_manager import list_installed_repo_ids_from_disk

        ids = list_installed_repo_ids_from_disk(md)
        preview = "\n".join(ids[:50]) + ("\n…" if len(ids) > 50 else "")
        aquaduct_information(
            win,
            "Detect models",
            f"Resolved folder:\n{md}\n\nFound {len(ids)} model snapshot(s) on disk:\n\n{preview or '(none)'}",
        )

    def _on_models_storage_mode_changed(_i: int = 0) -> None:
        _apply_models_storage_ui()
        if hasattr(win, "_save_settings"):
            win._save_settings()
        if hasattr(win, "_refresh_settings_model_combos"):
            win._refresh_settings_model_combos()

    win.models_external_browse_btn.clicked.connect(_browse_models_dir)
    win.models_external_apply_btn.clicked.connect(_apply_models_storage_path)
    win.models_external_detect_btn.clicked.connect(_detect_models_in_folder)
    win.models_storage_mode_combo.currentIndexChanged.connect(_on_models_storage_mode_changed)
    _apply_models_storage_ui()

    _update_fit_badges()
    _sync_local_model_combo_tooltip(win.llm_combo)
    _sync_local_model_combo_tooltip(win.img_combo)
    _sync_local_model_combo_tooltip(win.vid_combo)
    _sync_local_model_combo_tooltip(win.voice_combo)

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
    win._update_model_fit_badges = _update_fit_badges

    api_page = QWidget()
    al = QVBoxLayout(api_page)
    api_hint = QLabel(
        "API mode runs script, stills, and (optionally) voice via cloud APIs — no local diffusion weights. "
        "Configure providers and keys in the panel below (same controls appear on the API tab). "
        "FFmpeg still runs locally for assembly."
    )
    api_hint.setWordWrap(True)
    api_hint.setStyleSheet("color:#B7B7C2;font-size:12px;")
    al.addWidget(api_hint, 0)

    scroll = QScrollArea()
    scroll.setObjectName("modelApiGenScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    scroll.setMinimumHeight(260)
    scroll.setStyleSheet(
        "QScrollArea#modelApiGenScroll { background: transparent; border: none; }"
        "QScrollArea#modelApiGenScroll > QWidget > QWidget { background: transparent; }"
    )
    inner = QWidget()
    inner.setObjectName("modelApiGenScrollInner")
    win._model_api_gen_layout = QVBoxLayout(inner)
    win._model_api_gen_layout.setContentsMargins(0, 0, 8, 0)
    win._model_api_gen_layout.setSpacing(0)
    scroll.setWidget(inner)
    al.addWidget(scroll, 1)
    win._model_api_gen_scroll = scroll

    local_scroll.setWidget(local_page)
    win._model_local_scroll = local_scroll
    win._model_mode_stack.addWidget(local_scroll)
    win._model_mode_stack.addWidget(api_page)

    def _apply_model_execution_ui() -> None:
        api = str(win.model_execution_mode_combo.currentData() or "local") == "api"
        win._model_mode_stack.setCurrentIndex(1 if api else 0)
        win.dl_menu_btn.setVisible(not api)
        win.auto_fit_models_btn.setVisible(not api)
        win._hub_status_lbl.setVisible(not api)
        win._settings_hf_banner.setVisible(not api and not hf_on)
        if hasattr(win, "_sync_generation_api_panel_parent"):
            try:
                win._sync_generation_api_panel_parent()
            except Exception:
                pass
        if hasattr(win, "_sync_api_gen_row_states"):
            try:
                win._sync_api_gen_row_states()
            except Exception:
                pass
        if hasattr(win, "_resize_to_current_tab"):
            QTimer.singleShot(0, win._resize_to_current_tab)

    win._apply_model_execution_ui = _apply_model_execution_ui
    win.model_execution_mode_combo.currentIndexChanged.connect(lambda _i: _apply_model_execution_ui())
    _apply_model_execution_ui()

    win.tabs.addTab(w, "Model")
