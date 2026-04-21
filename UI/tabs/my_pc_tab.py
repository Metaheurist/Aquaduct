from __future__ import annotations

import os
from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
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
from UI.no_wheel_controls import NoWheelComboBox


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

    header = QLabel("My PC (hardware + model fit)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    info = get_hardware_info()
    sub = QLabel("Summary + what models should fit on this machine (uses GPU policy below).")
    sub.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(sub)

    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setStyleSheet("QFrame { background: #14141A; border: 1px solid #2A2A34; border-radius: 10px; }")
    card_lay = QVBoxLayout(card)

    form = QFormLayout()
    form.setLabelAlignment(form.labelAlignment() | 0x2)
    os_lbl = QLabel(info.os)
    cpu_lbl = QLabel(info.cpu)
    ram_lbl = QLabel(f"{info.ram_gb:.1f} GB" if info.ram_gb else "(not detected)")
    gpu_summary = QLabel()
    if info.gpu_names_all:
        gpu_summary.setText(info.gpu_names_all)
    else:
        gpu_summary.setText(info.gpu_name or "(not detected)")
    vram_lbl = QLabel(f"{info.vram_gb:.1f} GB (max across GPUs)" if info.vram_gb else "(not detected)")
    for v in (os_lbl, cpu_lbl, ram_lbl, gpu_summary, vram_lbl):
        v.setStyleSheet("font-weight: 600;")

    form.addRow("OS", os_lbl)
    form.addRow("CPU", cpu_lbl)
    form.addRow("RAM", ram_lbl)
    form.addRow("GPU(s)", gpu_summary)
    form.addRow("VRAM (summary)", vram_lbl)
    card_lay.addLayout(form)

    gpus = list_cuda_gpus()
    gpu_table = QTableWidget()
    gpu_table.setColumnCount(5)
    gpu_table.setHorizontalHeaderLabels(["#", "Name", "VRAM (GB)", "SMs", "CC"])
    gpu_table.verticalHeader().setVisible(False)
    gpu_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    gpu_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    if gpus:
        gpu_table.setRowCount(len(gpus))
        for r, g in enumerate(gpus):
            gpu_table.setItem(r, 0, QTableWidgetItem(str(g.index)))
            gpu_table.setItem(r, 1, QTableWidgetItem(g.name))
            gpu_table.setItem(r, 2, QTableWidgetItem(f"{g.total_vram_gb:.2f}"))
            gpu_table.setItem(r, 3, QTableWidgetItem(str(g.multiprocessor_count)))
            cc = f"{g.major}.{g.minor}" if g.major or g.minor else "—"
            gpu_table.setItem(r, 4, QTableWidgetItem(cc))
        gpu_table.resizeColumnsToContents()
    else:
        gpu_table.setRowCount(1)
        gpu_table.setItem(0, 0, QTableWidgetItem("—"))
        gpu_table.setItem(0, 1, QTableWidgetItem("No CUDA GPUs detected (or PyTorch CPU-only)."))
    card_lay.addWidget(QLabel("Detected GPUs"))
    card_lay.addWidget(gpu_table)

    policy_row = QHBoxLayout()
    policy_row.addWidget(QLabel("GPU policy:"))
    win.gpu_policy_combo = NoWheelComboBox()
    win.gpu_policy_combo.addItem("Auto — LLM on compute-heuristic GPU, diffusion on max VRAM", "auto")
    win.gpu_policy_combo.addItem("Single GPU — pin all local stages to one device", "single")
    policy_row.addWidget(win.gpu_policy_combo, 1)
    card_lay.addLayout(policy_row)

    dev_row = QHBoxLayout()
    dev_row.addWidget(QLabel("Device:"))
    win.gpu_device_combo = NoWheelComboBox()
    dev_row.addWidget(win.gpu_device_combo, 1)
    card_lay.addLayout(dev_row)

    policy_hint = QLabel(
        "Auto does not merge VRAM — it picks where each stage runs. "
        '"Faster" for LLM is a heuristic (SMs × clock), not a benchmark.'
    )
    policy_hint.setWordWrap(True)
    policy_hint.setStyleSheet("color: #8A8A96; font-size: 12px;")
    card_lay.addWidget(policy_hint)

    hint = QLabel(
        "Rule of thumb: ≥ 8GB VRAM is the sweet spot for SDXL Turbo on the diffusion GPU. "
        "The pipeline unloads models between stages to reduce peak VRAM."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #B7B7C2; margin-top: 6px;")
    card_lay.addWidget(hint)
    lay.addWidget(card)

    legend = QLabel(
        "<b>Fit markers</b> (same codes as <code>rate_model_fit_for_repo</code> / Model tab): "
        "<b>EXCELLENT</b>, <b>OK</b>, <b>RISKY</b>, <b>UNKNOWN</b>, and internal <code>NO_GPU</code> "
        "shown as <b>VRAM Limit</b>. Colors: green / blue / amber / gray / red."
    )
    legend.setWordWrap(True)
    legend.setTextFormat(Qt.TextFormat.RichText)
    legend.setStyleSheet("color: #B7B7C2; margin-top: 8px;")
    lay.addWidget(legend)

    policy_legend = QLabel(
        "Fit uses <b>effective VRAM</b> per model kind from <b>GPU policy</b> above — "
        "Auto: script (LLM) vs image/video (diffusion) may use different GPUs; Single: one GPU for all. "
        "See docs/hardware.md."
    )
    policy_legend.setWordWrap(True)
    policy_legend.setTextFormat(Qt.TextFormat.RichText)
    policy_legend.setStyleSheet("color: #9A9AA8; font-size: 12px;")
    lay.addWidget(policy_legend)

    env_legend = QLabel()
    env_legend.setWordWrap(True)
    env_legend.setTextFormat(Qt.TextFormat.RichText)
    raw_env = (os.environ.get("AQUADUCT_CUDA_DEVICE") or "").strip()
    if raw_env:
        env_legend.setText(
            f"<b>Environment:</b> <code>AQUADUCT_CUDA_DEVICE={raw_env}</code> — overrides saved GPU policy; "
            "fit rows below follow this pinned device."
        )
        env_legend.setStyleSheet("color: #E8C080; font-size: 12px;")
    else:
        env_legend.setText(
            "<span style='color:#6A6A78;font-size:12px;'>"
            "Tip: set <code>AQUADUCT_CUDA_DEVICE</code> to force one CUDA index for all stages (overrides UI policy).</span>"
        )
    lay.addWidget(env_legend)

    table = QTableWidget()
    opts = model_options()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["Kind", "Model", "Speed", "Fit", "Why"])
    table.setRowCount(len(opts))
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

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
        win.gpu_policy_combo.blockSignals(True)
        win.gpu_policy_combo.setCurrentIndex(1 if mode == "single" else 0)
        win.gpu_policy_combo.blockSignals(False)
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
        win.gpu_device_combo.setEnabled(mode == "single" and bool(gpus))

    def _on_gpu_policy_changed(_i: int = 0) -> None:
        mode = str(win.gpu_policy_combo.currentData() or "auto")
        win.gpu_device_combo.setEnabled(mode == "single" and bool(gpus))
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

    win.gpu_policy_combo.currentIndexChanged.connect(_on_gpu_policy_changed)
    win.gpu_device_combo.currentIndexChanged.connect(_on_gpu_device_changed)

    lay.addWidget(table, 1)

    win.tabs.addTab(w, "My PC")
