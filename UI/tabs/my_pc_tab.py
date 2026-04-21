from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.models.hardware import (
    fit_marker_display,
    get_hardware_info,
    list_cuda_gpus,
    rate_model_fit_for_repo,
)
from src.models.model_manager import model_options
from src.util.cuda_device_policy import effective_vram_gb_for_kind
from UI.gpu_policy_toggle import GpuPolicyToggle
from UI.no_wheel_controls import NoWheelComboBox
from UI.tab_sections import add_section_spacing, section_card, section_title


def _fit_colors(marker: str) -> tuple[QColor, QColor]:
    marker = (marker or "").upper().strip()
    if marker == "EXCELLENT":
        return QColor("#12381F"), QColor("#CFFFE0")
    if marker == "OK":
        return QColor("#0F2F45"), QColor("#D7F1FF")
    if marker == "RISKY":
        return QColor("#3C2D12"), QColor("#FFE7C2")
    if marker == "NO_GPU":
        return QColor("#3B1414"), QColor("#FFD2D2")
    return QColor("#2A2A2F"), QColor("#E6E6F0")


def attach_my_pc_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("My PC")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    sub = QLabel("Hardware summary and per-model fit (uses GPU policy below).")
    sub.setStyleSheet("color: #B7B7C2;")
    sub.setToolTip("Effective VRAM per model kind follows Auto vs Select GPU and cuda_device_policy.")
    lay.addWidget(sub)

    info = get_hardware_info()
    gpus = list_cuda_gpus()

    sys_f, sys_lay = section_card()
    sys_lay.addWidget(section_title("This machine", emphasis=True))

    form = QFormLayout()
    form.setLabelAlignment(form.labelAlignment() | 0x2)
    os_lbl = QLabel(info.os)
    cpu_lbl = QLabel(info.cpu)
    ram_lbl = QLabel(f"{info.ram_gb:.1f} GB" if info.ram_gb else "(not detected)")
    gpu_block = QLabel()
    gpu_block.setWordWrap(True)
    if gpus:
        gpu_block.setText("\n".join(f"{g.name} ({g.total_vram_gb:.1f} GB)" for g in gpus))
    else:
        gpu_block.setText(info.gpu_name or "(not detected)")
    for v in (os_lbl, cpu_lbl, ram_lbl, gpu_block):
        v.setStyleSheet("font-weight: 600;")

    form.addRow("OS", os_lbl)
    form.addRow("CPU", cpu_lbl)
    form.addRow("RAM", ram_lbl)
    form.addRow("GPU(s)", gpu_block)
    sys_lay.addLayout(form)

    policy_row = QHBoxLayout()
    policy_row.addWidget(QLabel("GPU policy"))
    win.gpu_policy_toggle = GpuPolicyToggle()
    policy_row.addWidget(win.gpu_policy_toggle, 0)
    policy_row.addStretch(1)
    sys_lay.addLayout(policy_row)

    dev_wrap = QWidget()
    dev_row = QHBoxLayout(dev_wrap)
    dev_row.setContentsMargins(0, 0, 0, 0)
    dev_row.addWidget(QLabel("Device"))
    win.gpu_device_combo = NoWheelComboBox()
    dev_row.addWidget(win.gpu_device_combo, 1)
    sys_lay.addWidget(dev_wrap)
    win._my_pc_device_row = dev_wrap

    lay.addWidget(sys_f)

    table = QTableWidget()
    opts = model_options()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["Kind", "Model", "Speed", "Fit", "Why"])
    table.setRowCount(len(opts))
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setToolTip(
        "Fit markers match the Model tab (EXCELLENT / OK / RISKY / …). "
        "Rows use effective VRAM from the policy above (Auto vs Select GPU)."
    )

    def _fill_model_table() -> None:
        app = getattr(win, "settings", None)
        if app is None:
            return
        for r, opt in enumerate(opts):
            vk = effective_vram_gb_for_kind(opt.kind, gpus, app) if gpus else None
            vram_eff = vk if vk is not None else info.vram_gb
            marker, why = rate_model_fit_for_repo(
                kind=opt.kind,
                speed=opt.speed,
                repo_id=opt.repo_id,
                pair_image_repo_id=getattr(opt, "pair_image_repo_id", "") or "",
                vram_gb=vram_eff,
                ram_gb=info.ram_gb,
            )
            bg, fg = _fit_colors(marker)
            table.setItem(r, 0, QTableWidgetItem(opt.kind))
            table.setItem(r, 1, QTableWidgetItem(opt.repo_id))
            table.setItem(r, 2, QTableWidgetItem(opt.speed))
            fit_item = QTableWidgetItem(fit_marker_display(marker))
            fit_item.setBackground(bg)
            fit_item.setForeground(fg)
            table.setItem(r, 3, fit_item)
            table.setItem(r, 4, QTableWidgetItem(why))
        table.resizeColumnsToContents()

    def _sync_gpu_combos_from_settings() -> None:
        s = getattr(win, "settings", None)
        if s is None:
            return
        mode = str(getattr(s, "gpu_selection_mode", "auto") or "auto").strip().lower()
        win.gpu_policy_toggle.blockSignals(True)
        win.gpu_policy_toggle.setCurrentIndex(1 if mode == "single" else 0)
        win.gpu_policy_toggle.blockSignals(False)
        win.gpu_device_combo.blockSignals(True)
        win.gpu_device_combo.clear()
        if gpus:
            for g in gpus:
                win.gpu_device_combo.addItem(f"{g.index}: {g.name} ({g.total_vram_gb:.1f} GB)", int(g.index))
            want = int(getattr(s, "gpu_device_index", 0) or 0)
            for i in range(win.gpu_device_combo.count()):
                if int(win.gpu_device_combo.itemData(i)) == want:
                    win.gpu_device_combo.setCurrentIndex(i)
                    break
        win.gpu_device_combo.blockSignals(False)
        _update_device_row_visibility()

    def _update_device_row_visibility() -> None:
        mode = str(win.gpu_policy_toggle.currentData() or "auto")
        show_dev = bool(gpus) and mode == "single"
        win._my_pc_device_row.setVisible(show_dev)

    def _on_gpu_policy_changed(_i: int = 0) -> None:
        _update_device_row_visibility()
        if hasattr(win, "_save_settings"):
            win._save_settings()
        win.settings = win._collect_settings_from_ui() if hasattr(win, "_collect_settings_from_ui") else win.settings
        _fill_model_table()
        u = getattr(win, "_update_model_fit_badges", None)
        if callable(u):
            u()

    def _on_gpu_device_changed(_i: int = 0) -> None:
        if hasattr(win, "_save_settings"):
            win._save_settings()
        win.settings = win._collect_settings_from_ui() if hasattr(win, "_collect_settings_from_ui") else win.settings
        _fill_model_table()
        u = getattr(win, "_update_model_fit_badges", None)
        if callable(u):
            u()

    win.my_pc_model_fit_table = table
    win._refresh_my_pc_fit_table = _fill_model_table
    _sync_gpu_combos_from_settings()
    _fill_model_table()

    win.gpu_policy_toggle.currentIndexChanged.connect(_on_gpu_policy_changed)
    win.gpu_device_combo.currentIndexChanged.connect(_on_gpu_device_changed)

    add_section_spacing(lay)
    fit_f, fit_lay = section_card()
    fit_lay.addWidget(section_title("Model fit", emphasis=True))
    fit_lay.addWidget(table, 1)
    lay.addWidget(fit_f, 1)

    win.tabs.addTab(w, "My PC")
