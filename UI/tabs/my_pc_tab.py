from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from src.hardware import get_hardware_info, rate_model_fit
from src.model_manager import model_options


def attach_my_pc_tab(win) -> None:
    w = QWidget()
    lay = QVBoxLayout(w)

    header = QLabel("My PC (hardware + model fit)")
    header.setStyleSheet("font-size: 16px; font-weight: 700;")
    lay.addWidget(header)

    info = get_hardware_info()
    min_req = QLabel(
        "Minimum (recommended) for best results: NVIDIA GPU ≥ 8GB VRAM, RAM ≥ 16GB. "
        "This app will still run with fallbacks if models can’t load."
    )
    min_req.setStyleSheet("color: #B7B7C2;")
    lay.addWidget(min_req)

    hw = QPlainTextEdit()
    hw.setReadOnly(True)
    hw_lines = [
        f"OS: {info.os}",
        f"CPU: {info.cpu}",
        f"RAM: {info.ram_gb:.1f} GB" if info.ram_gb else "RAM: (not detected)",
        f"GPU: {info.gpu_name}" if info.gpu_name else "GPU: (not detected)",
        f"VRAM: {info.vram_gb:.1f} GB" if info.vram_gb else "VRAM: (not detected)",
    ]
    hw.setPlainText("\n".join(hw_lines))
    lay.addWidget(hw)

    table = QTableWidget()
    opts = model_options()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["Kind", "Model", "Speed", "Fit", "Why"])
    table.setRowCount(len(opts))
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

    for r, opt in enumerate(opts):
        marker, why = rate_model_fit(kind=opt.kind, speed=opt.speed, vram_gb=info.vram_gb, ram_gb=info.ram_gb)
        table.setItem(r, 0, QTableWidgetItem(opt.kind))
        table.setItem(r, 1, QTableWidgetItem(opt.repo_id))
        table.setItem(r, 2, QTableWidgetItem(opt.speed))
        table.setItem(r, 3, QTableWidgetItem(marker))
        table.setItem(r, 4, QTableWidgetItem(why))

    table.resizeColumnsToContents()
    lay.addWidget(table, 1)

    win.tabs.addTab(w, "My PC")
