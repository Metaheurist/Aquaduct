from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from src.core.config import get_models
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
    index_of_manual_mode,
    manual_quant_modes_low_to_high,
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
from UI.widgets.no_wheel_controls import NoWheelComboBox, NoWheelSlider, QuantAccentSlider
from UI.widgets.tab_sections import add_section_spacing, section_title
from UI.help.tutorial_links import help_tooltip_rich, help_tooltip_rich_unless_already
from UI.workers import ModelSizePingWorker


def _vram_label_style() -> str:
    return "color:#9BB0C4;font-size:12px;padding:4px 4px;"


def _models_help_tip(body: str, *, slide: int = 0) -> str:
    t = (body or "").strip()
    if not t:
        t = "See Help for models & storage."
    return help_tooltip_rich_unless_already(t, "models", slide=slide)


def _my_pc_help_tip(body: str) -> str:
    t = (body or "").strip()
    if not t:
        t = "See Help for hardware fit guidance."
    return help_tooltip_rich(t, "my_pc", slide=0)


def _api_help_tip(body: str, *, slide: int = 1) -> str:
    return help_tooltip_rich((body or "API generation - see Help.").strip(), "api_social", slide=slide)


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
    header = QLabel("Models - pick weights and downloads")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    title_row.addWidget(header)
    title_row.addStretch(1)
    win.model_execution_mode_combo = ModelExecutionModeToggle()
    _mem = str(getattr(win.settings, "model_execution_mode", "local") or "local").strip().lower()
    win.model_execution_mode_combo.setCurrentIndex(1 if _mem == "api" else 0)
    win.model_execution_mode_combo.setToolTip(
        help_tooltip_rich(
            "Local - Hugging Face weights on this PC (downloads, verify checksums, Auto-fit, VRAM fit badges).\n\n"
            "API - cloud script, stills, and voice; configure providers in the panel below (same as the API tab).\n\n"
            "Fit badges use the same GPU policy and effective VRAM per role as the My PC tab.",
            "models",
            slide=1,
        )
    )
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
        _models_help_tip(
            "Queue Hugging Face snapshots for every curated TTS repo (Kokoro, MOSS-VoiceGenerator). "
            "Skips folders already under models/.",
            slide=2,
        )
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
    _a.setToolTip(
        _models_help_tip("Select a folder containing model directories to import curated models from.", slide=2)
    )
    _a.triggered.connect(win._import_models_from_folder)
    dl_menu.addAction(_a)
    dl_menu.addSeparator()
    _a = QAction("Verify checksums - selected models (on disk)", win)
    _a.setToolTip(
        _models_help_tip(
            "Compare local files to Hugging Face Hub (SHA-256 for LFS weights, git blob ids for small files). "
            "Needs internet. Large models can take several minutes.",
            slide=2,
        )
    )
    _a.triggered.connect(win._verify_models_checksums_selected)
    dl_menu.addAction(_a)
    _a = QAction("Verify checksums - all folders in models/", win)
    _a.setToolTip(_models_help_tip("Same as above, for every model-sized folder under models/.", slide=2))
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
        _models_help_tip(
            "Install PyTorch for this PC (CUDA if an NVIDIA GPU is detected, else CPU; macOS uses PyPI), "
            "then pip install -r requirements.txt - same as: python scripts/install_pytorch.py --with-rest",
            slide=2,
        )
    )
    win.install_deps_btn.clicked.connect(win._install_deps)
    actions_row.addWidget(win.install_deps_btn)

    win.clear_data_btn = QPushButton("Clear data")
    win.clear_data_btn.setIcon(win.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
    win.clear_data_btn.setToolTip(
        _models_help_tip(
            "Wipe settings, cache, and project outputs. Removes default models under .Aquaduct_data/models; "
            "does not delete an external models folder.",
            slide=2,
        )
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
        "Green/amber fit badges use VRAM from My PC (Auto picks a card vs pinning one GPU)."
    )
    win._model_fit_policy_hint.setWordWrap(True)
    win._model_fit_policy_hint.setStyleSheet("color:#7A8A9A;font-size:12px;padding:0 0 8px 0;")
    ll.addWidget(win._model_fit_policy_hint)

    win.auto_quant_downgrade_on_failure_chk = QCheckBox(
        "If a local run fails, try one step lower quality and retry (auto-save)"
    )
    win.auto_quant_downgrade_on_failure_chk.setChecked(
        bool(getattr(win.settings, "auto_quant_downgrade_on_failure", False))
    )
    win.auto_quant_downgrade_on_failure_chk.setStyleSheet("color:#E8EEF5;font-size:12px;padding:0 0 10px 0;")
    win.auto_quant_downgrade_on_failure_chk.setToolTip(
        help_tooltip_rich(
            "When enabled, if a **local** pipeline stage fails (including errors other than VRAM OOM), "
            "Aquaduct lowers **Script / Image / Video / Voice** quantization by one step (same ordering as "
            "the manual slider on this tab), saves **ui_settings.json**, and retries. "
            "VRAM OOM still prefers switching to a larger or equal VRAM GPU when possible, then lowers quant. "
            "If every quantization level still fails, you get a message suggesting a different model.",
            "models",
            slide=0,
        )
    )
    ll.addWidget(win.auto_quant_downgrade_on_failure_chk)

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

    win._quant_manual_modes: dict[str, tuple[str, ...]] = {}

    win.llm_quant_auto_chk = QCheckBox("Automatic (fit this GPU)")
    win.img_quant_auto_chk = QCheckBox("Automatic (fit this GPU)")
    win.vid_quant_auto_chk = QCheckBox("Automatic (fit this GPU)")
    win.voice_quant_auto_chk = QCheckBox("Automatic (fit this GPU)")

    win.llm_quant_slider = QuantAccentSlider(Qt.Orientation.Horizontal)
    win.img_quant_slider = QuantAccentSlider(Qt.Orientation.Horizontal)
    win.vid_quant_slider = QuantAccentSlider(Qt.Orientation.Horizontal)
    win.voice_quant_slider = QuantAccentSlider(Qt.Orientation.Horizontal)

    win.llm_quant_value_lbl = QLabel("")
    win.img_quant_value_lbl = QLabel("")
    win.vid_quant_value_lbl = QLabel("")
    win.voice_quant_value_lbl = QLabel("")
    for _ql in (win.llm_quant_value_lbl, win.img_quant_value_lbl, win.vid_quant_value_lbl, win.voice_quant_value_lbl):
        _ql.setStyleSheet("color:#C8D4E0;font-size:12px;")
        _ql.setMinimumWidth(200)
        _ql.setWordWrap(False)

    def _prep_combo(combo: QComboBox) -> None:
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumWidth(220)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(26)
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

    def _append_saved_repo_row(combo: QComboBox, repo_id: str) -> None:
        """Append a selectable row so Hub ids from ui_settings.json appear even when not curated."""
        rid = (repo_id or "").strip()
        if not rid or _combo_index_for_data(combo, rid) >= 0:
            return
        m = combo.model()
        if not isinstance(m, QStandardItemModel):
            return
        item = QStandardItem(f"● Saved repo  [{rid}]")
        item.setData(rid, Qt.ItemDataRole.UserRole)
        item.setToolTip(
            _models_help_tip(
                "This repo id is stored in ui_settings.json but is not in the curated Model list.\n" + rid,
                slide=0,
            )
        )
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        m.appendRow(item)

    def _apply_saved_model_combo(combo: QComboBox, saved_id: str, *, default_repo: str) -> None:
        """Select curated row for saved id, or default when blank; append row for unknown ids."""
        rid = (saved_id or "").strip()
        pick = rid or (default_repo or "").strip()
        if not pick:
            _pick_first_enabled(combo)
            return
        idx = _combo_index_for_data(combo, pick)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            return
        _append_saved_repo_row(combo, pick)
        combo.setCurrentIndex(max(0, combo.count() - 1))

    def _restore_combo_after_fill(combo: QComboBox, prev_data, *, default_repo: str) -> None:
        """After rebuilding combo models (e.g. HF probe refresh), restore selection incl. non-curated ids."""
        if prev_data is None:
            _apply_saved_model_combo(combo, "", default_repo=default_repo)
            return
        sid = str(prev_data).strip()
        if not sid:
            _apply_saved_model_combo(combo, "", default_repo=default_repo)
            return
        idx = _combo_index_for_data(combo, sid)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            return
        _append_saved_repo_row(combo, sid)
        combo.setCurrentIndex(max(0, combo.count() - 1))

    _defaults = get_models()

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
                item.setToolTip(_models_help_tip(full_tip, slide=0))
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

        try:
            _restore_combo_after_fill(win.llm_combo, llm_data, default_repo=_defaults.llm_id)
        except Exception:
            _pick_first_enabled(win.llm_combo)
        try:
            _restore_combo_after_fill(win.img_combo, img_data, default_repo=_defaults.sdxl_turbo_id)
        except Exception:
            _pick_first_enabled(win.img_combo)
        try:
            _restore_combo_after_fill(win.vid_combo, vid_data, default_repo="")
        except Exception:
            _pick_first_enabled(win.vid_combo)
        try:
            _restore_combo_after_fill(win.voice_combo, voice_data, default_repo=_defaults.kokoro_id)
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

    _apply_saved_model_combo(win.llm_combo, win.settings.llm_model_id, default_repo=_defaults.llm_id)
    _apply_saved_model_combo(
        win.img_combo, str(getattr(win.settings, "image_model_id", "") or ""), default_repo=_defaults.sdxl_turbo_id
    )
    _apply_saved_model_combo(
        win.vid_combo, str(getattr(win.settings, "video_model_id", "") or ""), default_repo=""
    )
    _apply_saved_model_combo(win.voice_combo, win.settings.voice_model_id, default_repo=_defaults.kokoro_id)

    # Required VRAM (typical; heuristic) between combo and fit badge
    win.llm_vram_lbl = QLabel("-")
    win.img_vram_lbl = QLabel("-")
    win.vid_vram_lbl = QLabel("-")
    win.voice_vram_lbl = QLabel("-")
    for _lbl in (win.llm_vram_lbl, win.img_vram_lbl, win.vid_vram_lbl, win.voice_vram_lbl):
        _lbl.setStyleSheet(_vram_label_style())
        _lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _lbl.setWordWrap(False)
        _lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        _lbl.setMaximumWidth(280)
        _lbl.setToolTip(
            _my_pc_help_tip("Typical GPU VRAM for this model class (estimate only; CPU fallback may apply).")
        )

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

    def _quant_opts_by_mode(fill_role: str, repo: str) -> dict:
        return {o.mode: o for o in supported_quant_modes(role=fill_role, repo_id=repo)}

    def _refresh_quant_value_lbl(
        rkey: str,
        fill_role: str,
        repo: str,
        auto_chk: QCheckBox,
        slider: NoWheelSlider,
        value_lbl: QLabel,
    ) -> None:
        modes = getattr(win, "_quant_manual_modes", {}).get(rkey) or ()
        opts = _quant_opts_by_mode(fill_role, repo)
        if auto_chk.isChecked() or not modes:
            value_lbl.setText("Automatic")
            value_lbl.setToolTip(
                _models_help_tip(
                    "Resolves quantization from available GPU memory (same policy as fit badges).",
                    slide=0,
                )
            )
            return
        idx = max(0, min(int(slider.value()), len(modes) - 1))
        m = modes[idx]
        opt = opts.get(m)
        value_lbl.setText(opt.label if opt else mode_label(m))
        raw_tip = (opt.tooltip if opt else "") or ""
        value_lbl.setToolTip(_models_help_tip(raw_tip, slide=0) if raw_tip.strip() else _models_help_tip("", slide=0))

    def _current_effective_quant_mode(rkey: str, auto_chk: QCheckBox, slider: NoWheelSlider) -> str:
        modes = getattr(win, "_quant_manual_modes", {}).get(rkey) or ()
        if auto_chk.isChecked() or not modes:
            return "auto"
        i = max(0, min(int(slider.value()), len(modes) - 1))
        return str(modes[i])

    def _sync_quant_slider_range(
        auto_chk: QCheckBox,
        slider: NoWheelSlider,
        value_lbl: QLabel,
        rkey: str,
        fill_role: str,
        repo: str,
    ) -> None:
        modes = manual_quant_modes_low_to_high(role=fill_role, repo_id=repo)
        win._quant_manual_modes[rkey] = modes
        was_a = auto_chk.signalsBlocked()
        was_s = slider.signalsBlocked()
        auto_chk.blockSignals(True)
        slider.blockSignals(True)
        try:
            if not modes:
                slider.setMinimum(0)
                slider.setMaximum(0)
                slider.setEnabled(False)
                slider.setVisible(False)
                value_lbl.setVisible(False)
                auto_chk.setChecked(True)
                auto_chk.setEnabled(False)
            else:
                slider.setVisible(True)
                value_lbl.setVisible(True)
                auto_chk.setEnabled(True)
                n = len(modes)
                slider.setMinimum(0)
                slider.setMaximum(max(0, n - 1))
                slider.setSingleStep(1)
                slider.setPageStep(1)
                slider.setTickPosition(QSlider.TickPosition.NoTicks)
                slider.setEnabled(not auto_chk.isChecked())
        finally:
            auto_chk.blockSignals(was_a)
            slider.blockSignals(was_s)

    def _apply_want_quant_ui(
        rkey: str,
        fill_role: str,
        repo: str,
        auto_chk: QCheckBox,
        slider: NoWheelSlider,
        value_lbl: QLabel,
        want: str,
    ) -> None:
        modes = getattr(win, "_quant_manual_modes", {}).get(rkey) or ()
        want_s = str(want or "auto").strip().lower()

        if not modes:
            auto_chk.blockSignals(True)
            auto_chk.setChecked(True)
            auto_chk.blockSignals(False)
            _refresh_quant_value_lbl(rkey, fill_role, repo, auto_chk, slider, value_lbl)
            return

        if want_s == "auto":
            auto_chk.blockSignals(True)
            auto_chk.setChecked(True)
            auto_chk.blockSignals(False)
            slider.blockSignals(True)
            slider.setEnabled(False)
            slider.blockSignals(False)
        else:
            ix = index_of_manual_mode(modes, want_s)
            auto_chk.blockSignals(True)
            auto_chk.setChecked(False)
            auto_chk.blockSignals(False)
            slider.blockSignals(True)
            slider.setEnabled(True)
            slider.setValue(ix)
            slider.blockSignals(False)
        _refresh_quant_value_lbl(rkey, fill_role, repo, auto_chk, slider, value_lbl)

    def _quant_controls_panel(auto_chk: QCheckBox, slider: NoWheelSlider, value_lbl: QLabel) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(auto_chk)
        row = QHBoxLayout()
        row.setSpacing(8)
        slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(slider, 1)
        row.addWidget(value_lbl, 0)
        v.addLayout(row)
        return panel

    win.llm_quant_panel = _quant_controls_panel(win.llm_quant_auto_chk, win.llm_quant_slider, win.llm_quant_value_lbl)
    win.img_quant_panel = _quant_controls_panel(win.img_quant_auto_chk, win.img_quant_slider, win.img_quant_value_lbl)
    win.vid_quant_panel = _quant_controls_panel(win.vid_quant_auto_chk, win.vid_quant_slider, win.vid_quant_value_lbl)
    win.voice_quant_panel = _quant_controls_panel(
        win.voice_quant_auto_chk, win.voice_quant_slider, win.voice_quant_value_lbl
    )

    def _ensure_model_combo_valid_selection(combo: QComboBox) -> None:
        if _combo_repo_id_from_selection(combo):
            return
        _pick_first_enabled(combo)

    def _update_fit_badges() -> None:
        for c in (win.llm_combo, win.img_combo, win.vid_combo, win.voice_combo):
            _ensure_model_combo_valid_selection(c)
        try:
            from debug import debug_enabled, dprint

            if debug_enabled("ui"):
                sig = (
                    _combo_repo_id_from_selection(win.llm_combo) or "",
                    _combo_repo_id_from_selection(win.img_combo) or "",
                    _combo_repo_id_from_selection(win.vid_combo) or "",
                    _combo_repo_id_from_selection(win.voice_combo) or "",
                )
                if getattr(win, "_fit_badge_debug_sig", None) != sig:
                    win._fit_badge_debug_sig = sig
                    dprint(
                        "ui",
                        "settings fit badges refresh",
                        f"llm={sig[0][:64]!r}",
                        f"img={sig[1][:64]!r}",
                        f"vid={sig[2][:64]!r}",
                        f"voice={sig[3][:64]!r}",
                    )
        except Exception:
            pass
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
                    _models_help_tip(
                        "No local snapshot under models/ yet (or below minimum size).\n"
                        + "\n".join(f"{r}: not downloaded" for r in uniq),
                        slide=2,
                    )
                )
                return
            if len(have) < len(uniq):
                lbl.setText("◐ Partial")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#6EC8FF;")
                lbl.setToolTip(
                    _models_help_tip(
                        "Some weights on disk; others missing.\n"
                        + "\n".join(
                            f"{r}: {local_model_size_label(r, models_dir=ms)}"
                            if model_has_local_snapshot(r, models_dir=ms)
                            else f"{r}: not downloaded"
                            for r in uniq
                        ),
                        slide=2,
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
                    _models_help_tip(
                        f"Downloaded in models/: {sizes_tooltip()}\n\n"
                        "Checksum status unknown - use Download → Verify checksums to confirm files.",
                        slide=2,
                    )
                )
                return

            bad_known = [s for s in known if str(s) != "ok"]
            if bad_known:
                w = worst_integrity_status(bad_known)
                tips = {
                    "missing": "Reported files are missing locally (incomplete download or wrong tree). Re-download if needed.",
                    "corrupt": "Checksum mismatch - one or more files are wrong or damaged. Re-download this model.",
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
                lbl.setToolTip(_models_help_tip(f"{tips.get(w, '')}\n\n{sizes_tooltip()}{extra}", slide=2))
                return

            if unknown_repos:
                lbl.setText("✓ On disk")
                lbl.setStyleSheet(_dl_badge_base_style() + "color:#5DFFB0;")
                ok_rs = [uniq[i] for i, s in enumerate(integ) if s == "ok"]
                lbl.setToolTip(
                    _models_help_tip(
                        f"Checksum OK for: {', '.join(ok_rs)}.\n"
                        f"Not verified yet: {', '.join(unknown_repos)}.\n\n{sizes_tooltip()}",
                        slide=2,
                    )
                )
                return

            lbl.setText("✓ Verified")
            lbl.setStyleSheet(_dl_badge_base_style() + "color:#5DFFB0;")
            lbl.setToolTip(_models_help_tip("Local files matched Hugging Face checksums.\n\n" + sizes_tooltip(), slide=2))

        def set_badge(
            lbl: QLabel,
            *,
            kind: str,
            repo_id: str,
            pair_image_repo_id: str = "",
            quant_mode: str | None = None,
        ) -> None:
            opt = win._model_opt_by_repo.get(repo_id)
            speed = opt.speed if opt else "slow"
            marker, why = rate_model_fit_for_repo(
                kind=kind,
                speed=speed,
                repo_id=repo_id,
                pair_image_repo_id=pair_image_repo_id,
                vram_gb=_vram_for_kind(kind),
                ram_gb=win._hw_info.ram_gb,
                quant_mode=quant_mode,
            )
            lbl.setText(fit_marker_display(marker))
            lbl.setStyleSheet(_fit_badge_style(marker))
            lbl.setToolTip(_my_pc_help_tip(why))

        # Rebuilding manual quant steps resets the slider; preserve the live UI
        # selection when the same Hub repo is still selected; use ``AppSettings``
        # when the model row changes. See ``win._quant_ui_last_model_repo``.
        _last_mrepo = getattr(win, "_quant_ui_last_model_repo", None)
        if not isinstance(_last_mrepo, dict):
            _last_mrepo = {"script": None, "image": None, "video": None, "voice": None}

        def _refill_and_restore_quant(
            auto_chk: QCheckBox,
            slider: NoWheelSlider,
            value_lbl: QLabel,
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
                preserve_eff = _current_effective_quant_mode(rkey, auto_chk, slider)
            else:
                preserve_eff = ""

            _sync_quant_slider_range(auto_chk, slider, value_lbl, rkey, fill_role, r)

            modes_after = getattr(win, "_quant_manual_modes", {}).get(rkey) or ()
            want = preserve_eff if preserve_eff else ""
            if not want:
                want = str(getattr(win.settings, settings_attr, "auto") or "auto")
            if modes_after:
                if want != "auto" and want not in modes_after:
                    want = modes_after[index_of_manual_mode(modes_after, want)]
            else:
                want = "auto"

            _apply_want_quant_ui(rkey, fill_role, r, auto_chk, slider, value_lbl, want)
            _last_mrepo[rkey] = repo

        llm_repo = _combo_repo_id_from_selection(win.llm_combo)
        _refill_and_restore_quant(
            win.llm_quant_auto_chk,
            win.llm_quant_slider,
            win.llm_quant_value_lbl,
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
            qm = _current_effective_quant_mode("script", win.llm_quant_auto_chk, win.llm_quant_slider)
            pv = predict_vram_gb(role="script", repo_id=llm_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.llm_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.llm_vram_lbl.setToolTip(_my_pc_help_tip(pv.rationale))
        else:
            win.llm_vram_lbl.setText("-")
        if llm_repo:
            set_badge(win.llm_fit, kind="script", repo_id=llm_repo, quant_mode=qm)
            set_dl_badge(win.llm_dl_badge, [llm_repo])
        else:
            win.llm_fit.setText("-")
            win.llm_dl_badge.setText("")

        img_repo = _combo_repo_id_from_selection(win.img_combo)
        _refill_and_restore_quant(
            win.img_quant_auto_chk,
            win.img_quant_slider,
            win.img_quant_value_lbl,
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
            qm = _current_effective_quant_mode("image", win.img_quant_auto_chk, win.img_quant_slider)
            pv = predict_vram_gb(role="image", repo_id=img_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.img_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.img_vram_lbl.setToolTip(_my_pc_help_tip(pv.rationale))
        else:
            win.img_vram_lbl.setText("-")
        if img_repo:
            set_badge(win.img_fit, kind="image", repo_id=img_repo, quant_mode=qm)
            set_dl_badge(win.img_dl_badge, [img_repo])
        else:
            win.img_fit.setText("-")
            win.img_dl_badge.setText("")

        vid_repo = _combo_repo_id_from_selection(win.vid_combo)
        _refill_and_restore_quant(
            win.vid_quant_auto_chk,
            win.vid_quant_slider,
            win.vid_quant_value_lbl,
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
            qm = _current_effective_quant_mode("video", win.vid_quant_auto_chk, win.vid_quant_slider)
            pv = predict_vram_gb(role="video", repo_id=vid_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.vid_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.vid_vram_lbl.setToolTip(_my_pc_help_tip(pv.rationale))
        else:
            win.vid_vram_lbl.setText("-")
        if vid_repo:
            set_badge(win.vid_fit, kind="video", repo_id=str(vid_repo), pair_image_repo_id=pair_id, quant_mode=qm)
            set_dl_badge(win.vid_dl_badge, [vid_repo])
        else:
            win.vid_fit.setText("-")
            win.vid_dl_badge.setText("")

        voice_repo = _combo_repo_id_from_selection(win.voice_combo)
        _refill_and_restore_quant(
            win.voice_quant_auto_chk,
            win.voice_quant_slider,
            win.voice_quant_value_lbl,
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
            qm = _current_effective_quant_mode("voice", win.voice_quant_auto_chk, win.voice_quant_slider)
            pv = predict_vram_gb(role="voice", repo_id=voice_repo, base_low_gb=lo, base_high_gb=hi, mode=qm)  # type: ignore[arg-type]
            win.voice_vram_lbl.setText(pv.display(mode=qm))  # type: ignore[arg-type]
            win.voice_vram_lbl.setToolTip(_my_pc_help_tip(pv.rationale))
        else:
            win.voice_vram_lbl.setText("-")
        if voice_repo:
            set_badge(win.voice_fit, kind="voice", repo_id=voice_repo, quant_mode=qm)
            set_dl_badge(win.voice_dl_badge, [voice_repo])
        else:
            win.voice_fit.setText("-")
            win.voice_dl_badge.setText("")

    def _sync_local_model_combo_tooltip(combo: QComboBox) -> None:
        idx = combo.currentIndex()
        if idx < 0:
            ct = (combo.currentText() or "").strip()
            combo.setToolTip(_models_help_tip(ct, slide=0) if ct else _models_help_tip("", slide=0))
            return
        midx = combo.model().index(idx, 0)
        t = midx.data(Qt.ItemDataRole.ToolTipRole)
        if t is not None and str(t).strip():
            combo.setToolTip(help_tooltip_rich_unless_already(str(t), "models", slide=0))
        else:
            ct = (combo.currentText() or "").strip()
            combo.setToolTip(_models_help_tip(ct, slide=0) if ct else _models_help_tip("", slide=0))

    win.llm_combo.currentIndexChanged.connect(_update_fit_badges)
    win.img_combo.currentIndexChanged.connect(_update_fit_badges)
    win.vid_combo.currentIndexChanged.connect(_update_fit_badges)
    win.voice_combo.currentIndexChanged.connect(_update_fit_badges)
    win.llm_quant_auto_chk.toggled.connect(lambda _checked=False: _update_fit_badges())
    win.img_quant_auto_chk.toggled.connect(lambda _checked=False: _update_fit_badges())
    win.vid_quant_auto_chk.toggled.connect(lambda _checked=False: _update_fit_badges())
    win.voice_quant_auto_chk.toggled.connect(lambda _checked=False: _update_fit_badges())
    win.llm_quant_slider.valueChanged.connect(lambda _v=0: _update_fit_badges())
    win.img_quant_slider.valueChanged.connect(lambda _v=0: _update_fit_badges())
    win.vid_quant_slider.valueChanged.connect(lambda _v=0: _update_fit_badges())
    win.voice_quant_slider.valueChanged.connect(lambda _v=0: _update_fit_badges())
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
        quant_panel: QWidget,
        vram_l: QLabel,
        fit_l: QLabel,
    ) -> QFrame:
        """Responsive role block: title/fit, full-width model, metadata, quantization (auto + slider)."""
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

        quant_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay_card.addWidget(quant_panel)
        return card

    _model_rows: list[tuple[str, QComboBox, QLabel, QWidget, QLabel, QLabel]] = [
        ("Script model (LLM)", win.llm_combo, win.llm_dl_badge, win.llm_quant_panel, win.llm_vram_lbl, win.llm_fit),
        ("Image model (diffusion stills)", win.img_combo, win.img_dl_badge, win.img_quant_panel, win.img_vram_lbl, win.img_fit),
        ("Video model (motion / Pro / scenes)", win.vid_combo, win.vid_dl_badge, win.vid_quant_panel, win.vid_vram_lbl, win.vid_fit),
        ("Voice model (TTS)", win.voice_combo, win.voice_dl_badge, win.voice_quant_panel, win.voice_vram_lbl, win.voice_fit),
    ]
    for _txt, combo, dl_b, quant_panel, vram_l, fit_l in _model_rows:
        ll.addWidget(_model_role_card(_txt, combo, dl_b, quant_panel, vram_l, fit_l))

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
                rr = _combo_repo_id_from_selection(win.llm_combo)
                _sync_quant_slider_range(
                    win.llm_quant_auto_chk,
                    win.llm_quant_slider,
                    win.llm_quant_value_lbl,
                    "script",
                    "script",
                    rr,
                )
                _apply_want_quant_ui(
                    "script",
                    "script",
                    rr,
                    win.llm_quant_auto_chk,
                    win.llm_quant_slider,
                    win.llm_quant_value_lbl,
                    str(q or "auto"),
                )
            if ranked.image_quant_modes:
                q = ranked.image_quant_modes[win.img_combo.currentIndex()] if win.img_combo.currentIndex() >= 0 else ""
                rr = _combo_repo_id_from_selection(win.img_combo)
                _sync_quant_slider_range(
                    win.img_quant_auto_chk,
                    win.img_quant_slider,
                    win.img_quant_value_lbl,
                    "image",
                    "image",
                    rr,
                )
                _apply_want_quant_ui(
                    "image",
                    "image",
                    rr,
                    win.img_quant_auto_chk,
                    win.img_quant_slider,
                    win.img_quant_value_lbl,
                    str(q or "auto"),
                )
            if ranked.video_quant_modes:
                q = ranked.video_quant_modes[win.vid_combo.currentIndex()] if win.vid_combo.currentIndex() >= 0 else ""
                rr = _combo_repo_id_from_selection(win.vid_combo)
                _sync_quant_slider_range(
                    win.vid_quant_auto_chk,
                    win.vid_quant_slider,
                    win.vid_quant_value_lbl,
                    "video",
                    "video",
                    rr,
                )
                _apply_want_quant_ui(
                    "video",
                    "video",
                    rr,
                    win.vid_quant_auto_chk,
                    win.vid_quant_slider,
                    win.vid_quant_value_lbl,
                    str(q or "auto"),
                )
            if ranked.voice_quant_modes:
                q = ranked.voice_quant_modes[win.voice_combo.currentIndex()] if win.voice_combo.currentIndex() >= 0 else ""
                rr = _combo_repo_id_from_selection(win.voice_combo)
                _sync_quant_slider_range(
                    win.voice_quant_auto_chk,
                    win.voice_quant_slider,
                    win.voice_quant_value_lbl,
                    "voice",
                    "voice",
                    rr,
                )
                _apply_want_quant_ui(
                    "voice",
                    "voice",
                    rr,
                    win.voice_quant_auto_chk,
                    win.voice_quant_slider,
                    win.voice_quant_value_lbl,
                    str(q or "auto"),
                )
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
    win.models_external_apply_btn.setToolTip(
        _models_help_tip("Save path and storage mode to settings.", slide=3)
    )
    win.models_external_detect_btn = QPushButton("Detect")
    win.models_external_detect_btn.setToolTip(
        _models_help_tip(
            "List model snapshots found under the resolved folder (uses path field when External).",
            slide=3,
        )
    )
    win.models_external_path_edit.setText(str(getattr(win.settings, "models_external_path", "") or ""))
    win.models_external_path_edit.setToolTip(
        _models_help_tip(
            "Absolute path to a folder for Hugging Face model snapshots when storage is External. "
            "Apply saves the path; Detect lists repos found on disk.",
            slide=3,
        )
    )
    win.models_external_browse_btn.setToolTip(_models_help_tip("Choose a folder for external model snapshots.", slide=3))

    ext_row = QHBoxLayout()
    ext_row.addWidget(win.models_external_path_edit, 1)
    ext_row.addWidget(win.models_external_browse_btn, 0)
    ext_row.addWidget(win.models_external_apply_btn, 0)
    ext_row.addWidget(win.models_external_detect_btn, 0)
    ll.addLayout(ext_row)

    win.models_storage_mode_combo.setToolTip(
        _models_help_tip(
            "Default: snapshots under .Aquaduct_data/models. External: another folder for large disks or shared "
            "libraries - set path, Apply, Detect.",
            slide=3,
        )
    )
    storage_hint = QLabel("Default .Aquaduct_data/models, or External + path + Apply - hover storage toggle for detail.")
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
                    f"Model list updated from Hugging Face. {bad} not listed online-dimmed unless already in models/."
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
    api_hint = QLabel("API mode: cloud generation - hover the scroll area below for full detail.")
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
    scroll.setToolTip(
        _api_help_tip(
            "API mode runs script, stills, and (optionally) voice via cloud APIs - no local diffusion weights. "
            "Configure providers and keys in the panel below (same controls appear on the API tab). "
            "FFmpeg still runs locally for assembly.",
            slide=1,
        )
    )
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
